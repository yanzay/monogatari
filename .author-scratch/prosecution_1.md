# Prosecution table — story 1 (v2.5 cold start)

Hostile critic mode: every "yeah but" counts as a NO.

## Per-sentence

| # | role | JP (gist) | could I delete with no loss? | verb concrete-physical? | object load-bearing? | NOTES |
|---|---|---|---|---|---|---|
| s0 | setting | morning, kitchen is bright | NO — establishes scene + brightness as wake trigger | N (copula) | N/A | passes |
| s1 | setting | mother is in the kitchen | NO — second character on stage; sets up causality (she set out tea) | N (existence) | N/A | passes |
| s2 | setting | by the window there is a small tea | NO — anchor object first appearance | N (existence) | YES (anchor) | passes |
| s3 | setting | there is big bread too | YES — testable removal: if I cut s3 the story still works | N (existence) | partial — bread is mentioned once and never reused | **WEAKNESS**: bread fails the "decorative noun" anti-pattern |
| s4 | action | I walk to the kitchen | NO — narrator state change (offstage → onstage) | YES (歩きます) | N/A | passes |
| s5 | action | I look at mother | YES-ISH — informational, but doesn't change state. Could remove without losing arc | YES (見ます) | mother is not anchor | **WEAK** — looks like grammar-bait for 見ます |
| s6 | reflection | the tea is warm | NO — adds NEW info (temperature) not on page | N (copula) | tea is anchor | passes §C.1 reflection rule |
| s7 | closer | I hold the tea | NO — anchor changes location (table → hand); anchor causality satisfied | YES (持ちます) | YES (anchor) | passes |

## Contract checks

| contract claim | honored? | evidence |
|---|---|---|
| change_of_state (offstage → at table → holding tea) | **YES** | s4 (walk to kitchen) + s7 (holds tea); s0 vs s7 are materially different |
| anchor passes object-causality test | **YES** | tea changes location (window → hand) at s7 |
| closer is ACTION not noun-pile | **YES** | 私は茶を持ちます — subject + object + transitive verb |
| closer mirrors no prior closer | **YES** (vacuous — corpus empty) | n/a |
| every character earns slot | **PARTIAL** | mother is offstage causally (set out tea) but has no on-page action. s5 is the only beat between her and the narrator. **WEAKNESS**: mother is borderline decorative |
| no anti-patterns hit | **YES** | no 静か, no 思います, no tautological-equivalence, no noun-pile closer |
| seed plan honored (with documented amendments) | **YES** | 17 vocab + 10 grammar within ladder; 持ちます + の/へ/も amendments documented in spec.intent |

## Verdict

**OVERALL: PROVISIONAL SHIP** with 2 documented weaknesses:

1. **s3 「大きいパンもあります」** is borderline decorative. Bread is never picked up, eaten, or referenced again. It exists ONLY to land 大きい+パン+も in one sentence. Per §C.1 / anti-pattern "decorative-noun" this is a real defect — **but** it's the cheapest path to landing three obligated seeds. Decision: keep but flag for post-ship audit; if story 2 doesn't reuse bread, fix in the seed plan.

2. **s5 「私は母を見ます」** is grammar-bait for 見ます. Mother does nothing in response. **But** it weakly motivates the closer (narrator orients before turning to tea) and satisfies §B.2 q4. Decision: keep; if §E.7 flags independently, rewrite.

## Override budget burned this session: 0/1 (seed-plan amendments are permanent edits, not session overrides)
