import { describe, it, expect } from 'vitest';
import { applyGrade, isDue, migrateCard, newCard, GRADES } from '$lib/state/srs';

const NOW = new Date('2026-04-27T12:00:00Z');

function fresh() {
  return newCard({ word_id: 'W00001', story_id: 1, context_sentence_idx: 0, now: NOW });
}

describe('newCard', () => {
  it('creates a new card with sensible defaults', () => {
    const c = fresh();
    expect(c.status).toBe('new');
    expect(c.interval_min).toBe(0);
    expect(c.ease).toBe(2.5);
    expect(c.reps).toBe(0);
    expect(c.lapses).toBe(0);
    expect(new Date(c.due).getTime()).toBe(NOW.getTime());
  });
});

describe('applyGrade', () => {
  it('AGAIN sets 10-min interval and bumps lapses', () => {
    const c = applyGrade(fresh(), GRADES.AGAIN, NOW);
    expect(c.interval_min).toBe(10);
    expect(c.lapses).toBe(1);
    expect(c.status).toBe('relearning');
    expect(c.ease).toBeCloseTo(2.3);
  });

  it('GOOD on a new card → 1 day interval, status=young', () => {
    const c = applyGrade(fresh(), GRADES.GOOD, NOW);
    expect(c.interval_min).toBe(1440);
    expect(c.reps).toBe(1);
    expect(c.status).toBe('young');
  });

  it('HARD after AGAIN does NOT collapse to a 1-day interval (legacy bug)', () => {
    let c = applyGrade(fresh(), GRADES.AGAIN, NOW);
    c = applyGrade(c, GRADES.HARD, NOW);
    // Interval was 10 min, ×1.2 = 12 min, floored to ≥10. NOT 1 day.
    expect(c.interval_min).toBeGreaterThanOrEqual(10);
    expect(c.interval_min).toBeLessThan(60);
    expect(c.status).toBe('learning');
  });

  it('EASY chain promotes through young to mature', () => {
    let c = fresh();
    c = applyGrade(c, GRADES.GOOD, NOW); // 1 day → young
    expect(c.status).toBe('young');
    c = applyGrade(c, GRADES.EASY, NOW); // 3d × 1.3 = ~4d → still young
    expect(c.status).toBe('young');
    // Force several Good reviews to escalate past 21 days
    for (let i = 0; i < 6; i++) c = applyGrade(c, GRADES.GOOD, NOW);
    expect(c.status).toBe('mature');
    expect(c.interval_min).toBeGreaterThanOrEqual(21 * 1440);
  });

  it('ease never goes below 1.3 or above 4.0', () => {
    let c = fresh();
    for (let i = 0; i < 50; i++) c = applyGrade(c, GRADES.AGAIN, NOW);
    expect(c.ease).toBeGreaterThanOrEqual(1.3);
    c = fresh();
    for (let i = 0; i < 50; i++) c = applyGrade(c, GRADES.EASY, NOW);
    expect(c.ease).toBeLessThanOrEqual(4.0);
  });

  it('leech threshold sticks once 6 lapses accumulate', () => {
    let c = fresh();
    for (let i = 0; i < 6; i++) c = applyGrade(c, GRADES.AGAIN, NOW);
    expect(c.status).toBe('leech');
    c = applyGrade(c, GRADES.GOOD, NOW);
    expect(c.status).toBe('leech'); // sticky
  });

  it('due date moves forward by interval_min', () => {
    const c = applyGrade(fresh(), GRADES.GOOD, NOW);
    const due = new Date(c.due).getTime();
    expect(due - NOW.getTime()).toBe(c.interval_min * 60 * 1000);
  });
});

describe('isDue', () => {
  it('cards with no due are always due', () => {
    expect(isDue({ due: '' } as any, NOW)).toBe(true);
  });

  it('cards with Invalid Date are treated as due (defensive)', () => {
    expect(isDue({ due: 'not-a-date' } as any, NOW)).toBe(true);
  });

  it('respects future due dates', () => {
    const future = new Date(NOW.getTime() + 3600_000).toISOString();
    expect(isDue({ due: future }, NOW)).toBe(false);
  });
});

describe('migrateCard', () => {
  it('converts legacy interval_days → interval_min', () => {
    const legacy = {
      word_id: 'W00042',
      interval_days: 3,
      ease: 2.5,
      reps: 2,
      lapses: 0,
      status: 'young',
      due: '2026-04-27T00:00:00Z',
      first_learned_story: 5,
      context_story: 5,
      context_sentence_idx: 0,
    };
    const m = migrateCard(legacy);
    expect(m.interval_min).toBe(3 * 1440);
    expect(m.status).toBe('young');
  });

  it('passes through already-migrated cards unchanged', () => {
    const c = fresh();
    const m = migrateCard(c);
    expect(m).toEqual(c);
  });

  it('clamps unknown status to new', () => {
    const m = migrateCard({ word_id: 'X', status: 'wat', interval_days: 0 });
    expect(m.status).toBe('new');
  });
});
