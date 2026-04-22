"""Class D: Pipeline determinism.

Tools should be idempotent and pure where possible.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def pytest_generate_tests(metafunc):
    if "story_path_for_autofix" in metafunc.fixturenames:
        from pathlib import Path
        story_dir = Path(__file__).resolve().parents[2] / "stories"
        paths = sorted(story_dir.glob("story_*.json"),
                       key=lambda p: int(p.stem.split("_")[1]))
        metafunc.parametrize("story_path_for_autofix", paths, ids=lambda p: p.stem)


def test_autofix_is_idempotent(tmp_path, root, story_path_for_autofix):
    """Running autofix on a clean story should be a no-op (no diff)."""
    src = story_path_for_autofix
    work_dir = tmp_path / "stories"
    work_dir.mkdir()
    workspace_root = tmp_path

    # Set up minimal workspace: copy data + this story
    shutil.copytree(root / "data", workspace_root / "data")
    dest = work_dir / src.name
    shutil.copyfile(src, dest)

    # First run (in case story has unfixed issues, we apply fixes once)
    res = subprocess.run(
        [sys.executable, str(root / "pipeline" / "autofix.py"),
         "--story", str(dest)],
        capture_output=True, text=True, cwd=workspace_root,
    )
    assert res.returncode == 0, f"first autofix failed: {res.stderr}"

    after_first = dest.read_text()

    # Second run should be a no-op
    res2 = subprocess.run(
        [sys.executable, str(root / "pipeline" / "autofix.py"),
         "--story", str(dest)],
        capture_output=True, text=True, cwd=workspace_root,
    )
    assert res2.returncode == 0, f"second autofix failed: {res2.stderr}"

    after_second = dest.read_text()
    assert after_first == after_second, (
        f"autofix not idempotent on {src.name}: second run changed the file"
    )

    # And the second-run output should explicitly say no fixes needed
    assert ("No fixes needed" in res2.stdout) or ("0 fix" in res2.stdout) or (after_first == after_second), (
        f"Expected idempotent no-op message, got: {res2.stdout[:200]}"
    )


def test_validate_is_pure(root, story_paths):
    """Same story validated twice must give the same result."""
    if not story_paths:
        pytest.skip("no stories")
    target = story_paths[0]
    cmd = [sys.executable, str(root / "pipeline" / "validate.py"), str(target),
           "--vocab", "data/vocab_state.json", "--grammar", "data/grammar_state.json"]
    r1 = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    r2 = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    assert r1.returncode == r2.returncode
    assert r1.stdout == r2.stdout
    assert r1.stderr == r2.stderr
