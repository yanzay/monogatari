#!/usr/bin/env python3
"""
Monogatari — Engagement review (stage 3.5).

Runs *after* the validator has accepted the story and *before* the state
updater ships it. The validator proves the story is legal; this stage
asks whether it is **worth reading**.

The reviewer is **Rovo Dev** (the AI coding agent that's already authoring
the story in the same conversation). There is no external LLM call: the
script renders the story + rubric, Rovo Dev produces a structured review
inside the same conversation and writes it to `pipeline/review.json`,
and a separate `--mode finalize` step validates the file and computes
the average. The state updater (`pipeline/run.py --step 4`) then refuses
to ship unless `review.json.approved == true`.

Two modes:

  --mode print     (default) Renders the story + rubric and writes a blank
                   `pipeline/review.json` template. Rovo Dev fills it in.

  --mode finalize  Reads the filled-in review.json, validates the scores
                   are 1..5, computes the average, enforces the bar
                   (avg ≥ 3.5 and every dimension ≥ 3), and exits 0 only
                   if approved.

Bypass:

  --skip           Writes a `review.json` with `approved: true` and
                   `reviewer: "skip"` — for hot-fixes only. Auditing
                   shipped stories for `reviewer == "skip"` is the right
                   way to make this strict over time.
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
    # Review-honesty gate (added 2026-04-22): if the reviewer's own free-text
    # notes describe the prose as repetitive / awkward / nonsensical, the
    # corresponding numeric score must reflect that. Catches the failure
    # mode where reviewers were waving stories through with "small note: a
    # bit repetitive" while still scoring originality 4.
    try:
        from review_lint import review_honesty_issues
        errs.extend(review_honesty_issues(review))
    except ImportError:
        pass  # module missing — soft-skip (back-compat)
    return errs


def _compute_average(scores: dict) -> float:
    nums = [scores[d] for d in DIMENSIONS if isinstance(scores.get(d), int)]
    return round(sum(nums) / len(nums), 2) if nums else 0.0


def _meets_bar(scores: dict) -> bool:
    if not all(isinstance(scores.get(d), int) for d in DIMENSIONS):
        return False
    return _compute_average(scores) >= APPROVE_AVG and min(scores[d] for d in DIMENSIONS) >= APPROVE_MIN


# ── Main flows ──────────────────────────────────────────────────────────────
def _print_mode(story: dict) -> int:
    """Render the story + rubric to stdout, write a blank review.json
    template, and exit non-zero so the pipeline blocks until Rovo Dev
    fills in real scores and the reviewer re-runs --mode finalize."""
    print(_render_story_md(story))
    print()
    print(_render_rubric_md())
    print()

    template_path = DEFAULT_REVIEW_J
    template = _empty_template(story["story_id"], mode="rovo-dev")
    template_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote review template to {template_path}.")
    print("Rovo Dev: read pipeline/engagement_review_prompt.md, score the")
    print("story honestly, fill in pipeline/review.json (suggestions + approved),")
    print("then run:")
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
                    choices=["print", "finalize", "skip"],
                    help="print: render story+rubric and write blank review.json; "
                         "finalize: read filled-in review.json and validate it; "
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
    elif args.mode == "skip":
        rc = _skip_mode(story)
    else:
        print(f"Unknown mode: {args.mode}", file=sys.stderr)
        sys.exit(2)
    sys.exit(rc)


if __name__ == "__main__":
    main()
