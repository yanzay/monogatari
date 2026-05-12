# docs/archive — historical planning documents

These documents were accurate at the time of writing but describe decisions, plans, and migration work that has since been completed. They are retained for historical context only; the current system state is described in `docs/spec.md` and `docs/authoring.md`.

| File | Date | What it was |
|------|------|-------------|
| `audit-2026-04-27.md` | 2026-04-27 | Literary quality audit of the v1 corpus (56 stories). Identified the 5 recurring defect categories (noun-pile closer, bare-known-fact, misapplied-quiet, tautological equivalence, missing arc) that drove the v2 redesign. The lint rules from this audit (11.6–11.10) are now live in `pipeline/semantic_lint.py`. |
| `v2-strategy-2026-04-27.md` | 2026-04-27 | Strategy draft for v2: word-ladder design, 4 new lint rules, literary-review gate spec, migration/cascade analysis. All decisions in §4 were implemented; the LLM literary-review gate (`pipeline/literary_review.py`) was replaced by the in-skill discipline in SKILL.md. |
| `phase3-tasks-2026-04-28.md` | 2026-04-28 | Detailed task list for v2 implementation (Phase 3a–3d). Foundation tasks 1.1–1.15 are complete. The tools `echo.py`, `coverage.py`, `north_star.py`, and `arc.py` specified in §1 were not built; their functions were absorbed into `agent_brief.py` and the in-skill discipline. `pipeline/literary_review.py` was not built. |
| `phase4-bootstrap-reload-2026-04-29.md` | 2026-04-29 | Plan for the v2.5 corpus reset: per-story bootstrap ladder, prescriptive seed plan (`data/v2_5_seed_plan.json`), destructive reset of stories 1–10. The reset was executed; the corpus was re-authored from scratch. 15 stories are currently shipped. |
