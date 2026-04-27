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

  // Word popup is open
  const popup = page.locator('div.popup[role="dialog"]');
  await expect(popup).toBeVisible();
  // Sanity check: popup-content gets at least one child once the word
  // record has loaded from the shard. The "Loading…" placeholder is a
  // <p class="empty-state">; once loaded it becomes either a WordPopup
  // (.popup-word) or a GrammarPopup (.popup-grammar-title) — both have
  // distinctive text.
  const popupBody = popup.locator('.popup-content');
  await expect(popupBody).toBeVisible();
  // Wait until the popup is no longer in the loading placeholder state.
  // .popup-word | .popup-grammar-title appear after lazy load resolves.
  await expect(async () => {
    const text = await popupBody.innerText();
    if (text.includes('Loading…')) throw new Error('still loading');
  }).toPass({ timeout: 10_000 });

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
    await goodBtn.click();
    // Either another card or session complete
    await expect(page.locator('#review-container')).toBeVisible();
  }
});

test('library navigation: open story 2', async ({ page }) => {
  await page.goto('/');
  await page.locator('a.nav-btn[data-view="library"]').click();
  await expect(page).toHaveURL(/\/library/);

  // Wait for cards to render (virtualized — only the first slice).
  const card = page
    .locator('button.story-card', { hasText: 'Story 2' })
    .first();
  await card.waitFor({ state: 'visible', timeout: 15_000 });
  await card.click();
  await expect(page).toHaveURL(/\/read\?story=2/);
  await expect(page.locator('.story-id-label')).toHaveText('Story 2');
});

test('vocab view loads and search filters', async ({ page }) => {
  await page.goto('/');
  await page.locator('a.nav-btn[data-view="vocab"]').click();
  await expect(page).toHaveURL(/\/vocab/);

  // Stats visible
  const stats = page.locator('.vocab-stats');
  await expect(stats).toBeVisible();

  // Type a search that should filter results
  const search = page.locator('input.vocab-search');
  await search.fill('zzz_no_match_xyzzy');
  await expect(page.locator('.empty-state')).toBeVisible();

  await search.fill('');
  // At least one row should reappear
  await expect(page.locator('button.vocab-row').first()).toBeVisible({ timeout: 5_000 });
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
