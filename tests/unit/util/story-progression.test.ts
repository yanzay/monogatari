/**
 * Tests for the strict-graded-reader unlock policy. The library card
 * lock state and the read view's deep-link guard both depend on these
 * three helpers; they're kept tiny on purpose so the policy is easy
 * to reason about and audit.
 */
import { describe, it, expect } from 'vitest';
import {
  isStoryUnlocked,
  highestUnlockedStory,
  nextStoryToRead,
} from '../../../src/lib/util/story-progression';

const completed = (...ids: number[]) =>
  Object.fromEntries(ids.map((i) => [String(i), { completed: true }]));

describe('isStoryUnlocked', () => {
  it('story 1 is always unlocked, even with no progress', () => {
    expect(isStoryUnlocked(1, undefined)).toBe(true);
    expect(isStoryUnlocked(1, null)).toBe(true);
    expect(isStoryUnlocked(1, {})).toBe(true);
    expect(isStoryUnlocked(1, completed())).toBe(true);
  });

  it('story 2 is locked until story 1 is completed', () => {
    expect(isStoryUnlocked(2, {})).toBe(false);
    expect(isStoryUnlocked(2, completed(1))).toBe(true);
  });

  it('story N is locked until story N-1 is completed', () => {
    expect(isStoryUnlocked(5, completed(1, 2, 3))).toBe(false);
    expect(isStoryUnlocked(5, completed(1, 2, 3, 4))).toBe(true);
  });

  it('a partial-progress entry without completed=true does NOT unlock the next story', () => {
    expect(isStoryUnlocked(3, { '2': { completed: false } })).toBe(false);
  });

  it('null entries are treated as "not completed"', () => {
    expect(isStoryUnlocked(3, { '2': null } as any)).toBe(false);
  });

  it('non-positive or non-finite ids are locked', () => {
    expect(isStoryUnlocked(0, completed(1, 2, 3))).toBe(false);
    expect(isStoryUnlocked(-1, completed(1, 2, 3))).toBe(false);
    expect(isStoryUnlocked(NaN, completed(1, 2, 3))).toBe(false);
    expect(isStoryUnlocked(Infinity, completed(1, 2, 3))).toBe(false);
  });

  it('does NOT auto-unlock a later story just because earlier ones are complete', () => {
    // Sanity: completing 1 and 2 unlocks 3 — not 5.
    const p = completed(1, 2);
    expect(isStoryUnlocked(3, p)).toBe(true);
    expect(isStoryUnlocked(5, p)).toBe(false);
  });

  it('current_story bookmark does NOT count as completion', () => {
    // Reaching story 5 via the URL doesn't unlock story 6 — only
    // pressing "save for review" on story 5 does. This guards
    // against a learner deep-linking past unread material.
    expect(isStoryUnlocked(6, completed(1, 2, 3, 4))).toBe(false);
  });
});

describe('highestUnlockedStory', () => {
  it('returns 1 for a brand-new user', () => {
    expect(highestUnlockedStory(undefined, 10)).toBe(1);
    expect(highestUnlockedStory({}, 10)).toBe(1);
  });

  it('returns 2 once story 1 is completed', () => {
    expect(highestUnlockedStory(completed(1), 10)).toBe(2);
  });

  it('returns the first incomplete story regardless of out-of-order completions', () => {
    // The learner completed 1 and 2 normally, but ALSO somehow
    // completed 5 (e.g. from a partial backup). The unlock should
    // still walk linearly: highest unlocked = 3 (first gap).
    expect(highestUnlockedStory(completed(1, 2, 5), 10)).toBe(3);
  });

  it('returns totalStories when EVERY story is complete', () => {
    expect(highestUnlockedStory(completed(1, 2, 3), 3)).toBe(3);
  });

  it('returns 1 for an invalid totalStories', () => {
    expect(highestUnlockedStory(completed(1, 2), 0)).toBe(1);
    expect(highestUnlockedStory(completed(1, 2), -5)).toBe(1);
    expect(highestUnlockedStory(completed(1, 2), NaN)).toBe(1);
  });
});

describe('nextStoryToRead', () => {
  it('returns 1 for a brand-new user', () => {
    expect(nextStoryToRead({}, 10)).toBe(1);
  });

  it('returns 2 once story 1 is done', () => {
    expect(nextStoryToRead(completed(1), 10)).toBe(2);
  });

  it('returns null once everything is done', () => {
    expect(nextStoryToRead(completed(1, 2, 3, 4, 5), 5)).toBeNull();
  });

  it('returns the first gap', () => {
    expect(nextStoryToRead(completed(1, 2, 5), 10)).toBe(3);
  });

  it('returns null for invalid totalStories', () => {
    expect(nextStoryToRead(completed(1, 2), 0)).toBeNull();
  });
});
