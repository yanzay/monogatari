import { test, expect } from '@playwright/test';

/**
 * Happy-path E2E:
 *
 *   load → read view (story 1) → click a clickable token → word popup
 *   appears → close popup → mark as read → review view shows queue →
 *   reveal → grade Good → next-card flow.
 *
 * Hash router means we navigate via the in-app links, not URL pushes.
 */
test('happy path: read → popup → mark as read → review → grade', async ({ page }) => {
  await page.goto('/');
  // Boot finishes when a clickable token shows up — that requires vocab + manifest + story_1 all loaded.
  await expect(page.locator('h1.story-title')).toBeVisible({ timeout: 15_000 });

  // Click the first clickable token in the story body.
  const firstClickable = page
    .locator('#sentences-container button.token.clickable')
    .first();
  await firstClickable.click();

  // Word popup is open. We MUST get a word/grammar popup here, NOT a
  // sentence popup — clicking a token should not bubble up to the
  // parent .sentence-wrap. (Regression guard for the bug fixed in
  // commit 'fix(reader): stop click propagation on tokens'.)
  const popup = page.locator('div.popup[role="dialog"]');
  await expect(popup).toBeVisible();
  const popupBody = popup.locator('.popup-content');
  await expect(popupBody).toBeVisible();
  // Wait until the popup is out of the "Loading…" placeholder state.
  await expect(async () => {
    const text = await popupBody.innerText();
    if (text.includes('Loading…')) throw new Error('still loading');
  }).toPass({ timeout: 10_000 });
  // Distinguish: WordPopup renders .popup-word, GrammarPopup renders
  // .popup-grammar-title. SentencePopup renders .popup-sentence-jp —
  // which would mean the click bubbled to the sentence wrap.
  await expect(popup.locator('.popup-sentence-jp')).toHaveCount(0);
  await expect(
    popup.locator('.popup-word, .popup-grammar-title'),
  ).toBeVisible();

  // Escape closes it and returns focus
  await page.keyboard.press('Escape');
  await expect(popup).toBeHidden();

  // Mark as read
  const markBtn = page.locator('#btn-mark-read');
  if (await markBtn.isEnabled()) {
    await markBtn.click();
    await expect(markBtn).toBeDisabled();
  }

  // Review view
  await page.locator('a.nav-btn[data-view="review"]').click();
  await expect(page).toHaveURL(/\/review/);

  // Either we have a queue (Show answer button) or empty state
  const reveal = page.locator('button.btn-reveal');
  const empty = page.locator('.empty-state', { hasText: 'Nothing due' });
  await Promise.race([
    reveal.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => null),
    empty.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => null),
  ]);

  if (await reveal.isVisible()) {
    await reveal.click();
    const goodBtn = page.locator('.grade-btn', { hasText: 'Good' });
    await expect(goodBtn).toBeVisible();
    // Verify the 'Hard' button is gone (FSRS rewrite dropped it).
    await expect(page.locator('.grade-btn', { hasText: 'Hard' })).toHaveCount(0);
    await goodBtn.click();
    // Either another card or session complete
    await expect(page.locator('#review-container')).toBeVisible();
  }
});

test('stats view loads', async ({ page }) => {
  await page.goto('/');
  await page.locator('a.nav-btn[data-view="stats"]').click();
  await expect(page).toHaveURL(/\/stats/);
  await expect(page.locator('.library-heading', { hasText: 'Stats' })).toBeVisible();
  // Settings sliders/inputs exist
  await expect(page.locator('input[type="range"]').first()).toBeVisible();
});

test('library navigation: open story 1 (always unlocked seed)', async ({ page }) => {
  // Per the strict graded-reader unlock policy (2026-04-29), a fresh
  // learner has only story 1 unlocked; story N≥2 is locked until
  // story N-1 is marked completed. We exercise the library-card →
  // /read flow against story 1 because it is the only card that any
  // visitor (fresh CI run or returning user) can be guaranteed to
  // have unlocked. The previous version of this test clicked Story 2
  // — that card is disabled for a fresh user and the click would be
  // intercepted, breaking CI.
  await page.goto('/');
  await page.locator('a.nav-btn[data-view="library"]').click();
  await expect(page).toHaveURL(/\/library/);

  // Wait for cards to render (virtualized — only the first slice).
  const card = page
    .locator('button.story-card', { hasText: 'Story 1' })
    .first();
  await card.waitFor({ state: 'visible', timeout: 15_000 });
  // Sanity: story 1 is the seed and must always be enabled.
  await expect(card).toBeEnabled();
  await card.click();
  await expect(page).toHaveURL(/\/read\?story=1/);
  await expect(page.locator('.story-id-label')).toHaveText('Story 1');
});

test('vocab view loads and search filters', async ({ page }) => {
  // The vocab view now defaults to "learner's known words only" (the
  // entire corpus dictionary is overwhelming for a fresh user). The
  // page renders an empty-state CTA "show all N words in the corpus"
  // for fresh visitors; clicking that CTA flips the showAll toggle
  // and is the user-facing path we should exercise. We don't poke
  // the underlying checkbox directly because Svelte-5 hydration
  // races make the input flaky to target by selector.
  await page.goto('/');
  await page.locator('a.nav-btn[data-view="vocab"]').click();
  await expect(page).toHaveURL(/\/vocab/);

  // Stats render unconditionally.
  await expect(page.locator('.vocab-stats')).toBeVisible();

  // Wait for the vocab index to finish loading. For a fresh learner
  // (zero known words), this surfaces the "show all" CTA in an
  // empty-state. For a returning learner with known words, the rows
  // render directly. Handle both paths so the test is portable
  // across environments.
  const showAllCta = page.locator('button.link-button', { hasText: /show all/i });
  const anyRow = page.locator('button.vocab-row').first();
  await Promise.race([
    showAllCta.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => null),
    anyRow.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => null),
  ]);
  if (await showAllCta.isVisible().catch(() => false)) {
    await showAllCta.click();
  }
  // Either way, rows should now be visible (full corpus is non-empty).
  await expect(anyRow).toBeVisible({ timeout: 10_000 });

  // Type a search that should filter to nothing.
  const search = page.locator('input.vocab-search');
  await search.fill('zzz_no_match_xyzzy');
  await expect(page.locator('.empty-state')).toBeVisible();

  await search.fill('');
  // At least one row should reappear.
  await expect(anyRow).toBeVisible({ timeout: 5_000 });
});

test('grammar view shows entries with prebuilt examples', async ({ page }) => {
  await page.goto('/');
  await page.locator('a.nav-btn[data-view="grammar"]').click();
  await expect(page).toHaveURL(/\/grammar/);

  // First grammar item header
  const firstHeader = page.locator('button.grammar-item-header').first();
  await expect(firstHeader).toBeVisible({ timeout: 10_000 });
  await firstHeader.click();
  // Body shows up
  await expect(page.locator('.grammar-item-body').first()).toBeVisible();
});
