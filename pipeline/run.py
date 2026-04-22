#!/usr/bin/env python3
"""
Monogatari — Pipeline Runner (Rovo Dev mode)

Prints step-by-step instructions for generating a new story with Rovo Dev.
Authoring is performed by Rovo Dev (the AI coding agent in the
active conversation). No external model APIs are called.

Usage:
    python3 pipeline/run.py [--n-new-words 3] [--theme "evening walk"]
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def run(cmd: list[str]) -> int:
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def load_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Monogatari Pipeline (Rovo Dev mode)")
    parser.add_argument("--n-new-words",   type=int, default=3)
    parser.add_argument("--n-new-grammar", type=int, default=1)
    parser.add_argument("--theme",         default=None)
    parser.add_argument("--vocab",         default="data/vocab_state.json")
    parser.add_argument("--grammar",       default="data/grammar_state.json")
    parser.add_argument("--no-audio",      action="store_true",
                        help="Skip the audio build step at end of step 4")
    parser.add_argument("--tts-backend",
                        default=os.environ.get("MONOGATARI_TTS", "google"),
                        choices=["synth", "google"],
                        help="Audio backend at step 4d (default: google — see "
                             "docs/authoring.md § v0.11. Use synth only for "
                             "offline development; never ship with synth).")
    parser.add_argument("--tts-voice",
                        default=os.environ.get("MONOGATARI_TTS_VOICE", "ja-JP-Neural2-B"),
                        help="Google TTS voice name (when --tts-backend=google)")
    parser.add_argument("--tts-encoding",
                        default=os.environ.get("MONOGATARI_TTS_AUDIO", "LINEAR16"),
                        choices=["LINEAR16", "MP3", "OGG_OPUS"],
                        help="Google TTS audio encoding (when --tts-backend=google)")
    parser.add_argument("--step",          type=int, default=1,
                        help="Start from step (1=plan, 2=write, 3=validate, 4=ship)")
    parser.add_argument("--skip-engagement-review", action="store_true",
                        help="Bypass the stage-3.5 engagement review (emergency only)")
    parser.add_argument("--force-reship", action="store_true",
                        help="Allow step 4 to re-ship a story whose stories/story_N.json "
                             "already exists. Without this flag, step 4 refuses to run a "
                             "second time on the same story_id because state_updater.py is "
                             "non-idempotent and a re-ship double-increments occurrence "
                             "counts (and breaks the lifetime-occurrence pytest).")
    args = parser.parse_args()

    print("\n" + "═"*60)
    print("  Monogatari Pipeline — Rovo Dev authoring mode")
    print("═"*60)

    # ── Step 1: Generate planner prompt ──────────────────────────────────────
    if args.step <= 1:
        print("\n[Step 1] Generating planner prompt…")
        planner_args = [
            sys.executable, "pipeline/planner.py",
            "--n-new-words",   str(args.n_new_words),
            "--n-new-grammar", str(args.n_new_grammar),
            "--vocab",   args.vocab,
            "--grammar", args.grammar,
            "--prompt-out", "pipeline/planner_prompt.md",
        ]
        if args.theme:
            planner_args += ["--theme", args.theme]
        rc = run(planner_args)
        if rc != 0:
            sys.exit(rc)

        print("\n" + "─"*60)
        print("  ► ROVO DEV ACTION REQUIRED:")
        print("    Read pipeline/planner_prompt.md and produce pipeline/plan.json")
        print("─"*60)
        print("\nOnce plan.json is written, run:")
        print("  python3 pipeline/run.py --step 2")
        return

    # ── Step 2: Validate plan + generate writer prompt ────────────────────────
    if args.step == 2:
        plan_path = Path("pipeline/plan.json")
        if not plan_path.exists():
            print("ERROR: pipeline/plan.json not found. Run step 1 first.", file=sys.stderr)
            sys.exit(1)

        print("\n[Step 2a] Validating plan…")
        rc = run([sys.executable, "pipeline/planner.py", "--validate", str(plan_path),
                  "--vocab", args.vocab, "--grammar", args.grammar])
        if rc != 0:
            print("Fix plan.json and retry.")
            sys.exit(1)

        print("\n[Step 2b] Generating writer prompt…")
        rc = run([sys.executable, "pipeline/writer.py",
                  "--plan", str(plan_path),
                  "--vocab",   args.vocab,
                  "--grammar", args.grammar,
                  "--prompt-out", "pipeline/writer_prompt.md"])
        if rc != 0:
            sys.exit(rc)

        print("\n" + "─"*60)
        print("  ► ROVO DEV ACTION REQUIRED:")
        print("    Read pipeline/writer_prompt.md and produce pipeline/story_raw.json")
        print("─"*60)
        print("\nOnce story_raw.json is written, run:")
        print("  python3 pipeline/run.py --step 3")
        return

    # ── Step 3: Validate story ────────────────────────────────────────────────
    if args.step == 3:
        raw_path  = Path("pipeline/story_raw.json")
        plan_path = Path("pipeline/plan.json")

        if not raw_path.exists():
            print("ERROR: pipeline/story_raw.json not found.", file=sys.stderr)
            sys.exit(1)

        print("\n[Step 3a] Auto-repairing common authoring slips (autofix.py)…")
        rc = run([sys.executable, "pipeline/autofix.py", "--story", str(raw_path)])
        if rc != 0:
            print("\n✗ autofix failed (likely a path/IO issue, not your story).")
            sys.exit(1)

        print("\n[Step 3b] Validating story…")
        validate_args = [sys.executable, "pipeline/validate.py", str(raw_path),
                         "--vocab", args.vocab, "--grammar", args.grammar]
        if plan_path.exists():
            validate_args += ["--plan", str(plan_path)]
        rc = run(validate_args)

        if rc != 0:
            print("\n✗ Validation failed.")
            print("  Ask Rovo Dev to fix pipeline/story_raw.json based on the errors above,")
            print("  then retry: python3 pipeline/run.py --step 3")
            sys.exit(1)

        print("\n✓ Story valid!")
        print("\n" + "─"*60)
        print("  ► NEXT — Stage 3.5: engagement review")
        print("─"*60)
        print("  The validator only proves the story is legal. The next step")
        print("  asks whether it's worth reading. To open the review template:")
        print()
        print("    python3 pipeline/engagement_review.py --mode print")
        print()
        print("  Then edit pipeline/review.json (set scores + approved:true)")
        print("  and finalize:")
        print()
        print("    python3 pipeline/engagement_review.py --mode finalize")
        print()
        print("  Once review.json shows approved:true, ship with:")
        print("    python3 pipeline/run.py --step 4")
        return

    # ── Step 4: Ship (update state) ───────────────────────────────────────────
    if args.step == 4:
        # Pre-flight: make sure the existing state is clean — never ship on top
        # of an already-broken vocab/grammar file (e.g. unfilled scaffolds).
        print("\n[Step 4 pre] Validating existing state files…")
        rc = run([sys.executable, "pipeline/validate_state.py",
                  "--vocab", args.vocab, "--grammar", args.grammar])
        if rc != 0:
            print("Existing state files contain placeholders/issues. Fix them before shipping.")
            sys.exit(1)

        raw_path  = Path("pipeline/story_raw.json")
        plan_path = Path("pipeline/plan.json")

        if not raw_path.exists():
            print("ERROR: pipeline/story_raw.json not found.", file=sys.stderr)
            sys.exit(1)

        # ── Ship-once guard ─────────────────────────────────────────────────
        # state_updater.py is non-idempotent — a second run will double-
        # increment every word's occurrence count and break the lifetime-
        # occurrence pytest. The shipped story file is the canonical
        # 'has-this-already-shipped?' marker. Authors who genuinely need
        # to re-ship (e.g. after a post-ship JP token edit) must pass
        # --force-reship AND restore the pre-ship vocab/grammar state from
        # state_backups/ before running so the increment is applied to a
        # clean baseline. See docs/authoring.md G_STATE.
        try:
            raw_story = load_json(raw_path) or {}
            raw_sid = raw_story.get("story_id")
            if isinstance(raw_sid, int):
                shipped_path = Path("stories") / f"story_{raw_sid}.json"
                if shipped_path.exists() and not args.force_reship:
                    print(f"\n✗ stories/story_{raw_sid}.json already exists.")
                    print(f"  Step 4 refuses to re-ship the same story_id because")
                    print(f"  state_updater.py is non-idempotent and a re-run would")
                    print(f"  double-increment vocab occurrence counts.")
                    print(f"")
                    print(f"  If you really need to re-ship (e.g. you edited JP")
                    print(f"  tokens post-ship and need fresh audio + state):")
                    print(f"    1. Restore data/vocab_state.json and data/grammar_state.json")
                    print(f"       from the most recent state_backups/*.json taken BEFORE")
                    print(f"       the original ship of story {raw_sid}.")
                    print(f"    2. Re-run with --force-reship.")
                    print(f"")
                    print(f"  See docs/authoring.md § G_STATE for the recipe.")
                    sys.exit(1)
                if shipped_path.exists() and args.force_reship:
                    print(f"\n⚠  --force-reship: re-shipping over existing "
                          f"stories/story_{raw_sid}.json. Make sure you restored "
                          f"vocab/grammar state to the pre-ship baseline first.")
        except Exception as e:
            # Defensive: never let the guard itself break the ship of a
            # legitimate first-time story. If we can't read the raw file
            # cleanly, the validate step below will surface the real issue.
            print(f"  (ship-once guard skipped: {e})")

        # Final validation before shipping
        print("\n[Step 4a] Final validation…")
        validate_args = [sys.executable, "pipeline/validate.py", str(raw_path),
                         "--vocab", args.vocab, "--grammar", args.grammar]
        if plan_path.exists():
            validate_args += ["--plan", str(plan_path)]
        rc = run(validate_args)
        if rc != 0:
            print("Story failed final validation. Fix before shipping.")
            sys.exit(1)

        # Engagement-review gate. The story must have an approved review
        # before it can ship. The reviewer is Rovo Dev (the same agent
        # that authored the story), running --mode finalize. The
        # --skip-engagement-review flag bypasses the gate for emergencies
        # and leaves a visible 'reviewer: skip' in review.json so audits
        # can find it later.
        print("\n[Step 4a.5] Checking engagement review…")
        review_path = Path("pipeline/review.json")
        if args.skip_engagement_review:
            print("  ⚠  --skip-engagement-review passed; bypassing the gate.")
            run([sys.executable, "pipeline/engagement_review.py",
                 "--story", str(raw_path), "--mode", "skip"])
        elif not review_path.exists():
            print("✗ pipeline/review.json not found.")
            print("  Rovo Dev: run `python3 pipeline/engagement_review.py --mode print`")
            print("  to render the rubric, then fill in pipeline/review.json honestly")
            print("  and run `--mode finalize`.")
            print("  Pass --skip-engagement-review to bypass (not recommended).")
            sys.exit(1)
        else:
            review = load_json(review_path) or {}
            if not review.get("approved"):
                print("✗ Engagement review is not approved.")
                print(f"  Current scores: {review.get('scores')}")
                print(f"  Average:        {review.get('average')}")
                print("  Edit pipeline/story_raw.json (or pipeline/review.json) and re-run")
                print("  `python3 pipeline/engagement_review.py --mode finalize` until approved:true.")
                sys.exit(1)
            if review.get("story_id") != (load_json(raw_path) or {}).get("story_id"):
                print("✗ review.json.story_id does not match story_raw.json.story_id.")
                print("  Re-draft the review for the current story.")
                sys.exit(1)
            print(f"  ✓ Approved by {review.get('reviewer','?')} "
                  f"(avg {review.get('average','?')}).")

        print("\n[Step 4b] Updating state and shipping story…")
        updater_args = [sys.executable, "pipeline/state_updater.py", str(raw_path),
                        "--vocab", args.vocab, "--grammar", args.grammar]
        if plan_path.exists():
            updater_args += ["--plan", str(plan_path)]
        rc = run(updater_args)
        if rc != 0:
            sys.exit(rc)

        # Post-flight: verify the new state is also clean. If the plan was
        # missing a grammar definition this will catch the scaffold immediately.
        print("\n[Step 4c] Validating updated state files…")
        rc = run([sys.executable, "pipeline/validate_state.py",
                  "--vocab", args.vocab, "--grammar", args.grammar])
        if rc != 0:
            print("Updated state has incomplete entries. Fill them in (data/grammar_state.json")
            print("and/or data/vocab_state.json) and re-run validate_state.")
            sys.exit(1)

        story = load_json(raw_path)
        story_id = story.get("story_id", "?") if story else "?"

        # ── Step 4c.5: Rebuild stories manifest ──
        print("\n[Step 4c.5] Rebuilding stories/index.json…")
        rc = run([sys.executable, "pipeline/build_manifest.py"])
        if rc != 0:
            print("Manifest rebuild failed; reader will fall back to discovery probe.")

        # ── Step 4c.6: Append review to engagement baseline (idempotent) ──
        # Without this, the next ship's repo-health pytest fails on
        # test_leaderboard_covers_every_review. Doing it here means future
        # agents never have to remember it.
        print("\n[Step 4c.6] Updating engagement_baseline.json…")
        shipped_story = Path("stories") / f"story_{story_id}.json"
        run([sys.executable, "pipeline/engagement_review.py",
             "--story", str(shipped_story),
             "--mode",  "baseline"])

        # ── Step 4d: Audio (optional, on by default) ──
        if not getattr(args, "no_audio", False):
            backend = getattr(args, "tts_backend", "synth")
            print(f"\n[Step 4d] Building audio (backend={backend})…")
            shipped_story = Path("stories") / f"story_{story_id}.json"
            audio_cmd = [
                sys.executable, "pipeline/audio_builder.py",
                str(shipped_story),
                "--vocab", args.vocab,
                "--backend", backend,
            ]
            if backend == "google":
                audio_cmd += [
                    "--voice", args.tts_voice,
                    "--audio-encoding", args.tts_encoding,
                ]
            rc = run(audio_cmd)
            if rc != 0:
                print("Audio step failed — story shipped but has no audio yet.")
            else:
                # Audio paths just landed in the story JSON — rebuild manifest
                # so its `has_audio` flag reflects reality.
                run([sys.executable, "pipeline/build_manifest.py"])

        # ── Step 4e: Full repo-health test suite ──
        # Catches state drift, surface-grammar mis-tagging, manifest
        # gaps, audio orphans, etc. — anything the per-story validate
        # missed because the bug spans multiple files.
        print("\n[Step 4e] Running full repo-health test suite…")
        rc = run([sys.executable, "-m", "pytest", "pipeline/tests", "-q", "--tb=line"])
        if rc != 0:
            print("⚠  Tests failed AFTER ship. Story is on disk but state has integrity issues.")
            print("   Investigate before pushing. Common causes: stale lifetime occ, missing manifest entry,")
            print("   missing audio for an older story, or a new surface→grammar mis-tag.")
            sys.exit(1)

        print(f"\n{'═'*60}")
        print(f"  ✓ Story {story_id} shipped to stories/story_{story_id}.json")
        print(f"  Reload http://localhost:8000 and navigate to Story {story_id}")
        print(f"{'═'*60}\n")
        return

    # ── Step 6: Standalone repo-health check ─────────────────────────────────
    if args.step == 6:
        print("\n[Step 6] Repo health check (without authoring a story)…")

        print("\n  • State validator:")
        rc = run([sys.executable, "pipeline/validate_state.py",
                  "--vocab", args.vocab, "--grammar", args.grammar])
        state_ok = (rc == 0)

        print("\n  • Per-story validate (all shipped):")
        story_failures = []
        for p in sorted(Path("stories").glob("story_*.json"),
                        key=lambda p: int(p.stem.split("_")[1])):
            print(f"      {p.name}…", end=" ", flush=True)
            res = run([sys.executable, "pipeline/validate.py", str(p),
                       "--vocab", args.vocab, "--grammar", args.grammar])
            print("✓" if res == 0 else "✗")
            if res != 0:
                story_failures.append(p.name)

        print("\n  • Legacy validator unit tests:")
        legacy_rc = run([sys.executable, "pipeline/test_validate.py"])

        print("\n  • Repo-health pytest suite:")
        pytest_rc = run([sys.executable, "-m", "pytest", "pipeline/tests", "-q", "--tb=line"])

        if state_ok and not story_failures and legacy_rc == 0 and pytest_rc == 0:
            print("\n✓ All checks pass. Repo is healthy.")
        else:
            print("\n✗ One or more checks failed. See output above.")
            if story_failures:
                print(f"  Failed stories: {story_failures}")
            sys.exit(1)
        return

    print(f"Unknown step: {args.step}. Use --step 1, 2, 3, 4, or 6.")
    sys.exit(1)


if __name__ == "__main__":
    main()
