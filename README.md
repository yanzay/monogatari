# Monogatari

A graded-reader app for learning Japanese through short stories with click-to-lookup vocabulary, integrated SRS, and per-token audio.

- **Reader** — a static web app (`index.html` + `js/app.js` + `css/style.css`). Open it in any browser; no server required.
- **Library** — 67 hand-curated short stories under `stories/`, plus per-token audio under `audio/`.
- **Authoring pipeline** — Python scripts under `pipeline/` that turn bilingual JP+EN text into a fully-tagged story JSON (vocabulary IDs, grammar IDs, inflections, glosses) and generate the matching audio.

## Quickstart

### Read

```bash
# Any static file server works
python3 -m http.server 8080
# Then open http://localhost:8080
```

### Author a new story

> **⚠ Always activate the project venv before running any pipeline script.**
> The regenerator depends on `fugashi`, `jamdict`, and `jaconv`. If any of
> those imports fail at runtime, `text_to_story` silently produces empty
> token arrays and the orphan-vocab cleanup at the end of a regen run will
> wipe `data/vocab_state.json`. The script now hard-fails on missing deps
> (and refuses to drop >50% of vocab as "orphans"), but you should still get
> in the habit of activating the venv first:
>
> ```bash
> source .venv/bin/activate     # macOS / Linux
> # .venv\Scripts\activate      # Windows PowerShell
> ```
>
> If `.venv/` doesn't exist yet:
>
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate
> pip install -r requirements.txt
> ```

```bash
# 1. Install authoring deps (one-time, inside the venv — see callout above)
pip install -r requirements.txt

# 2. Write your bilingual JP+EN spec — this is the source of truth
cat > pipeline/inputs/story_68.bilingual.json <<'EOF'
{
  "story_id": 68,
  "title":    {"jp": "雨", "en": "Rain"},
  "sentences": [
    {"jp": "今朝は雨です。",       "en": "This morning, it is raining."},
    {"jp": "私は窓から外を見ます。", "en": "I look outside through the window."}
  ]
}
EOF

# 3. Regenerate the entire library (idempotent; only changed stories rewritten)
python3 pipeline/regenerate_all_stories.py --apply

# 4. Validate
python3 pipeline/validate.py stories/story_68.json

# 5. Generate audio (requires Google Cloud TTS credentials)
python3 pipeline/audio_builder.py stories/story_68.json

# 6. Refresh manifest + run tests
python3 pipeline/build_manifest.py
python3 -m pytest pipeline/tests/
```

The bilingual spec is the only thing humans edit. `stories/story_68.json` is a derived artifact of `pipeline/inputs/story_68.bilingual.json` and is regenerated on demand. See [`docs/authoring.md`](docs/authoring.md) for the full workflow.

## Layout

```
index.html, js/, css/, sw.js     # Reader app (static)
stories/story_*.json             # Shipped stories (DERIVED from pipeline/inputs/)
audio/story_*/                   # Per-sentence + per-word MP3
data/                            # Cumulative vocab + grammar state
pipeline/
  inputs/                        # Bilingual JP+EN specs — SOURCE OF TRUTH
  text_to_story.py               # JP+EN text → story JSON (single-story entry point)
  regenerate_all_stories.py      # Bulk regenerator (reads inputs/, writes stories/)
  validate.py                    # Deterministic validator
  audio_builder.py               # Google TTS audio generator
  state_updater.py               # Update vocab_state + grammar_state after a new story
  jp.py                          # Tokenizer (fugashi/UniDic) and inflection helpers
  lookup.py                      # Vocab + grammar search CLI
  tests/                         # pytest suite
docs/
  spec.md                        # Data model and reader app spec
  authoring.md                   # Authoring workflow
```

## Tech

- **Reader**: vanilla JS, no build step, works offline (service worker)
- **Tokenizer**: [fugashi](https://github.com/polm/fugashi) + UniDic
- **Dictionary**: [jamdict](https://github.com/neocl/jamdict) (JMDict)
- **Kana conversion**: [jaconv](https://github.com/ikegami-yukino/jaconv)
- **Audio**: Google Cloud Text-to-Speech (Standard ja-JP voices)

## Tests

```bash
python3 -m pytest pipeline/tests/
```

The pytest suite covers schema integrity, validator correctness, referential integrity (audio ↔ tokens), and pedagogical sanity (vocabulary reinforcement, grammar progression).

## License

Personal-use project. Not yet licensed for redistribution.
