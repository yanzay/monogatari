#!/usr/bin/env python3
"""
Monogatari — Pipeline Runner (Rovo Dev mode)

Prints step-by-step instructions for generating a new story with Rovo Dev.
Does not call any external LLM API.

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
                        default=os.environ.get("MONOGATARI_TTS", "synth"),
                        choices=["synth", "google"],
                        help="Audio backend at step 4d (synth=offline, google=GCP TTS)")
    parser.add_argument("--tts-voice",
                        default=os.environ.get("MONOGATARI_TTS_VOICE", "ja-JP-Neural2-B"),
                        help="Google TTS voice name (when --tts-backend=google)")
    parser.add_argument("--tts-encoding",
                        default=os.environ.get("MONOGATARI_TTS_AUDIO", "LINEAR16"),
                        choices=["LINEAR16", "MP3", "OGG_OPUS"],
                        help="Google TTS audio encoding (when --tts-backend=google)")
    parser.add_argument("--step",          type=int, default=1,
                        help="Start from step (1=plan, 2=write, 3=validate, 4=ship)")
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

        print("\n[Step 3] Validating story…")
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
        print("\nTo ship the story, run:")
        print("  python3 pipeline/run.py --step 4")
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

        print(f"\n{'═'*60}")
        print(f"  ✓ Story {story_id} shipped to stories/story_{story_id}.json")
        print(f"  Reload http://localhost:8000 and navigate to Story {story_id}")
        print(f"{'═'*60}\n")
        return

    print(f"Unknown step: {args.step}. Use --step 1, 2, 3, or 4.")
    sys.exit(1)


if __name__ == "__main__":
    main()
