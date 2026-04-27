<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';
  import { learner } from '$lib/state/learner.svelte';
  import { loadVocab, loadGrammar } from '$lib/data/corpus';
  import { popup } from '$lib/state/popup.svelte';
  import Popup from '$lib/ui/Popup.svelte';
  import WordPopup from '$lib/ui/WordPopup.svelte';
  import GrammarPopup from '$lib/ui/GrammarPopup.svelte';
  import type { VocabState, GrammarState } from '$lib/data/types';
  import { sanitizeImported } from '$lib/state/learner.svelte';

  let { children } = $props();

  let vocab = $state<VocabState | null>(null);
  let grammar = $state<GrammarState | null>(null);
  let bootError = $state<string | null>(null);
  let dueCount = $derived.by(() => {
    if (!learner.ready) return 0;
    const now = Date.now();
    return Object.values(learner.state.srs).filter((c) => {
      if (!c.due) return true;
      const t = new Date(c.due).getTime();
      return !Number.isFinite(t) || t <= now;
    }).length;
  });

  onMount(async () => {
    try {
      await learner.init();
      [vocab, grammar] = await Promise.all([loadVocab(), loadGrammar()]);
    } catch (e) {
      console.error('Boot failed:', e);
      bootError = 'Could not load corpus. Please reload the page.';
    }
  });

  // Theme handling
  $effect(() => {
    if (!learner.ready) return;
    const theme = learner.state.prefs.theme ?? 'auto';
    document.documentElement.dataset.theme = theme;
  });

  const views = [
    { name: 'read', label: 'Read', href: `${base}/read` },
    { name: 'library', label: 'Library', href: `${base}/library` },
    { name: 'review', label: 'Review', href: `${base}/review` },
    { name: 'vocab', label: 'Vocab', href: `${base}/vocab` },
    { name: 'grammar', label: 'Grammar', href: `${base}/grammar` },
  ];

  function activeView(): string {
    const p = page.url.pathname;
    for (const v of views) {
      if (p.endsWith(`/${v.name}`)) return v.name;
    }
    return 'read';
  }

  // Export / Import
  let importEl: HTMLInputElement | undefined = $state();
  function exportProgress() {
    const blob = new Blob([learner.exportJSON()], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `monogatari_progress_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  async function importProgress(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const sanitized = sanitizeImported(parsed);
      if (sanitized.version > 2) {
        alert('This progress file was created by a newer version of Monogatari. Please update.');
        return;
      }
      learner.replace(sanitized);
      alert('Progress imported successfully!');
    } catch (err) {
      console.error(err);
      alert('Invalid progress file.');
    } finally {
      input.value = '';
    }
  }
</script>

<nav class="nav">
  <span class="nav-logo" lang="ja">物語</span>
  <div class="nav-links">
    {#each views as v (v.name)}
      <a
        class="nav-btn"
        class:active={activeView() === v.name}
        data-view={v.name}
        href={v.href}
        onclick={(e) => {
          e.preventDefault();
          goto(v.href);
        }}
      >
        {v.label}{#if v.name === 'review' && dueCount > 0}
          <span class="review-badge">{dueCount}</span>
        {/if}
      </a>
    {/each}
  </div>
  <div class="nav-actions">
    <button class="nav-action-btn" onclick={exportProgress} title="Export progress">↑ Export</button>
    <label class="nav-action-btn" title="Import progress">
      ↓ Import
      <input
        type="file"
        accept=".json"
        bind:this={importEl}
        onchange={importProgress}
        hidden
      />
    </label>
  </div>
</nav>

<main id="app">
  {#if bootError}
    <p class="empty-state" style="padding:2rem;">{bootError}</p>
  {:else if !vocab || !grammar || !learner.ready}
    <p class="empty-state" style="padding:2rem;">Loading…</p>
  {:else}
    {@render children()}
  {/if}
</main>

<Popup
  open={popup.current.kind !== null}
  onClose={() => popup.close()}
  title={popup.current.kind === 'word' ? 'Word details' : 'Grammar details'}
>
  {#if popup.current.kind === 'word' && popup.current.wordId && vocab}
    {@const w = vocab.words[popup.current.wordId]}
    {#if w && grammar}
      <WordPopup
        word={w}
        tok={popup.current.tok}
        story={null}
        {grammar}
        onOpenGrammar={(gid) => popup.openGrammar(gid)}
      />
    {/if}
  {:else if popup.current.kind === 'grammar' && popup.current.grammarId && grammar}
    {@const gp = grammar.points[popup.current.grammarId]}
    {#if gp}
      <GrammarPopup {gp} />
    {/if}
  {/if}
</Popup>
