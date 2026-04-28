<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';
  import { learner } from '$lib/state/learner.svelte';
  import { loadVocabIndex, loadGrammar, getWord } from '$lib/data/corpus';
  import { countDueCards, nextDueChangeTimestamp } from '$lib/util/due-count';
  import { popup } from '$lib/state/popup.svelte';
  import Popup from '$lib/ui/Popup.svelte';
  import WordPopup from '$lib/ui/WordPopup.svelte';
  import GrammarPopup from '$lib/ui/GrammarPopup.svelte';
  import SentencePopup from '$lib/ui/SentencePopup.svelte';
  import ReloadPrompt from '$lib/ui/ReloadPrompt.svelte';
  import type { VocabIndex, GrammarState, Word } from '$lib/data/types';
  import { sanitizeImported } from '$lib/state/learner.svelte';

  let { children } = $props();

  let vocabIndex = $state<VocabIndex | null>(null);
  let grammar = $state<GrammarState | null>(null);
  let popupWord = $state<Word | null>(null);
  let popupWordError = $state<string | null>(null);
  let bootError = $state<string | null>(null);
  // Real-time-correct due-count for the menu's "Review N" badge.
  //
  // The badge previously read stale because its derivation called
  // Date.now() directly — Date.now() isn't a reactive dependency, so
  // a card whose `due` was 5 minutes in the future when the page
  // loaded never made the badge tick over to "1" when its time came.
  // Only mutations to the srs map (e.g. grading a card) re-ran the
  // derivation. Symptom: badge showed yesterday's number until refresh.
  //
  // Fix: a reactive `nowTick` $state. The `dueCount` derivation reads
  // `nowTick` (so it's a dependency) AND the srs map. After every
  // re-run, an $effect schedules a single, precise setTimeout for the
  // EXACT moment the next card becomes due — see nextDueChangeTimestamp.
  // No polling, no fixed cadence, no wasted wakeups: a session with
  // zero pending cards has zero timers; a session with one card due
  // in 7 minutes wakes exactly once 7 minutes from now.
  //
  // The clamp at 100ms protects against re-entrant scheduling if the
  // helper somehow returns a target in the past (defensive).
  let nowTick = $state(Date.now());
  let dueCount = $derived.by(() => {
    if (!learner.ready) return 0;
    return countDueCards(learner.state.srs, nowTick);
  });

  $effect(() => {
    if (!learner.ready) return;
    const target = nextDueChangeTimestamp(learner.state.srs, nowTick);
    if (target === null) return;
    const wait = Math.max(100, target - Date.now());
    const id = setTimeout(() => {
      nowTick = Date.now();
    }, wait);
    return () => clearTimeout(id);
  });

  onMount(async () => {
    try {
      await learner.init();
      [vocabIndex, grammar] = await Promise.all([loadVocabIndex(), loadGrammar()]);
    } catch (e) {
      console.error('Boot failed:', e);
      bootError = 'Could not load corpus. Please reload the page.';
    }
  });

  // Lazy-load the full Word record whenever a word popup opens.
  $effect(() => {
    const wid = popup.current.kind === 'word' ? popup.current.wordId : null;
    if (!wid) {
      popupWord = null;
      popupWordError = null;
      return;
    }
    popupWord = null;
    popupWordError = null;
    getWord(wid)
      .then((w) => {
        if (popup.current.kind === 'word' && popup.current.wordId === wid) {
          if (w) popupWord = w;
          else popupWordError = `Could not find word ${wid}.`;
        }
      })
      .catch(() => {
        if (popup.current.kind === 'word' && popup.current.wordId === wid) {
          popupWordError = 'Failed to load word details.';
        }
      });
  });

  // Theme is reset to auto and not user-toggleable — Phase D dark-mode
  // CSS broke text rendering (focus rings around every character token,
  // furigana unreadable). Reverted; reintroduce later with per-route
  // selectors that exempt .token elements.
  $effect(() => {
    if (!learner.ready) return;
    document.documentElement.removeAttribute('data-theme');
  });

  const views = [
    { name: 'read', label: 'Read', href: `${base}/read` },
    { name: 'library', label: 'Library', href: `${base}/library` },
    { name: 'review', label: 'Review', href: `${base}/review` },
    { name: 'vocab', label: 'Vocab', href: `${base}/vocab` },
    { name: 'grammar', label: 'Grammar', href: `${base}/grammar` },
    { name: 'stats', label: 'Stats', href: `${base}/stats` },
  ];

  function activeView(): string {
    const p = page.url.pathname;
    for (const v of views) {
      if (p.endsWith(`/${v.name}`)) return v.name;
    }
    return 'read';
  }

  // Export / Import / Reset
  let importEl: HTMLInputElement | undefined = $state();

  async function resetProgress() {
    // Two-step confirmation: blocks accidental wipes from a stray click,
    // and the second prompt makes the user type a word so muscle-memory
    // double-clicks can't destroy progress.
    const first = confirm(
      'Reset ALL progress?\n\n' +
        'This will permanently delete:\n' +
        '  • every card in your SRS queue\n' +
        '  • every story-completion mark\n' +
        '  • your current-story bookmark\n' +
        '  • your preferences\n\n' +
        'Continue?',
    );
    if (!first) return;
    const typed = prompt('Type RESET (in capitals) to confirm:');
    if (typed !== 'RESET') return;
    await learner.resetAll();
    alert('All progress has been reset.');
  }
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
    <button
      class="nav-action-btn nav-action-danger"
      onclick={resetProgress}
      title="Reset all progress (cannot be undone)"
      aria-label="Reset all progress (requires confirmation)"
    >⟲ Reset</button>
  </div>
</nav>

<main id="app">
  {#if bootError}
    <p class="empty-state">{bootError}</p>
  {:else if !vocabIndex || !grammar || !learner.ready}
    <p class="empty-state">Loading…</p>
  {:else}
    {@render children()}
  {/if}
</main>

<Popup
  open={popup.current.kind !== null}
  onClose={() => popup.close()}
  title={popup.current.kind === 'word' ? 'Word details' : 'Grammar details'}
>
  {#if popup.current.kind === 'word' && popup.current.wordId}
    {#if popupWord && grammar}
      <WordPopup
        word={popupWord}
        tok={popup.current.tok}
        story={null}
        {grammar}
        onOpenGrammar={(gid) => popup.openGrammar(gid)}
      />
    {:else if popupWordError}
      <p class="empty-state">{popupWordError}</p>
    {:else}
      <p class="empty-state">Loading…</p>
    {/if}
  {:else if popup.current.kind === 'grammar' && popup.current.grammarId && grammar}
    {@const gp = grammar.points[popup.current.grammarId]}
    {#if gp}
      <GrammarPopup {gp} />
    {/if}
  {:else if popup.current.kind === 'sentence' && popup.current.sentence}
    {@const s = popup.current.sentence}
    <SentencePopup sentence={s.data} storyId={s.story_id} sentenceIdx={s.sentence_idx} />
  {/if}
</Popup>

<ReloadPrompt />
