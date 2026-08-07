"""Coverage tests for ``--all`` in ``scripts/check-windows-footguns.py``.

``--all`` is the mode the blocking "Windows footguns" CI job runs, and it
walks an allowlist of roots rather than the repository. A top-level Python
package that nobody adds to that list is therefore unguarded in the one place
the check is enforced — and silently so, because the job still prints
"✓ No Windows footguns found".

That is not hypothetical: ``tui_gateway`` arrived in #65895, two months after
the checker became blocking, was never added to the list, and accumulated a
raw ``os.kill(pid, 0)`` and a bare ``signal.SIGKILL``. Both sat on ``main``
with CI green until someone pointed the linter at the file by hand.

These tests fail when a new top-level package is added without a decision
about scanning it — either list it in ``all_scan_roots`` or record why it is
skipped in ``UNSCANNED_TOP_LEVEL``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINTER_PATH = REPO_ROOT / "scripts" / "check-windows-footguns.py"


def _load_linter_module():
    """Import the linter script as a module (it's not a package)."""
    spec = importlib.util.spec_from_file_location("check_windows_footguns", LINTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_windows_footguns"] = mod
    spec.loader.exec_module(mod)
    return mod


def _top_level_python_dirs() -> set[str]:
    """Top-level directories that contain at least one tracked ``.py`` file."""
    mod = _load_linter_module()
    found = set()
    for child in REPO_ROOT.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in mod.EXCLUDED_DIRS:
            continue
        if next(child.rglob("*.py"), None) is not None:
            found.add(child.name)
    return found


def test_every_top_level_package_is_scanned_or_explicitly_skipped():
    mod = _load_linter_module()
    scanned = {p.name for p in mod.all_scan_roots(REPO_ROOT) if p.is_dir()}
    unguarded = _top_level_python_dirs() - scanned - mod.UNSCANNED_TOP_LEVEL
    assert not unguarded, (
        "top-level Python package(s) not covered by `--all` and not listed in "
        f"UNSCANNED_TOP_LEVEL: {sorted(unguarded)}. The blocking CI job runs "
        "`--all`, so these are unguarded while CI still reports success. Add "
        "them to all_scan_roots(), or to UNSCANNED_TOP_LEVEL with a reason."
    )


def test_tui_gateway_is_scanned():
    """Regression lock for the specific package that slipped through."""
    mod = _load_linter_module()
    assert "tui_gateway" in {p.name for p in mod.all_scan_roots(REPO_ROOT) if p.is_dir()}


def test_top_level_modules_are_scanned():
    """``cli.py``, ``run_agent.py``, ``hermes_state.py`` … are shipped code too."""
    mod = _load_linter_module()
    scanned = {p.name for p in mod.all_scan_roots(REPO_ROOT) if p.is_file()}
    expected = {p.name for p in REPO_ROOT.glob("*.py")}
    assert expected, "sanity: repo root should contain top-level .py modules"
    assert expected <= scanned, f"unscanned top-level modules: {sorted(expected - scanned)}"


def test_skipped_packages_are_real():
    """``UNSCANNED_TOP_LEVEL`` must not accumulate stale entries."""
    mod = _load_linter_module()
    stale = {
        name
        for name in mod.UNSCANNED_TOP_LEVEL
        if not (REPO_ROOT / name).exists()
    }
    assert not stale, f"UNSCANNED_TOP_LEVEL names directories that no longer exist: {sorted(stale)}"
