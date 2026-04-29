#!/usr/bin/env python3
"""
Monogatari — Stories manifest builder.

Scans `stories/story_*.json` and writes:

  * stories/index.json       — root manifest (lightweight)
  * stories/index/p001.json  — page 1 of stories
  * stories/index/p002.json  — page 2 of stories
  * ...

The root manifest carries the list of pages plus per-page bounds:

    {
      "version":      2,
      "generated_at": "...",
      "n_stories":    1234,
      "page_size":    50,
      "pages": [
        {"page": 1, "path": "stories/index/p001.json",
         "first_story_id": 1, "last_story_id": 50, "n_stories": 50},
        ...
      ]
    }

A page payload contains the same per-story rows the legacy v1 manifest
used. The reader fetches the root manifest and then loads pages on
demand (Library renders one page at a time and supports virtualization).

Backward compatibility
----------------------
For corpora <= page_size, we still inline the rows in the root manifest
under a "stories" key (alongside "pages") so the old reader code path
keeps working. Callers that understand v2 should prefer "pages" for
larger corpora.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

# Make sibling modules importable when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import iter_stories  # noqa: E402

PAGE_SIZE = 50


def _scan_stories(stories_dir: Path) -> list[dict]:
    """Scan stories/ and produce one manifest row per story.

    All paths emitted into the manifest are repo-root-relative POSIX
    paths (e.g. "stories/story_1.json", "audio/story_1/s0.mp3"). The
    manifest ships in the static site and is fetched relative to the
    web origin — absolute filesystem paths would 404. The
    `audio_path_relative` test in pipeline/tests pins this invariant.
    """
    # Compute repo root so we can emit repo-relative POSIX paths even
    # when this script is invoked with an absolute `stories_dir`
    # (which is what `step_audio` / author_loop do — they pass `ROOT /
    # "stories"`). Without this rewrite the manifest's `path` field
    # ships as `/Users/.../stories/story_1.json` and the frontend 404s.
    repo_root = stories_dir.resolve().parent
    audio_root = repo_root / "audio"

    rows: list[dict] = []
    for sid, s in iter_stories(stories_dir):
        sentences = s.get("sentences", [])
        n_content = sum(
            1
            for sent in sentences
            for tok in sent.get("tokens", [])
            if tok.get("role") in ("content", "aux")
        )
        story_path = (stories_dir / f"story_{sid}.json").resolve()
        try:
            rel_path = story_path.relative_to(repo_root).as_posix()
        except ValueError:
            rel_path = story_path.as_posix()
        # Hard guard: refuse to ship an absolute path in the manifest.
        if rel_path.startswith("/") or rel_path.startswith("\\"):
            raise RuntimeError(
                f"build_manifest refuses to emit an absolute path: "
                f"{rel_path!r}. stories_dir ({stories_dir!r}) does not "
                f"live under repo_root ({repo_root!r})."
            )
        # `has_audio` is true iff the per-sentence audio dir actually
        # exists on disk for this story. Reading `sentences[0].audio`
        # is unreliable: the field may be a stale absolute path from a
        # pre-fix build, or empty for legacy stories whose audio is
        # synthesized by the frontend by convention.
        story_audio_dir = audio_root / f"story_{sid}"
        has_audio = (
            story_audio_dir.exists()
            and any(story_audio_dir.glob("s*.mp3"))
        )
        rows.append(
            {
                "story_id": s.get("story_id", sid),
                "path": rel_path,
                "title_jp": (s.get("title") or {}).get("jp", ""),
                "title_en": (s.get("title") or {}).get("en", ""),
                "n_sentences": len(sentences),
                "n_content_tokens": n_content,
                "n_new_words": len(s.get("new_words", [])),
                "n_new_grammar": len(s.get("new_grammar", [])),
                "has_audio": has_audio,
            }
        )
    return rows


def _paginate(rows: list[dict], page_size: int) -> list[list[dict]]:
    return [rows[i : i + page_size] for i in range(0, len(rows), page_size)]


def build(stories_dir: Path, page_size: int = PAGE_SIZE) -> tuple[dict, list[list[dict]]]:
    rows = _scan_stories(stories_dir)
    pages = _paginate(rows, page_size)

    page_summaries = []
    for i, page_rows in enumerate(pages, start=1):
        page_summaries.append(
            {
                "page": i,
                "path": f"stories/index/p{i:03d}.json",
                "first_story_id": page_rows[0]["story_id"] if page_rows else None,
                "last_story_id": page_rows[-1]["story_id"] if page_rows else None,
                "n_stories": len(page_rows),
            }
        )

    root = {
        "version": 2,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "n_stories": len(rows),
        "page_size": page_size,
        "pages": page_summaries,
    }
    # Backward-compat: inline rows for small corpora so old readers keep working.
    if len(rows) <= page_size:
        root["stories"] = rows

    return root, pages


def write_manifest(stories_dir: Path, page_size: int = PAGE_SIZE) -> dict:
    """Build and persist the v2 paginated manifest.

    Writes `stories_dir/index.json` and refreshes `stories_dir/index/p*.json`.
    Returns the root manifest dict (so callers can report on it).
    """
    root, pages = build(stories_dir, page_size=page_size)

    (stories_dir / "index.json").write_text(
        json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    page_dir = stories_dir / "index"
    if page_dir.exists():
        shutil.rmtree(page_dir)
    page_dir.mkdir(parents=True, exist_ok=True)

    for i, page_rows in enumerate(pages, start=1):
        payload = {
            "version": 2,
            "page": i,
            "page_size": page_size,
            "stories": page_rows,
        }
        (page_dir / f"p{i:03d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return root


def main() -> None:
    stories_dir = Path("stories")
    if not stories_dir.exists():
        print(f"ERROR: {stories_dir} not found", file=sys.stderr)
        sys.exit(1)
    root = write_manifest(stories_dir)
    n_pages = len(root.get("pages", []))
    print(
        f"✓ Wrote stories/index.json + {n_pages} page(s) "
        f"({root['n_stories']} stories, page_size={PAGE_SIZE})"
    )


if __name__ == "__main__":
    main()
