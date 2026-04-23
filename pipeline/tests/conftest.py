"""Shared pytest fixtures for the Monogatari test suite."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

# Make pipeline modules and _helpers.py importable
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def vocab(root) -> dict:
    with (root / "data" / "vocab_state.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="session")
def grammar(root) -> dict:
    with (root / "data" / "grammar_state.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="session")
def catalog(root) -> dict:
    with (root / "data" / "grammar_catalog.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="session")
def stories(root) -> list[dict]:
    paths = sorted(
        (root / "stories").glob("story_*.json"),
        key=lambda p: int(p.stem.split("_")[1]),
    )
    out = []
    for p in paths:
        with p.open() as f:
            s = json.load(f)
        s["_path"] = p
        s["_id"] = p.stem
        out.append(s)
    return out


@pytest.fixture(scope="session")
def story_paths(root) -> list[Path]:
    return sorted(
        (root / "stories").glob("story_*.json"),
        key=lambda p: int(p.stem.split("_")[1]),
    )


def iter_tokens(story: dict):
    """Yield (section_name, sentence_idx_or_None, token_idx, token) for every token."""
    for sec_name in ("title",):
        sec = story.get(sec_name) or {}
        for j, tok in enumerate(sec.get("tokens", [])):
            yield (sec_name, None, j, tok)
    for i, sent in enumerate(story.get("sentences", [])):
        for j, tok in enumerate(sent.get("tokens", [])):
            yield ("sentence", i, j, tok)
