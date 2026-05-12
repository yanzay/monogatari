# Monogatari — Authoring Guide

How to add a new story to the library. For the full system reference see [`spec.md`](spec.md).

## Overview

Authoring is **agent-driven and spec-first**. The agent writes a bilingual JSON spec (`pipeline/inputs/story_N.bilingual.json`), then runs `pipeline/author_loop.py author N`. The orchestrator runs the full deterministic gauntlet and, on success, ships the story, updates state, rebuilds `is_new` flags, and generates audio — all in one command.

```
pipeline/inputs/story_N.bilingual.json   ← THE source of truth (agent writes this)
        │
        ▼ author_loop.py author N
        │
        ├─ build (text_to_story.py)
        ├─ validate (Checks 1–11)
        ├─ mint_budget / pedagogical_sanity / vocab_reinforcement / coverage_floor
        ├─ write → stories/story_N.json  (state_updater + regenerate_all_stories)
        └─ audio → audio/story_N/ + audio/words/
```

**Never hand-edit `stories/*.json`.** The next regenerator run overwrites it.

The in-skill literary-review discipline (SKILL.md §B.0/B.1/§E.5/E.6/E.7/E.7.5/§G) runs **before** the live ship. Run `author_loop.py author N --dry-run` first; only run live once the dry-run is clean and the literary review passes.

## Prerequisites

> **⚠ Activate the project venv — every time.**
> Pipeline scripts depend on `fugashi`, `jamdict`, and `jaconv`. If imports fail, `text_to_story.build_story` silently emits empty token arrays.

```bash
# One-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Every shell session that touches pipeline/
source .venv/bin/activate

# For audio generation:
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<your-project-id>
```

> **Always invoke scripts from the project root**, not from inside `pipeline/`:
> ```bash
> python3 pipeline/author_loop.py author 11   # correct
> cd pipeline && python3 author_loop.py        # CWD doesn't persist — avoid
> ```

## The authoring flow

### Step 1 — Read the agent brief

```bash
python3 pipeline/author_loop.py author N --brief-only
```

The brief is the agent's entire memory for this story. It contains: the per-story ladder (mint budget, grammar floor/ceiling), seed-plan must-mints, reinforcement debts, available palette, forbidden zones, previous 3 story summaries, and coverage gaps. Read it fully before drafting.

### Step 2 — Run the literary pre-flight (in-skill)

Before writing the spec, run the in-skill discipline from SKILL.md:
- **§B.0 premise contract** — confirm scene, anchor, role arc are planned
- **§B.1 forbidden zones** — consult `pipeline/tools/forbid.py` for banned patterns
- **§E.5 prosecutor pass** — adversarial check on the drafted prose
- **§E.6 EN-only re-read** — read glosses aloud; flag awkward hedging
- **§E.7 / E.7.5 fresh-eyes review** — subagent reads with rubric

These gates catch literary defects (noun-pile closer, bare known fact, tautological equivalence, misapplied quiet, missing arc) before the deterministic gauntlet, so the discard cost is a re-draft — not a re-state.

### Step 3 — Write the bilingual spec

Create `pipeline/inputs/story_N.bilingual.json`:

```json
{
  "story_id": 11,
  "title":    {"jp": "図書館", "en": "The Library"},
  "intent":   "A student discovers a handwritten note inside a borrowed book.",
  "scene_class": "library",
  "anchor_object": "本",
  "lexical_overrides": [],
  "sentences": [
    {"jp": "今日、図書館で本を借りました。",  "en": "Today I borrowed a book from the library.", "role": "setting"},
    {"jp": "本の中に、手紙がありました。",    "en": "Inside the book, there was a letter.",      "role": "action"},
    {"jp": "手紙は古いです。",              "en": "The letter is old.",                          "role": "inflection"},
    {"jp": "誰が書きましたか。",            "en": "Who wrote it?",                               "role": "reflection"},
    {"jp": "私は手紙をそっと閉じました。",   "en": "I quietly closed the letter.",                "role": "closer"}
  ],
  "new_word_meanings": {
    "図書館": "library",
    "借ります": "to borrow"
  }
}
```

Required fields:
- **`story_id`** — next free integer after the highest in `stories/`.
- **`intent`** — one sentence describing authorial intent.
- **`scene_class`** — a value from `data/scene_affordances.json`.
- **`anchor_object`** — a JP noun that appears in ≥3 sentences.
- **`sentences[].role`** ∈ `{setting, action, dialogue, inflection, reflection, closer}` — one per sentence.
- **`sentences[].jp`** — must end with `。`, `！`, or `？`.
- **`sentences[].en`** — keep concise; Check 9 requires gloss ratio within `[0.7, 3.0]` × JP meaning-bearing tokens.
- **`new_word_meanings`** — optional but recommended for any word you expect to be new; otherwise the converter uses the first JMDict sense.

Optional:
- **`lexical_overrides`** — list of surfaces allowed to exceed the JLPT difficulty cap; max 2 per story.

### Step 4 — Dry-run the gauntlet

```bash
python3 pipeline/author_loop.py author N --dry-run
```

Runs all gauntlet steps except writing to `stories/` and generating audio. Fix any failures, iterate. Common failures:

| Failure | Fix |
|---------|-----|
| Check 5: inflection mismatch | UniDic picked the wrong homograph. Add a `LEMMA_OVERRIDES` entry in `pipeline/text_to_story.py` and re-run. |
| Check 7: token count out of band | Add or remove tokens until within the policy range for this story's tier. |
| Check 9: gloss ratio out of `[0.7, 3.0]` | Rewrite that sentence's English gloss — too terse or too verbose. |
| Check 11.7: closer noun-pile | Rewrite the closing sentence to include an action verb. |
| Check 11.8: tautological equivalence | Rewrite — avoid `XのY は ZのY です` structures. |
| mint_budget: too many new words | Reuse existing vocabulary; consult `vocab.py would-mint`. |
| coverage_floor: no new grammar | Introduce at least one grammar point from the current JLPT tier. |

### Step 5 — Ship (live run)

```bash
python3 pipeline/author_loop.py author N
```

On success the orchestrator:
1. Writes `stories/story_N.json`.
2. Runs `state_updater` to mint W-IDs and update `data/vocab_state.json` and `data/grammar_state.json`.
3. Runs `regenerate_all_stories --story N --apply` to rewrite `is_new` flags.
4. Runs `audio_builder` for per-sentence and per-word MP3s (incremental — existing audio is reused).

A failure exits non-zero with `halted_at: <step>`. The `state_backups/` directory retains the prior state for recovery.

### Step 6 — Final verification

```bash
python3 -m pytest pipeline/tests/ -q
```

Always run the full corpus test suite after any ship. A passing dry-run does **not** guarantee corpus tests pass — `test_vocabulary_introduction_cadence`, `test_vocab_words_are_reinforced`, `test_grammar_introduction_cadence`, and `test_audio_word_files_only_for_known_words` only fire here.

### Step 7 — Commit and push

Per standing convention: on a clean ship with pytest green, commit and push immediately:

```bash
git add stories/story_N.json audio/story_N/ audio/words/ \
        data/vocab_state.json data/grammar_state.json \
        data/vocab_attributions.json data/grammar_attributions.json \
        pipeline/inputs/story_N.bilingual.json
git commit -m "Ship story N: <title>"
git push
```

## Authoring tools

All tools require the project venv. Invoke from the project root.

### `pipeline/author_loop.py` — the gauntlet orchestrator

```bash
author_loop.py author N               # full gauntlet; ships if all steps pass
author_loop.py author N --dry-run     # all steps except write + audio
author_loop.py author N --brief-only  # emit agent_brief JSON and exit
author_loop.py author N --json        # machine-readable verdict report
```

### `pipeline/tools/vocab.py` — vocabulary inventory

```bash
vocab.py search 思                         # all words containing 思
vocab.py info W00043                       # full record + every story occurrence
vocab.py would-mint "毎日、本を読みます。"   # preview new mints before committing
vocab.py orphans --max 1                   # words used in ≤1 stories
vocab.py range W00080 W00098               # numeric range view
```

**`would-mint` is the right preflight.** Before drafting a sentence, run it through `would-mint` to see what new words it would introduce. Avoids the draft → tokenize → discover unknown word → rewrite loop.

### `pipeline/tools/palette.py` — word inventory by category

```bash
palette.py N              # available words for story N, grouped by sensory category
palette.py N --format json
```

### `pipeline/tools/cadence.py` — pedagogical cadence probe

```bash
cadence.py vocab-reinforce            # Rule R1: ≥1 reuse in next 10 stories
cadence.py grammar-reinforce          # Rule G2: introduced grammar reused
cadence.py validate                   # validate.py over the full library
cadence.py all                        # everything in one report
```

### `pipeline/tools/forbid.py` — banned patterns checker

```bash
forbid.py check "猫は静かです。"       # check a sentence for banned patterns
forbid.py list                         # show all active bans
```

### `pipeline/tools/spec.py` — surgical bilingual editor

```bash
spec.py show 11                              # pretty-print spec
spec.py append 11 --jp "…" --en "…"         # append a sentence
spec.py replace 11:3 --jp "…" --en "…"      # replace sentence index 3
spec.py delete 11:3                          # delete sentence index 3
spec.py move 11:3 --to 11:5                  # reorder within a story
spec.py find "鞄"                             # all stories containing 鞄
spec.py title 11 --jp "…" --en "…"          # change a title
```

### `pipeline/tools/weave.py` — reinforcement-weave assistant

```bash
weave.py suggest > plan.json     # auto-draft a plan: one stub per R1 violation
weave.py preview plan.json       # tokenize each weave; flag any mints
weave.py apply plan.json --regen # apply, regen library, validate
```

### `pipeline/tools/agent_brief.py` — full context for the agent

Called internally by `author_loop.py --brief-only`. Returns a JSON payload with: ladder, seed plan, mint budget, reinforcement debts, palette, forbidden zones, coverage gaps, echo warnings, and previous 3 story summaries.

### `pipeline/tools/regen.py` — story regeneration

```bash
regen.py story 11              # safe: full library regen (preserves first-occurrence)
regen.py story 11 --unsafe     # fast: regen one story; may corrupt is_new flags
regen.py all                   # equivalent to regenerate_all_stories.py --apply
regen.py validate              # validate every shipped story
regen.py diff 11               # show what regen would change for story 11
```

### `pipeline/tools/cadence.py` — backup garden

```bash
cleanup_state_backups.py                               # dry-run
cleanup_state_backups.py --keep 3 --days 3 --apply    # aggressive prune
```

### `pipeline/tools/cleanup_audio_orphans.py` — stale audio removal

```bash
cleanup_audio_orphans.py        # dry-run
cleanup_audio_orphans.py --apply
```

Detects: `audio/words/W*.mp3` whose ID is no longer in `vocab_state.json`; `audio/story_N/sX.mp3` where X exceeds current sentence count; legacy `audio/story_N/w_W*.mp3` files.

### `pipeline/lookup.py` — vocab and grammar search

```bash
python3 pipeline/lookup.py 飲む                # find a word
python3 pipeline/lookup.py --by-kana のむ      # find by kana
python3 pipeline/lookup.py --reuse-preflight   # what should I reinforce?
python3 pipeline/lookup.py --grammar te-form   # find a grammar point
```

## Adding a new grammar point

When your story uses a grammar surface not yet in `data/grammar_state.json`:

1. Add an entry to `data/grammar_catalog.json` with `id` (catalog form: `N5_foo_bar`), `title`, `short`, `long`, `jlpt`, `prerequisites`, `sources`.
2. Add the surface→ID mapping to `SURFACE_TO_GRAMMAR` in `pipeline/text_to_story.py`.
3. Add a matching entry to `text_to_story.KNOWN_AUTO_GRAMMAR_DEFINITIONS` if the point is auto-tagged by `_classify_inflection`.
4. Run `python3 pipeline/build_grammar_catalog.py` to refresh derived indices.
5. Re-run the gauntlet.

## Re-ship and recovery

### After a failed attempt with state changes

1. Restore `data/{vocab,grammar}_state.json` from `state_backups/` (most recent pre-attempt backup).
2. Run `cleanup_audio_orphans.py --apply` to remove stale audio.
3. Fix the spec and re-ship via `author_loop.py author N`.
4. Run `pytest pipeline/tests/ -q`.

### Corpus-wide regeneration (e.g. after editing an early spec)

```bash
python3 pipeline/regenerate_all_stories.py --apply
python3 -m pytest pipeline/tests/ -q
```

The regenerator is idempotent: a second `--apply` with no edits produces no changes.

### Full state reset

For corpus-wide rewrites that change vocab introduction order, a full reset is operationally cheaper than patching state in-place. See `AGENTS.md` ("Full state reset vs in-place spec edit") for the reset script.

## Naturalness checklist

Common defects the validator cannot catch — check these in the §E.7.5 native-naturalness review:

| Pattern | Problem | Fix |
|---------|---------|-----|
| 持つ for "take/receive/remove" | 持つ = "hold as ongoing state" only; 持ちました reads as "began carrying briefly" | Use 取る (pick up), 受け取る (receive), 出す (take out) |
| 小さい/大きい on mass nouns | 小さいお茶 not natural — size the container, not the liquid | 小さいお茶碗 |
| 「お金で買います」 | お金で is empty pedagogy — buying always implies money | Use で-means where means is genuinely informative |
| Bare 持ちません vs 持っていません | State-change needs te-iru + ません | 持っていません |
| Bare quoted 「…」 with no 言う/呼ぶ | Reads as stage direction, not prose | Add a framing verb |
| で vs に on stative verbs | で = activity-location; に = state-location | 「前に立っています」 not 「前で立っています」 |
| 歩く vs 行く inside a building | 歩く foregrounds manner; 行く is neutral | 行く for room-to-room movement |
| 見る on people in greeting context | 「母を見ます」 reads clinical | 母に会う or flip subject |
| Grammaticalized verbs in kanji | 有ります, 居ます, 成る — kanji form reads stiff | Use hiragana: あります, います, なる |

## Closer shape rotation

Fresh closer patterns become clichés after 2–3 stories. Before writing a closer, check the previous 3 stories' closing sentences for **shape** (subject-particle-attribute-copula, possessive-departure-verb, listing-equivalence). Matching shape = rotate.

Banned closer shapes:
- `N は [i-adj] です` — if already used as closer in the previous 3 stories
- Departure-walk (`〜を出ます / 歩きます`) — ban for 5 stories after first use
- Listing-と equivalence (`N₁と N₂は…です`) — same shape repeats banned

## Grammar cascade trap

Before introducing grammar G in story N, verify that at least one story in the range N+1 to N+5 already organically uses the construction. If none, defer G. Introducing a grammar point with no downstream usage triggers `test_introduced_grammar_is_reinforced` failure, which then requires editing downstream stories — a cascade.

```bash
grep '"grammar_id": "N5_foo_bar"' stories/story_*.json
```

## Troubleshooting

**"surface not in vocab and no `new_word_meanings` entry"** — Typo, or add an explicit meaning to `new_word_meanings`.

**"unknown grammar surface"** — Add the surface to `SURFACE_TO_GRAMMAR` in `text_to_story.py` or rephrase.

**Converter produces wrong reading or base form** — Add to `LEMMA_OVERRIDES` or `READING_OVERRIDES` in `text_to_story.py` and re-run.

**Audio generation fails** — Confirm `gcloud auth application-default login` is current and `GOOGLE_CLOUD_PROJECT` is set.

**Pytest fails after shipping** — Run `regen.py all` dry-run to see pending diffs. If diffs exist, `regen.py all` (applies). Then re-run pytest.

**`test_audio_word_files_only_for_known_words` fails** — Run `cleanup_audio_orphans.py --apply` to remove stale audio files.

**`test_vocab_state_carries_no_attribution_fields` fails** — A state_updater regression wrote `first_story`/`last_seen_story`/`occurrences` back onto `vocab_state.json`. Remove those keys and investigate the writer path.
