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

```bash
# 1. Install authoring deps (one-time)
pip install -r requirements.txt

# 2. Write your bilingual JP+EN spec
cat > pipeline/inputs/story_68.json <<'EOF'
{
  "story_id": 68,
  "title":    {"jp": "雨", "en": "Rain"},
  "subtitle": {"jp": "静かな朝", "en": "A quiet morning"},
  "sentences": [
    {"jp": "今朝は雨です。",       "en": "This morning, it is raining."},
    {"jp": "私は窓から外を見ます。", "en": "I look outside through the window."}
  ]
}
EOF

# 3. Convert text → story JSON
python3 pipeline/text_to_story.py pipeline/inputs/story_68.json \
    --out pipeline/story_raw.json --report pipeline/text_to_story.report.json

# 4. Validate
python3 pipeline/validate.py pipeline/story_raw.json

# 5. Generate audio (requires Google Cloud TTS credentials)
python3 pipeline/audio_builder.py pipeline/story_raw.json

# 6. Ship: copy to stories/ and update state
cp pipeline/story_raw.json stories/story_68.json
python3 pipeline/state_updater.py stories/story_68.json
```

See [`docs/authoring.md`](docs/authoring.md) for the full workflow.

## Layout

```
index.html, js/, css/, sw.js     # Reader app (static)
stories/story_*.json             # Shipped stories
audio/story_*/                   # Per-sentence + per-word MP3
data/                            # Cumulative vocab + grammar state
pipeline/                        # Authoring tools
  text_to_story.py               # JP+EN text → story JSON (the main authoring entry point)
  text_to_story_roundtrip.py     # Regression harness
  normalize_to_v2.py             # Schema normalizer (idempotent)
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
