# Monogatari v2 — Phase 3 Task List

**Decisions baked into this list (from open-questions answered 2026-04-28 00:14):**
- Cull policy: **default retire** (surviving corpus likely 32–40 stories)
- Reviewer: **same family, different persona prompt**
- Override: **logged soft override** (auto-suspends on 3rd use of same rule)
- Required spec fields: **all four** (intent, scene_class, anchor_object, per-sentence role)
- Agent identity: **fresh per story** (agent_brief.py is the entire memory)
- Authoring mode: **agent only**
- North-stars: **accept Claude's drafts** (§1.5 of strategy doc)
- Story 1: **revisit** to make it consistent with new lint rules
- Escalation: **best-effort + warn** (with the qualification in §0.1)
- v1 corpus: **clean break** (v1 frozen as `legacy/v1-stories/`, v2 starts at story 1)

## §0. Pre-execution discipline (read before starting any task)

### 0.1 Hardness clarification on "best-effort + warn"
You picked best-effort + warn for escalations. To prevent the new lints from becoming decorative, this is **scoped**:
- **Deterministic lints (validate.py, semantic_lint.py, the 4 new rules):** HARD BLOCK. Story does not ship until they pass. No best-effort.
- **Literary reviewer (LLM gate):** best-effort + warn after 3 rounds. Story ships with `"reviewer_escalation": true` flag and a queue entry in `data/escalations/`.
- **Cadence warnings:** never block; surface in agent_brief for next-story awareness.

### 0.2 Recurring human audit schedule
Because reviewer = same model family, blind-spot risk is real. Schedule:
- Every **10 new stories**, the human (you) reads the new batch with fresh eyes and surfaces any new defect category.
- Every new defect category becomes either a lint rule (deterministic, preferred) or a clause in the reviewer prompt.
- `cadence.py audit-due` reports when the next audit is due.

### 0.3 v1 freeze
Before any v2 work begins:
- Move `stories/*.json` → `legacy/v1-stories/`
- Move `pipeline/inputs/*.bilingual.json` → `legacy/v1-inputs/`
- Snapshot `data/vocab_state.json`, `data/grammar_state.json`, `data/grammar_catalog.json` to `legacy/v1-data/`
- v2 starts with empty `stories/`, empty `pipeline/inputs/` (except `_template.bilingual.json`), and a fresh `data/vocab_state.json` derived from the v1 inventory but with the §1.2 word-ladder applied.

---

## §1. Phase 3a — Foundation (no story authoring yet)

**Goal:** every piece of infrastructure the agent author depends on must exist and be tested before story 1 of v2 is authored.

### Task 1.1 — Mint the 3 new vocabulary entries
- Add **下 (した)**, **置きます (おきます)**, **持ちます (もちます)** to `data/vocab_state.json` (or its v2 successor).
- Add JLPT tier metadata, occurrences=0.
- Test: `vocab.py info` succeeds for each.

### Task 1.2 — Implement the 4 lint rules (§2 of strategy)
Files: `pipeline/semantic_lint.py`.
- 1.2a — Rule 11.6 `closer_noun_pile` (with escape hatches).
- 1.2b — Rule 11.7 `tautological_possessive_equivalence` (with name/job/home exemptions).
- 1.2c — Loosen rule 11.1 `inanimate_quiet_extended`.
- 1.2d — Loosen rule 11.3 `bare_known_fact_extended`.
- Tests: positive cases from the audit + negative cases from the SHIP list.

### Task 1.3 — Implement override discipline (§B2.2)
Files: new `pipeline/overrides.py`, `data/overrides.json`.
- Read `"override"` field from bilingual specs.
- Log every use to `data/overrides.json` with timestamp, story_id, rule_id, rationale.
- Block 3rd override of same rule by same agent run (escalates to human).
- `cadence.py overrides` reports usage stats.

### Task 1.4 — Build `pipeline/tools/palette.py`
JSON output by default. Composes word inventory by sensory category, with reinforcement-debt stars from `cadence.py`.
- Test: `palette.py 11 --format json` returns the expected structure.

### Task 1.5 — Build `pipeline/tools/echo.py`
Token-set Jaccard scan against all prior stories.
- `echo.py "<sentence>"` → list of stories with exact / near matches.
- `echo.py corpus-shapes --top 20` → most-reused sentence shapes (for agent_brief).

### Task 1.6 — Build `pipeline/tools/coverage.py`
Scene-type taxonomy from noun co-occurrence patterns.
- Output: scenes used vs. underused vs. never-depicted.
- Tested against the v1 corpus (frozen) for baseline calibration.

### Task 1.7 — Build `pipeline/tools/north_star.py`
Reads `data/north_stars.json` (populated from §1.5 of strategy doc).
- `north_star.py 11` → era's north-star + voice notes.

### Task 1.8 — Repurpose `arc.py`
- `arc.py classify <story.json>` → infers role per sentence (JSON).
- `arc.py validate <story.json>` → checks declared role matches detected role; checks arc shape validity.

### Task 1.9 — Build `pipeline/tools/agent_brief.py` ★
**The single most critical task.** Composes outputs of palette, north_star, echo, coverage, cadence into one JSON payload. Includes:
- size_band, available_words, available_grammar
- north_stars for the era
- scene_coverage (underused/overused)
- echo_warnings (top-20 reused sentence shapes)
- reinforcement_debt (critical/due)
- lint_rules_active (with one-line summaries)
- anti_patterns_to_avoid (5 audit defects + escape examples)
- previous_3_stories_summary (one-line each)

### Task 1.10 — Implement literary-review gate
Files: `pipeline/literary_review.py`, `data/reviews.json`.
- Same model family, strict editor-persona prompt, no shared scratchpad.
- Returns `{verdict, defects, specific_sentence_hints}`.
- 3-round retry cap; on failure, ship with `"reviewer_escalation": true` + queue entry.
- SHA-cached.

### Task 1.11 — Build `pipeline/author_loop.py`
The orchestrator from §B2.1. Replaces ad-hoc story authoring.
- Single CLI entry: `author_loop.py author <story_id>`.
- Runs the 7-step gauntlet.
- Logs every step's output for debugging.
- Refuses to write to `stories/*.json` if any deterministic step failed.

### Task 1.12 — Update `pipeline/inputs/_template.bilingual.json`
JSON template with required fields: intent, scene_class, anchor_object, characters, per-sentence role.

### Task 1.13 — Rewrite `docs/authoring.md` as agent runbook
Sections per §B4:
0. Audience: LLM agent
1. Goals invariants
2. The author-loop procedure
3. Failure modes and recovery (lint → action table)
4. Override discipline
5. Escalation criteria
6. Forbidden actions
7. Prompt fragments (the system prompt itself, kept in-doc)

### Task 1.14 — Populate `data/north_stars.json`
From §1.5 of strategy doc (10 north-stars for stories 1–10).

### Task 1.15 — Build `cadence.py audit-due` and `cadence.py overrides`
Reporting commands required by §0.1 and §0.2.

### Phase 3a verification
- All deterministic lints pass on a synthetic test story authored by hand to exercise each rule.
- `agent_brief.py 1` returns a complete, well-formed JSON payload.
- `author_loop.py author 1 --dry-run` exits clean against a hand-prepared story_1 spec.

**Estimated effort:** ~5 days.

---

## §2. Phase 3b — Author the v2 corpus, stories 1–10

**Goal:** 10 stories that establish voice and serve as the corpus's literary anchor. Quality bar is high because v2 has no other voice anchor.

### Per-story flow (executed by the agent, monitored by you)
For story N in 1..10:
1. Run `author_loop.py author N`.
2. Agent receives the JSON brief from `agent_brief.py N`.
3. Agent drafts spec, declares roles, writes to `pipeline/inputs/story_N.bilingual.json`.
4. Gauntlet runs. Failures → up to 3 retries.
5. On success → ship. On reviewer escalation → flag and continue.
6. Audio rebuild for story N.

### Human checkpoints
- After story 1: you read it. If voice is wrong, we revise the system prompt before authoring story 2.
- After story 5: mid-anchor checkpoint. Same.
- After story 10: full read of stories 1–10. This is the **first scheduled audit**.

### Hard rules
- No bare-known-fact, no tautological equivalence, no closer-noun-pile, no misapplied-quiet — enforced by lints.
- Every story must have one of: action verb beat, dialogue beat, inflection point — enforced by `arc.py validate`.
- Every story must declare anchor_object that appears in ≥3 sentences — enforced by spec validator.

**Estimated effort:** ~1 day for stories 1–10 if the gauntlet works as designed; ~2–3 days if reviewer iteration kicks in heavily (which it likely will for early stories until the prompt is tuned).

---

## §3. Phase 3c — Author the v2 corpus, stories 11–N

**Goal:** continue authoring until the v2 corpus is ≥ what v1 reached (or you decide to stop earlier).

### Process
- Same per-story flow as §2.
- Human audit after every 10 stories (so: 20, 30, 40, 50).
- Each audit may produce new lint rules or reviewer-prompt clauses; those land *before* the next batch is authored.

### Stopping criteria (you decide which applies)
- Reach story 32 (parity with v1 SHIP-list count) — minimum acceptable corpus.
- Reach story 56 (parity with v1 total) — full replacement.
- Reach the point where the 7th audit produces zero new defect categories — *empirical convergence*; the rule set is now sufficient.

### Cull-on-author defaults
- Per the "default retire" policy, when an agent fails 3 rounds *and* the literary reviewer escalates, the story is *not* shipped. Instead, the brief gets one more iteration with the human in the loop.
- Aim for a working ratio of ~80% first-pass-ship, ~15% reviewer-escalated-but-shipped, ~5% retired.

**Estimated effort:** depends on stopping criterion. If targeting 32 stories: ~3–5 days authoring + audits. If targeting 56: ~6–10 days.

---

## §4. Phase 3d — Hardening & monitoring

After the corpus settles:

### Task 4.1 — Recurring audit infrastructure
- `cadence.py audit-due` warns when human audit is overdue.
- Audits are saved to `docs/audit-YYYY-MM-DD.md` so the history of defect discovery is preserved.

### Task 4.2 — Drift detection
- `coverage.py drift` reports whether motif coverage is widening or narrowing across the last 10 stories.
- `cadence.py reuse-trend` reports whether echo-warning frequency is rising (sign of agent drifting toward defaults).

### Task 4.3 — Override audit
- `cadence.py overrides` is reviewed in every human audit.
- Frequently-used overrides → either lint loosening (rule was wrong) or lint hardening (rule wasn't strict enough; the agent was wriggling out).

### Task 4.4 — Reviewer prompt versioning
- `pipeline/literary_review.py` stores the reviewer-prompt version with each verdict.
- When the prompt is updated (after a human audit produces a new defect category), it gets a new version; affected stories can be re-reviewed selectively.

**Estimated effort:** ~1 day, mostly polish.

---

## §5. Total effort & parallelism

| Phase | Days | Parallelism |
|---|---|---|
| 3a — Foundation | ~5 | Tasks 1.1–1.15 mostly serial; 1.4–1.8 (the tools) parallelizable |
| 3b — Stories 1–10 | ~1–3 | Strictly serial (each story uses the prior corpus as context) |
| 3c — Stories 11–N | ~3–10 | Strictly serial; audits batched every 10 |
| 3d — Hardening | ~1 | Parallel with 3c after first audit |
| **Total** | **~10–19 days** | bounded |

The single biggest schedule risk is reviewer iteration in 3b (early stories before the prompt is tuned). If reviewer iteration explodes, escalate after story 3 to revise the reviewer prompt rather than power through.

---

## §6. What success looks like

When Phase 3 is complete:
- v2 corpus exists in `stories/`, ≥ 32 stories, all gauntlet-clean except a small number of reviewer-escalated entries.
- v1 corpus archived in `legacy/v1-stories/` (read-only).
- Every defect from `docs/audit-2026-04-27.md` either has a lint rule that catches it or is explicitly accepted by the reviewer prompt with rationale logged.
- Audits are scheduled and the audit-history doc is the long-term quality dashboard.
- You can author a new story by running `author_loop.py author <id>` and walking away — the agent + gauntlet does the rest. You read the result if you want.

## §7. What failure looks like

- After 6+ months, the corpus shows the same defects v1 had, just dressed in different vocabulary. Means the audit cycle wasn't run or its findings weren't codified into rules.
- Override count climbs steadily on a few rules. Means those rules are wrong or the agent is wriggling out; either way it's signal.
- Reviewer escalation rate stays above 20%. Means the gauntlet is too strict for the agent or the agent prompt is too weak; either way it's signal.

These are the things to watch in the first month, not the things to design against in advance.

---

*Drafted 2026-04-28 00:14 from the 10 open-question answers.*
