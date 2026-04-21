# Monogatari

A graded-reader for learning Japanese through LLM-authored short stories,
with guaranteed vocabulary control, click-to-lookup reading, audio playback,
an integrated SRS reviewer, and offline support.

> **Status:** M1–M7 implemented. See `docs/spec.md` for the full system spec.

## Run the reader

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

The reader is a static page (HTML + CSS + vanilla JS). All learner state is
persisted in `localStorage`. After the first visit, the service worker caches
the app shell + the stories + audio you've opened so the reader works fully
offline.

## Author a new story

The pipeline runs in five stages plus a deliberate quality gate, orchestrated
by `pipeline/run.py`:

```
plan → write → validate → engagement review → ship (state updater) → audio
```

```bash
# Step 1 — generate plan.json (LLM-driven; or hand-author for now)
python3 pipeline/run.py --step 1 --n-new-words 3 --n-new-grammar 1 --theme "..."

# Step 2 — validate the plan
python3 pipeline/run.py --step 2

# Step 3 — write story_raw.json (LLM-driven; or hand-author)
#          then validate it
python3 pipeline/run.py --step 3

# Step 3.5 — engagement review (the validator only proves the story is
#            *legal* — this stage asks whether it's *worth reading*).
#            Score 1–5 on hook / voice / originality / coherence / closure.
#            Approval requires average ≥ 3.5 and every dimension ≥ 3.
python3 pipeline/engagement_review.py --mode print     # writes review template
# (edit pipeline/review.json — set scores, suggestions, approved:true)
python3 pipeline/engagement_review.py --mode finalize  # validates the review

# Step 4 — ship (validate state → check engagement-review approval →
#                update state → manifest rebuild → audio build)
python3 pipeline/run.py --step 4
#   - default: synth backend (offline tones, deterministic)
#   - real TTS: --tts-backend google --tts-encoding MP3
#   - bypass review (emergencies only): --skip-engagement-review
```

The engagement-review prompt + rubric live in
`pipeline/engagement_review_prompt.md`. An LLM mode (`--mode llm`) is
wired but currently uses a conservative stub that refuses approval —
swap in a real model call when ready.

## Audio: synth vs Google TTS

Two backends are wired in `pipeline/audio_builder.py`:

| Backend  | Network? | Output | Use when                                           |
| -------- | -------- | ------ | -------------------------------------------------- |
| `synth`  | no       | WAV    | offline dev / CI; deterministic; not intelligible. |
| `google` | yes      | MP3 / WAV / OGG | real ja-JP voice via Google Cloud TTS.    |

Google backend setup (one-time):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install google-cloud-texttospeech
gcloud auth application-default login
# then enable Cloud Text-to-Speech API for the project
```

Then:

```bash
python pipeline/audio_builder.py stories/story_1.json \
  --vocab data/vocab_state.json \
  --backend google --voice ja-JP-Neural2-B --audio-encoding MP3 --force
```

Cost-safety: the builder is **idempotent** by default (skips existing files).
Use `--dry-run` (or `MONOGATARI_TTS_DRY_RUN=1`) to print the planned API
calls without billing.

## Validation

```bash
# Story validator (per shipped story file)
python3 pipeline/validate.py stories/story_3.json \
  --vocab data/vocab_state.json --grammar data/grammar_state.json

# State validator (catches placeholder / scaffold entries)
python3 pipeline/validate_state.py

# Internal test suite (44 tests covering all 10 validator checks)
python3 pipeline/test_validate.py
```

## Repository layout

```
index.html, css/, js/         reader app (single page)
sw.js                         service worker (offline cache)

stories/                      shipped story artifacts (JSON)
audio/story_<N>/*.mp3         per-sentence + per-word audio

data/
  vocab_state.json            cumulative vocabulary
  grammar_state.json          cumulative grammar points

state_backups/                automatic backup before each ship

pipeline/
  planner.py / planner_prompt.md
  writer.py  / writer_prompt.md
  validate.py / validate_state.py / test_validate.py
  state_updater.py
  audio_builder.py
  run.py                      orchestrator (steps 1–4)

docs/
  spec.md                     full system spec
  authoring.md                authoring rules
```

## Defenses in depth

- **`pipeline/validate.py`** — single-story validator (10 checks).
- **`pipeline/validate_state.py`** — refuses to ship when vocab/grammar
  state files contain placeholder / scaffold entries.
- **`pipeline/state_updater.py`** — raises rather than write a placeholder
  if a story introduces grammar without a full definition in plan.json.
- **`js/app.js`** — UI shows a warning badge if a grammar entry is somehow
  shipped incomplete (last line of defense).

## License

Private project for personal use.
