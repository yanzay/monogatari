/**
 * Pure helpers that decide whether the learner can open a given story.
 *
 * Rule (2026-04-29): the corpus is a strict graded reader. Each story
 * builds on vocab + grammar from the previous one. Skipping ahead is
 * counter-productive — the learner would hit unfamiliar words before
 * the cards backing them are saved for review.
 *
 * A story is UNLOCKED iff:
 *   - it's story 1 (the seed; nothing precedes it), OR
 *   - story (id - 1) is marked `completed: true` in story_progress.
 *
 * Note: we deliberately do NOT treat the learner's `current_story`
 * field as an unlock — that field is only the bookmark of the LAST
 * opened story, not a proof of completion. Reaching story 5 doesn't
 * mean stories 2/3/4 were finished, only that the URL was visited.
 */

export type StoryProgressMap = Record<string, { completed: boolean } | null | undefined>;

/**
 * Returns true if the learner is permitted to open the given story.
 */
export function isStoryUnlocked(
  storyId: number,
  progress: StoryProgressMap | undefined | null,
): boolean {
  if (!Number.isFinite(storyId) || storyId <= 0) return false;
  if (storyId === 1) return true;
  if (!progress) return false;
  const prev = progress[String(storyId - 1)];
  return !!prev && prev.completed === true;
}

/**
 * Returns the highest story id the learner is currently allowed to
 * open (= first incomplete story from id=1 upward, capped at
 * `totalStories`). For a brand-new user this returns 1; once they
 * complete story 1 it returns 2; etc.
 *
 * If the learner has completed every story up to the cap, returns the
 * cap (the read view should still let them re-read).
 */
export function highestUnlockedStory(
  progress: StoryProgressMap | undefined | null,
  totalStories: number,
): number {
  if (!Number.isFinite(totalStories) || totalStories <= 0) return 1;
  for (let i = 1; i <= totalStories; i += 1) {
    const entry = progress?.[String(i)];
    if (!entry || entry.completed !== true) return i;
  }
  return totalStories;
}

/**
 * Returns the story id immediately after the last completed story,
 * useful for marking a "Next up" badge. Same as highestUnlockedStory
 * for any non-completed user; differs only in the all-completed case
 * where this returns totalStories + 1 (i.e. nothing, "all done").
 */
export function nextStoryToRead(
  progress: StoryProgressMap | undefined | null,
  totalStories: number,
): number | null {
  if (!Number.isFinite(totalStories) || totalStories <= 0) return null;
  for (let i = 1; i <= totalStories; i += 1) {
    const entry = progress?.[String(i)];
    if (!entry || entry.completed !== true) return i;
  }
  return null; // all done
}
