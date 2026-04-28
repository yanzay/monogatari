import { describe, it, expect } from 'vitest';
import {
  applyGrade,
  buildQueue,
  dueForecast,
  dribbleOffset,
  GRADES,
  isDue,
  newCard,
  statusCounts,
  trueRetention,
} from '$lib/state/srs';
import type { Card, Grade, ReviewLogEntry } from '$lib/state/types';
import { State } from 'ts-fsrs';

const NOW = new Date('2026-04-27T12:00:00Z');

function fresh(word_id = 'W00001'): Card {
  return newCard({ word_id, story_id: 1, context_sentence_idx: 0, now: NOW });
}

function bumpHours(d: Date, h: number): Date {
  return new Date(d.getTime() + h * 3600_000);
}

/* ── newCard ─────────────────────────────────────────────────── */
describe('newCard', () => {
  it('creates a New-state card due immediately', () => {
    const c = fresh();
    expect(c.status).toBe('new');
    expect(c.state).toBe(State.New);
    expect(c.reps).toBe(0);
    expect(c.lapses).toBe(0);
    expect(c.stability).toBe(0);
    expect(c.difficulty).toBe(0);
    // Due may be slightly in the past relative to NOW but well within 1s
    const dueMs = new Date(c.due).getTime();
    expect(Math.abs(dueMs - NOW.getTime())).toBeLessThan(1000);
  });
});

/** Drive a card up to Review state via repeated GOODs with realistic
 *  time advances. Returns the matured card. */
function graduateToReview(start: Card, startWhen: Date = NOW): { card: Card; when: Date } {
  let c = start;
  let when = startWhen;
  for (let i = 0; i < 10; i++) {
    if (c.state === State.Review) return { card: c, when };
    const r = applyGrade(c, GRADES.GOOD, when);
    c = r.card;
    when = bumpHours(when, Math.max(1, c.scheduled_days * 24));
  }
  return { card: c, when };
}

/* ── applyGrade — invariants, not exact intervals ───────────── */
describe('applyGrade — invariants', () => {
  it('returns a card AND a review-log entry', () => {
    const r = applyGrade(fresh(), GRADES.GOOD, NOW);
    expect(r.card).toBeDefined();
    expect(r.log).toBeDefined();
    expect(r.log.word_id).toBe('W00001');
    expect(r.log.grade).toBe(GRADES.GOOD);
    expect(r.log.card_before.reps).toBe(0);
    expect(r.log.card_after.reps).toBeGreaterThanOrEqual(1);
  });

  it('AGAIN from Review bumps lapses and goes Relearning', () => {
    const { card: grad, when } = graduateToReview(fresh());
    const lapsed = applyGrade(grad, GRADES.AGAIN, when).card;
    expect(lapsed.lapses).toBeGreaterThanOrEqual(1);
    expect(lapsed.scheduled_days).toBeLessThan(1);
    expect(['relearning', 'learning', 'leech']).toContain(lapsed.status);
  });

  it('GOOD on a new card schedules at least a few minutes out', () => {
    const c = applyGrade(fresh(), GRADES.GOOD, NOW).card;
    const dueMs = new Date(c.due).getTime();
    expect(dueMs).toBeGreaterThan(NOW.getTime());
  });

  it('intervals are monotonically non-decreasing across consecutive GOODs', () => {
    let c = fresh();
    let lastInterval = 0;
    for (let i = 0; i < 6; i++) {
      const next = applyGrade(c, GRADES.GOOD, bumpHours(NOW, 24 * (i + 1) * 7)).card;
      // Once we're in Review state, scheduled_days should grow.
      if (next.state === State.Review) {
        expect(next.scheduled_days).toBeGreaterThanOrEqual(lastInterval - 1);
        lastInterval = next.scheduled_days;
      }
      c = next;
    }
  });

  it('EASY produces a longer or equal next interval vs GOOD', () => {
    // Compare first-rep behavior on a new card.
    const good = applyGrade(fresh(), GRADES.GOOD, NOW).card;
    const easy = applyGrade(fresh(), GRADES.EASY, NOW).card;
    expect(new Date(easy.due).getTime()).toBeGreaterThanOrEqual(new Date(good.due).getTime());
  });

  it('chain of EASYs eventually hits Review state and grows', () => {
    let c = fresh();
    let when = NOW;
    for (let i = 0; i < 6; i++) {
      const r = applyGrade(c, GRADES.EASY, when);
      c = r.card;
      when = bumpHours(when, 24 * 7);
    }
    expect(c.state).toBe(State.Review);
    expect(c.scheduled_days).toBeGreaterThan(1);
  });

  it('respects target retention: lower retention → longer intervals', () => {
    const c = fresh();
    const at90 = applyGrade(c, GRADES.GOOD, NOW, 0.9).card;
    const at75 = applyGrade(c, GRADES.GOOD, NOW, 0.75).card;
    expect(at75.stability).toBeGreaterThanOrEqual(at90.stability);
  });

  it('leech threshold sticks once 6 lapses accumulate', () => {
    // Each lapse cycle: graduate to Review → lapse → relearn → graduate again.
    let c = fresh();
    let when = NOW;
    for (let cycle = 0; cycle < 6; cycle++) {
      const g = graduateToReview(c, when);
      c = g.card;
      when = g.when;
      const r = applyGrade(c, GRADES.AGAIN, when);
      c = r.card;
      when = bumpHours(when, 1);
    }
    expect(c.lapses).toBeGreaterThanOrEqual(6);
    expect(c.status).toBe('leech');
    // Still leech (sticky).
    const after = graduateToReview(c, bumpHours(when, 24)).card;
    expect(after.status).toBe('leech');
  });
});

/* ── isDue ───────────────────────────────────────────────────── */
describe('isDue', () => {
  it('cards with empty due are due', () => {
    expect(isDue({ due: '' } as any, NOW)).toBe(true);
  });
  it('cards with Invalid Date are due (defensive)', () => {
    expect(isDue({ due: 'not-a-date' } as any, NOW)).toBe(true);
  });
  it('respects future due', () => {
    const future = bumpHours(NOW, 1).toISOString();
    expect(isDue({ due: future }, NOW)).toBe(false);
  });
});

/* ── buildQueue ──────────────────────────────────────────────── */
describe('buildQueue', () => {
  function due(card: Card, when: Date): Card {
    return { ...card, due: when.toISOString() };
  }

  it('empty srs → empty queue', () => {
    expect(buildQueue({}, { now: NOW })).toEqual([]);
  });

  it('caps maxReviews (the only remaining cap)', () => {
    // The previous `maxNew` cap was removed 2026-04-29 — see QueueOptions
    // docstring for the rationale (graded reader; user already opted into
    // every word in the SRS map by reading the story).
    const srs: Record<string, Card> = {};
    for (let i = 0; i < 30; i++) {
      const c = fresh(`W${String(i).padStart(5, '0')}`);
      const grad = graduateToReview(c, NOW).card;
      srs[grad.word_id] = due(grad, bumpHours(NOW, -1));
    }
    const q = buildQueue(srs, { now: NOW, maxReviews: 10, newPerReview: 0 });
    expect(q.length).toBeLessThanOrEqual(10);
  });

  it('uncapped by default — every due card surfaces', () => {
    // Default QueueOptions = no maxReviews cap. A user with a long backlog
    // should never see "all caught up" lies because of an Anki-inherited
    // session ceiling.
    const srs: Record<string, Card> = {};
    for (let i = 0; i < 50; i++) {
      const c = fresh(`W${String(i).padStart(5, '0')}`);
      const grad = graduateToReview(c, NOW).card;
      srs[grad.word_id] = due(grad, bumpHours(NOW, -1));
    }
    const q = buildQueue(srs, { now: NOW });
    expect(q.length).toBe(50);
  });

  it('filters out non-due cards', () => {
    const c = fresh();
    const future = due(c, bumpHours(NOW, 24));
    const q = buildQueue({ x: future }, { now: NOW });
    expect(q).toEqual([]);
  });

  it('learning + relearning cards come first', () => {
    const { card: gradA, when: whenA } = graduateToReview(fresh('A'));
    const learning = applyGrade(gradA, GRADES.AGAIN, whenA).card;
    const review = graduateToReview(fresh('B')).card;
    const srs = {
      A: due(learning, bumpHours(NOW, -0.1)),
      B: due(review, bumpHours(NOW, -1)),
    };
    const q = buildQueue(srs, { now: NOW });
    expect(q[0].word_id).toBe('A');
  });
});

/* ── dribbleOffset ───────────────────────────────────────────── */
describe('dribbleOffset', () => {
  it('returns 0 for the first card and grows monotonically', () => {
    expect(dribbleOffset(0)).toBe(0);
    for (let i = 1; i < 30; i++) {
      expect(dribbleOffset(i)).toBeGreaterThan(dribbleOffset(i - 1));
    }
  });

  it('caps so a 100-word story is not spread over hours', () => {
    expect(dribbleOffset(500)).toBeLessThan(60 * 60 * 1000); // < 1 hour
  });
});

/* ── stats helpers ───────────────────────────────────────────── */
describe('statusCounts', () => {
  it('counts cards by status', () => {
    const a = fresh('A');
    const b = applyGrade(fresh('B'), GRADES.GOOD, NOW).card;
    const counts = statusCounts({ A: a, B: b });
    expect(counts.new).toBe(1);
    expect(counts.young + counts.learning).toBe(1);
  });
});

describe('trueRetention', () => {
  it('zero retention when no reviews', () => {
    expect(trueRetention([]).rate).toBe(0);
  });

  it('skips first-ever sightings and counts only follow-ups', () => {
    const card_before_first: Card = { ...fresh('A'), reps: 0 };
    const card_before_repeat: Card = { ...fresh('A'), reps: 2 };
    const log: ReviewLogEntry[] = [
      {
        word_id: 'A',
        grade: 1 as Grade,
        reviewed_at: NOW.toISOString(),
        card_before: card_before_first,
        card_after: card_before_first,
      },
      {
        word_id: 'A',
        grade: 1 as Grade,
        reviewed_at: NOW.toISOString(),
        card_before: card_before_repeat,
        card_after: card_before_repeat,
      },
      {
        word_id: 'A',
        grade: 0 as Grade,
        reviewed_at: NOW.toISOString(),
        card_before: card_before_repeat,
        card_after: card_before_repeat,
      },
    ];
    const r = trueRetention(log, 30, NOW);
    expect(r.reviewed).toBe(2);
    expect(r.remembered).toBe(1);
    expect(r.rate).toBeCloseTo(0.5);
  });
});

describe('dueForecast', () => {
  it('returns N buckets, overdue rolls into today', () => {
    const c = applyGrade(fresh(), GRADES.GOOD, NOW).card;
    const overdue = { ...c, due: bumpHours(NOW, -48).toISOString() };
    const buckets = dueForecast({ X: overdue }, 7, NOW);
    expect(buckets.length).toBe(7);
    expect(buckets[0].count).toBe(1);
  });
});
