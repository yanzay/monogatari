<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';
  import { loadManifest } from '$lib/data/corpus';
  import { learner } from '$lib/state/learner.svelte';
  import type { StoryManifest } from '$lib/data/types';

  let manifest = $state<StoryManifest | null>(null);
  let loadError = $state<string | null>(null);

  onMount(async () => {
    try {
      manifest = await loadManifest();
    } catch (e) {
      console.error(e);
      loadError = 'Could not load library. Please reload.';
    }
  });

  function open(id: number) {
    goto(`${base}/read?story=${id}`);
  }

  function readingMin(entry: { n_content_tokens?: number; n_sentences?: number }) {
    const tokens = entry.n_content_tokens ?? (entry.n_sentences ?? 0) * 6;
    return Math.max(1, Math.round(tokens / 25));
  }
</script>

<div id="view-library" class="view active">
  <h2 class="library-heading">Library</h2>
  <p class="library-sub">
    Pick a story to read. Each card shows the title, an estimated reading time, and your progress.
  </p>
  {#if loadError}
    <p class="empty-state">{loadError}</p>
  {:else if !manifest}
    <p class="empty-state">Loading library…</p>
  {:else if !manifest.stories.length}
    <p class="empty-state">No stories yet.</p>
  {:else}
    <div id="library-grid" class="library-grid">
      {#each manifest.stories as entry (entry.story_id)}
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
