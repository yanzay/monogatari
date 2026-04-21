#!/usr/bin/env python3
"""
Monogatari — Engagement review (stage 3.5).

Runs *after* the validator has accepted the story and *before* the state
updater ships it. The validator proves the story is legal; this stage
asks whether it is **worth reading**.

The output is `pipeline/review.json` plus a human-readable
`pipeline/review.md`. The state updater (called by `pipeline/run.py
--step 4`) refuses to ship unless `review.json.approved == true`, so
this gate is enforced.

Two modes:

  --mode print   (default) Prints the story and the rubric to stdout
                 and asks you to fill in `pipeline/review.json` by hand
                 (template emitted automatically). No network, no cost.
                 Encourages deliberate human judgment.

  --mode llm     Calls an LLM to do the review. Requires no extra Python
                 dependencies; ships with a stub that produces a
                 conservative all-3 review and refuses approval. Replace
                 `_llm_review()` with a real API call when ready.

Bypass:

  --skip         Writes a `review.json` with `approved: true` and
                 `reviewer: "skip"` — for hot-fixes only. The CI script
                 should reject any shipped story that has reviewer ==
                 "skip" if you ever want to make this strict.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import textwrap
from pathlib import Path

DEFAULT_STORY    = Path("pipeline/story_raw.json")
DEFAULT_REVIEW_J = Path("pipeline/review.json")
DEFAULT_REVIEW_M = Path("pipeline/review.md")

DIMENSIONS = ["hook", "voice", "originality", "coherence", "closure"]
APPROVE_AVG = 3.5
APPROVE_MIN = 3


# ── Story rendering for the human reviewer ─────────────────────────────────
def _render_story_md(story: dict) -> str:
    lines: list[str] = []
    title    = (story.get("title") or {})
    subtitle = (story.get("subtitle") or {})
    lines.append(f"# Story {story.get('story_id')}: {title.get('jp','')} — *{title.get('en','')}*")
    if subtitle.get("jp") or subtitle.get("en"):
        lines.append(f"> {subtitle.get('jp','')} — *{subtitle.get('en','')}*")
    lines.append("")
    lines.append("| # | Japanese | English |")
    lines.append("|---|----------|---------|")
    for sent in story.get("sentences", []):
        jp = "".join(t["t"] for t in sent["tokens"])
        gloss = sent.get("gloss_en", "")
        lines.append(f"| {sent['idx']} | {jp} | {gloss} |")
    lines.append("")
    lines.append(f"*new_words:* {', '.join(story.get('new_words', []))}")
    lines.append(f"*new_grammar:* {', '.join(story.get('new_grammar', []))}")
    return "\n".join(lines)


def _render_rubric_md() -> str:
    return textwrap.dedent("""
    ## Rubric — score 1–5 each

    | Dimension     | What 5/5 looks like                                      |
    | ------------- | -------------------------------------------------------- |
    | hook          | First line drops the reader into a sensory moment.       |
    | voice         | A small "I" with consistent tone (quiet, playful, dry).  |
    | originality   | A small surprise or fresh juxtaposition.                 |
    | coherence     | Each sentence pulls forward; clear arc.                  |
    | closure       | Ends with an image or feeling that lingers.              |

    Approval requires: **average ≥ 3.5** AND **no score < 3**.
    """).strip() + "\n"


def _empty_template(story_id: int, mode: str) -> dict:
    return {
        "story_id": story_id,
        "scores": {d: None for d in DIMENSIONS},
        "average": None,
        "approved": False,
        "suggestions": [
            {"what": "", "why": ""},
        ],
        "notes": "",
        "reviewer": f"{mode}:unknown",
        "reviewed_at": None,
    }


def _validate_review(review: dict) -> list[str]:
    errs: list[str] = []
    scores = review.get("scores") or {}
    for d in DIMENSIONS:
        v = scores.get(d)
        if not isinstance(v, int) or not (1 <= v <= 5):
            errs.append(f"scores.{d} must be an int 1..5 (got {v!r})")
    if not isinstance(review.get("approved"), bool):
        errs.append("approved must be a boolean")
    return errs


def _compute_average(scores: dict) -> float:
    nums = [scores[d] for d in DIMENSIONS if isinstance(scores.get(d), int)]
    return round(sum(nums) / len(nums), 2) if nums else 0.0


def _meets_bar(scores: dict) -> bool:
    if not all(isinstance(scores.get(d), int) for d in DIMENSIONS):
        return False
    return _compute_average(scores) >= APPROVE_AVG and min(scores[d] for d in DIMENSIONS) >= APPROVE_MIN


# ── LLM stub ────────────────────────────────────────────────────────────────
def _llm_review(story: dict) -> dict:
    """Conservative stub: scores everything 3, refuses approval. Replace
    this with a real API call (OpenAI / Anthropic / Gemini) when ready.
    The shape of the returned dict must match the human review schema.
    """
    return {
        "story_id": story["story_id"],
        "scores": {d: 3 for d in DIMENSIONS},
        "average": 3.0,
        "approved": False,
        "suggestions": [
            {"what": "Replace this stub with a real LLM call in pipeline/engagement_review.py:_llm_review",
             "why":  "Currently returns identical 3s and refuses approval."},
        ],
        "notes": "LLM stub — no real model was called. Approval blocked on purpose.",
        "reviewer": "llm:stub",
        "reviewed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


# ── Main flows ──────────────────────────────────────────────────────────────
def _print_mode(story: dict) -> int:
    """Render the story + rubric to stdout, write a template review.json,
    and exit with a non-zero status so the pipeline blocks until the
    reviewer fills in real scores and re-runs."""
    print(_render_story_md(story))
    print()
    print(_render_rubric_md())
    print()

    template_path = DEFAULT_REVIEW_J
    template = _empty_template(story["story_id"], mode="human")
    template_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote review template to {template_path}.")
    print("Edit it (set scores, suggestions, approved, reviewer), then re-run:")
    print("  python3 pipeline/engagement_review.py --mode finalize")
    return 1


def _finalize_mode(story: dict) -> int:
    """Read the (presumably filled-in) review.json and validate it."""
    if not DEFAULT_REVIEW_J.exists():
        print(f"ERROR: {DEFAULT_REVIEW_J} not found. Run --mode print first.", file=sys.stderr)
        return 1
    review = json.loads(DEFAULT_REVIEW_J.read_text(encoding="utf-8"))
    errs = _validate_review(review)
    if errs:
        print("✗ Review is incomplete:")
        for e in errs:
            print(f"  - {e}")
        return 1
    review["average"] = _compute_average(review["scores"])
    if not _meets_bar(review["scores"]):
        review["approved"] = False
        print(f"✗ Story does not meet the engagement bar "
              f"(avg {review['average']}, min {min(review['scores'].values())}). "
              f"Lower bound: avg ≥ {APPROVE_AVG}, every dimension ≥ {APPROVE_MIN}.")
    elif not review.get("approved"):
        print(f"⚠ Scores meet the bar (avg {review['average']}) but reviewer "
              f"left approved=false. Set approved:true to ship.")
    else:
        print(f"✓ Approved (avg {review['average']}). Ready for step 4.")
    if not review.get("reviewed_at"):
        review["reviewed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    DEFAULT_REVIEW_J.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    DEFAULT_REVIEW_M.write_text(_render_story_md(story) + "\n\n" +
                                "## Review\n\n```json\n" +
                                json.dumps(review, ensure_ascii=False, indent=2) +
                                "\n```\n", encoding="utf-8")
    return 0 if review.get("approved") else 1


def _llm_mode(story: dict) -> int:
    review = _llm_review(story)
    review["average"] = _compute_average(review["scores"])
    if _meets_bar(review["scores"]):
        review["approved"] = True
    DEFAULT_REVIEW_J.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    DEFAULT_REVIEW_M.write_text(_render_story_md(story) + "\n\n" +
                                "## LLM review\n\n```json\n" +
                                json.dumps(review, ensure_ascii=False, indent=2) +
                                "\n```\n", encoding="utf-8")
    print(f"LLM review written to {DEFAULT_REVIEW_J}. Approved: {review.get('approved')}")
    return 0 if review.get("approved") else 1


def _skip_mode(story: dict) -> int:
    review = {
        "story_id": story["story_id"],
        "scores": {d: 3 for d in DIMENSIONS},
        "average": 3.0,
        "approved": True,
        "suggestions": [],
        "notes": "Engagement review skipped via --skip. Use only for emergencies.",
        "reviewer": "skip",
        "reviewed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    DEFAULT_REVIEW_J.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("⚠  Engagement review SKIPPED. review.json is marked approved.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Monogatari engagement review (stage 3.5).")
    ap.add_argument("--story",   default=str(DEFAULT_STORY),
                    help="Path to story_raw.json (default: pipeline/story_raw.json)")
    ap.add_argument("--mode",    default="print",
                    choices=["print", "finalize", "llm", "skip"],
                    help="print: render story+rubric and write template; "
                         "finalize: read filled-in review.json and validate; "
                         "llm: call the LLM stub; "
                         "skip: write an approved review (emergency only).")
    args = ap.parse_args()

    story_path = Path(args.story)
    if not story_path.exists():
        print(f"ERROR: story file not found: {story_path}", file=sys.stderr)
        sys.exit(2)
    story = json.loads(story_path.read_text(encoding="utf-8"))

    if args.mode == "print":
        rc = _print_mode(story)
    elif args.mode == "finalize":
        rc = _finalize_mode(story)
    elif args.mode == "llm":
        rc = _llm_mode(story)
    elif args.mode == "skip":
        rc = _skip_mode(story)
    else:
        print(f"Unknown mode: {args.mode}", file=sys.stderr)
        sys.exit(2)
    sys.exit(rc)


if __name__ == "__main__":
    main()
