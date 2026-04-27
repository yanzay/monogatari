<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';
  import {
    loadManifest,
    loadManifestPage,
    manifestPageCount,
    manifestStoryCount,
  } from '$lib/data/corpus';
  import { learner } from '$lib/state/learner.svelte';
  import VList from '$lib/ui/VList.svelte';
  import type { StoryManifestEntry } from '$lib/data/types';

  let pageCount = $state(0);
  let totalStories = $state(0);
  let loadError = $state<string | null>(null);

  // We render one page at a time; user can flip pages and the rows are
  // virtualized within each page.
  let currentPage = $state(1);
  let entries = $state<StoryManifestEntry[]>([]);
  let entriesLoading = $state(true);

  onMount(async () => {
    try {
      await loadManifest();
      [pageCount, totalStories] = await Promise.all([manifestPageCount(), manifestStoryCount()]);
      // Default to the page that contains the learner's current story.
      const cur = learner.state.current_story ?? 1;
      const guess = Math.max(1, Math.ceil(cur / 50));
      currentPage = Math.min(Math.max(1, guess), pageCount);
    } catch (e) {
      console.error(e);
      loadError = 'Could not load library. Please reload.';
    }
  });

  $effect(() => {
    const p = currentPage;
    if (!pageCount) return;
    entriesLoading = true;
    loadManifestPage(p).then((payload) => {
      if (payload && currentPage === p) {
        entries = payload.stories;
        entriesLoading = false;
      }
    });
  });

  function open(id: number) {
    goto(`${base}/read?story=${id}`);
  }

  function readingMin(entry: StoryManifestEntry) {
    const tokens = entry.n_content_tokens ?? (entry.n_sentences ?? 0) * 6;
    return Math.max(1, Math.round(tokens / 25));
  }

  let viewportHeight = $state(600);
  $effect(() => {
    if (typeof window === 'undefined') return;
    const compute = () => {
      // Subtract approx header/filter heights so the list fills the rest.
      viewportHeight = Math.max(360, window.innerHeight - 240);
    };
    compute();
    window.addEventListener('resize', compute);
    return () => window.removeEventListener('resize', compute);
  });

  // Virtualize only when the page is genuinely large. At <=200 entries
  // a plain CSS grid is faster, looks correct (multiple columns), and
  // avoids the absolutely-positioned-row layout shenanigans the VList
  // does. The grid is still server-friendly: pagination already caps
  // each page at 50, so this almost always uses the grid path.
  let useVirtualization = $derived(entries.length > 200);
</script>

<div id="view-library" class="view active">
  <h2 class="library-heading">Library</h2>
  <p class="library-sub">
    {totalStories} stories. Each card shows the title, an estimated reading time, and your progress.
  </p>

  {#if pageCount > 1}
    <div class="lib-pager" style="display:flex;gap:0.5rem;align-items:center;margin-bottom:0.6rem;">
      <button
        class="story-nav-btn"
        disabled={currentPage <= 1}
        onclick={() => (currentPage -= 1)}
      >← Prev page</button>
      <span style="opacity:0.7;">Page {currentPage} of {pageCount}</span>
      <button
        class="story-nav-btn"
        disabled={currentPage >= pageCount}
        onclick={() => (currentPage += 1)}
      >Next page →</button>
    </div>
  {/if}

  {#if loadError}
    <p class="empty-state">{loadError}</p>
  {:else if !pageCount}
    <p class="empty-state">Loading library…</p>
  {:else if entriesLoading}
    <p class="empty-state">Loading page…</p>
  {:else if !entries.length}
    <p class="empty-state">No stories on this page.</p>
  {:else if useVirtualization}
    <VList items={entries} itemHeight={140} height={viewportHeight}>
      {#snippet children(entry)}
        {@const progress = learner.state.story_progress?.[String(entry.story_id)]}
        {@const completed = !!progress?.completed}
        {@const isCurrent = entry.story_id === learner.state.current_story}
        <button
          class="story-card"
          class:current={isCurrent}
          style="height:128px;width:100%;"
          onclick={() => open(entry.story_id)}
          aria-label={`Open story ${entry.story_id}: ${entry.title_en ?? ''}`}
        >
          <span class="story-card-id">Story {entry.story_id}</span>
          <div class="story-card-title-jp" lang="ja">
            {entry.title_jp || `Story ${entry.story_id}`}
          </div>
          <div class="story-card-title-en">{entry.title_en || ''}</div>
          <div class="story-card-meta">
            <span>{entry.n_sentences ?? 0} sentences · ~{readingMin(entry)} min</span>
            <span class="story-card-badge" class:done={completed}>
              {completed ? '✓ done' : isCurrent ? 'reading' : 'unread'}
            </span>
          </div>
        </button>
      {/snippet}
    </VList>
  {:else}
    <div class="library-grid">
      {#each entries as entry (entry.story_id)}
        {@const progress = learner.state.story_progress?.[String(entry.story_id)]}
        {@const completed = !!progress?.completed}
        {@const isCurrent = entry.story_id === learner.state.current_story}
        <button
          class="story-card"
          class:current={isCurrent}
          onclick={() => open(entry.story_id)}
          aria-label={`Open story ${entry.story_id}: ${entry.title_en ?? ''}`}
        >
          <span class="story-card-id">Story {entry.story_id}</span>
          <div class="story-card-title-jp" lang="ja">
            {entry.title_jp || `Story ${entry.story_id}`}
          </div>
          <div class="story-card-title-en">{entry.title_en || ''}</div>
          <div class="story-card-meta">
            <span>{entry.n_sentences ?? 0} sentences · ~{readingMin(entry)} min</span>
            <span class="story-card-badge" class:done={completed}>
              {completed ? '✓ done' : isCurrent ? 'reading' : 'unread'}
            </span>
          </div>
        </button>
      {/each}
    </div>
  {/if}
</div>
