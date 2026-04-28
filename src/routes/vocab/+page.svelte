<script lang="ts">
  import { onMount } from 'svelte';
  import { loadVocabIndex } from '$lib/data/corpus';
  import { learner } from '$lib/state/learner.svelte';
  import { popup } from '$lib/state/popup.svelte';
  import VList from '$lib/ui/VList.svelte';
  import { isKnownWord } from '$lib/util/known-filters';
  import type { VocabIndex, VocabIndexRow } from '$lib/data/types';

  let vocabIndex = $state<VocabIndex | null>(null);
  let q = $state('');
  let statusFilter = $state<'all' | 'new' | 'learning' | 'young' | 'mature' | 'leech'>('all');
  let storyFilter = $state<'all' | string>('all');
  // Default to the learner's known words only — the entire corpus
  // dictionary is overwhelming and most rows are unactionable.
  // Toggle 'Show all' for the full catalog.
  let showAll = $state(false);

  onMount(async () => {
    vocabIndex = await loadVocabIndex();
  });

  let allWords = $derived<VocabIndexRow[]>(vocabIndex?.words ?? []);
  let words = $derived<VocabIndexRow[]>(
    showAll ? allWords : allWords.filter((w) => isKnownWord(w, learner.state.srs)),
  );

  let stats = $derived.by(() => {
    const s = { total: words.length, new: 0, learning: 0, young: 0, mature: 0, leech: 0 };
    for (const w of words) {
      const srs = learner.state.srs?.[w.id];
      const st = (srs?.status ?? 'new') as keyof typeof s;
      if (st in s) (s as any)[st] += 1;
      else s.new += 1;
    }
    return s;
  });

  let stories = $derived(
    Array.from(new Set(words.map((w) => String(w.first_story ?? '')).filter(Boolean))).sort(
      (a, b) => Number(a) - Number(b),
    ),
  );

  let filtered = $derived.by(() => {
    const ql = q.toLowerCase().trim();
    return words.filter((w) => {
      const srs = learner.state.srs?.[w.id];
      const wStatus = (srs?.status ?? 'new') as string;
      if (statusFilter !== 'all' && wStatus !== statusFilter) return false;
      if (storyFilter !== 'all' && String(w.first_story) !== storyFilter) return false;
      if (
        ql &&
        !(
          w.surface.includes(ql) ||
          w.kana.includes(ql) ||
          w.reading.toLowerCase().includes(ql) ||
          w.short_meaning.toLowerCase().includes(ql)
        )
      )
        return false;
      return true;
    });
  });

  function openWord(w: VocabIndexRow) {
    popup.openWord(w.id, undefined);
  }

  let viewportHeight = $state(600);
  $effect(() => {
    if (typeof window === 'undefined') return;
    const compute = () => (viewportHeight = Math.max(360, window.innerHeight - 280));
    compute();
    window.addEventListener('resize', compute);
    return () => window.removeEventListener('resize', compute);
  });

  // Plain DOM rendering until the list gets genuinely large. Below
  // 300 rows it's faster + visually correct; above we virtualize so
  // the DOM doesn't blow up at thousands-of-words scale.
  let useVirtualization = $derived(filtered.length > 300);
</script>

<div id="view-vocab" class="view active">
  <div class="vocab-stats">
    {#each [['Total', stats.total], ['New', stats.new], ['Learning', stats.learning], ['Young', stats.young], ['Mature', stats.mature]] as [label, n] (label)}
      <div class="stat-card">
        <span class="stat-number">{n}</span>
        <span class="stat-label">{label}</span>
      </div>
    {/each}
  </div>

  <div class="vocab-filters">
    <input
      type="search"
      class="vocab-search"
      placeholder="Search…"
      bind:value={q}
      aria-label="Search vocabulary"
    />
    <select class="vocab-select" bind:value={statusFilter} aria-label="Filter by status">
      <option value="all">All statuses</option>
      <option value="new">New</option>
      <option value="learning">Learning</option>
      <option value="young">Young</option>
      <option value="mature">Mature</option>
      <option value="leech">Leech</option>
    </select>
    <select class="vocab-select" bind:value={storyFilter} aria-label="Filter by story">
      <option value="all">All stories</option>
      {#each stories as sid (sid)}
        <option value={sid}>Story {sid}</option>
      {/each}
    </select>
    <label class="vocab-show-all" title="Include words you haven't started learning yet">
      <input type="checkbox" bind:checked={showAll} />
      <span>Show all</span>
    </label>
  </div>

  {#if !showAll && allWords.length > 0 && words.length === 0}
    <p class="empty-state">
      You haven't started learning any words yet. Read a story and press
      "save new words for review" to start, or
      <button class="link-button" type="button" onclick={() => (showAll = true)}>
        show all {allWords.length} words in the corpus
      </button>.
    </p>
  {/if}

  {#if !vocabIndex}
    <p class="empty-state">Loading…</p>
  {:else if !filtered.length && words.length > 0}
    <p class="empty-state">No vocabulary matches the current filters.</p>
  {:else if !filtered.length && words.length === 0 && showAll}
    <p class="empty-state">No vocabulary in the corpus yet.</p>
  {:else if useVirtualization}
    <VList items={filtered} itemHeight={56} height={viewportHeight}>
      {#snippet children(word)}
        {@const srs = learner.state.srs?.[word.id]}
        {@const status = srs?.status ?? 'new'}
        <button
          class="vocab-row"
          style="height:52px;width:100%;"
          onclick={() => openWord(word)}
        >
          <span class="vocab-row-jp" lang="ja">{word.surface}</span>
          <span class="vocab-row-reading">{word.reading}</span>
          <span class="vocab-row-meaning">{word.short_meaning}</span>
          <span class="status-dot" data-status={status} title={status}></span>
        </button>
      {/snippet}
    </VList>
  {:else}
    <div class="vocab-list">
      {#each filtered as word (word.id)}
        {@const srs = learner.state.srs?.[word.id]}
        {@const status = srs?.status ?? 'new'}
        <button class="vocab-row" onclick={() => openWord(word)}>
          <span class="vocab-row-jp" lang="ja">{word.surface}</span>
          <span class="vocab-row-reading">{word.reading}</span>
          <span class="vocab-row-meaning">{word.short_meaning}</span>
          <span class="status-dot" data-status={status} title={status}></span>
        </button>
      {/each}
    </div>
  {/if}
</div>
