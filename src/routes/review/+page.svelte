<script lang="ts">
  import { onMount } from 'svelte';
  import { learner } from '$lib/state/learner.svelte';
  import { loadStoryById, getWord, loadVocabIndex } from '$lib/data/corpus';
  import { audioFor } from '$lib/data/audio';
  import { applyGrade, buildQueue, GRADES } from '$lib/state/srs';
  import type { Sentence, Word, VocabIndex } from '$lib/data/types';
  import type { Card, Grade } from '$lib/state/types';

  let queue = $state<Card[]>([]);
  let revealed = $state(false);
  let contextSentence = $state<Sentence | null>(null);
  let word = $state<Word | null>(null);
  let vocabIndex = $state<VocabIndex | null>(null);
  let lastUndoable = $state(false);

  onMount(async () => {
    vocabIndex = await loadVocabIndex();
    rebuildQueue();
  });

  function rebuildQueue() {
    learner.rolloverDailyIfNeeded();
    const remainingNew = Math.max(
      0,
      (learner.state.prefs.daily_max_new ?? 20) - (learner.state.daily.new_introduced ?? 0),
    );
    const remainingReviews = Math.max(
      0,
      (learner.state.prefs.daily_max_reviews ?? 200) - (learner.state.daily.reviewed ?? 0),
    );
    queue = buildQueue(learner.state.srs ?? {}, {
      maxNew: remainingNew,
      maxReviews: remainingReviews,
      newPerReview: learner.state.prefs.new_per_review ?? 4,
    });
    revealed = false;
    lastUndoable = (learner.state.history?.length ?? 0) > 0;
  }

  let card = $derived<Card | null>(queue[0] ?? null);
  let queueStats = $derived.by(() => {
    let learning = 0,
      reviews = 0,
      news = 0;
    for (const c of queue) {
      if (c.status === 'new') news++;
      else if (c.status === 'learning' || c.status === 'relearning') learning++;
      else reviews++;
    }
    return { learning, reviews, news, total: queue.length };
  });

  $effect(() => {
    if (card) loadCurrent();
  });

  async function loadCurrent() {
    contextSentence = null;
    word = null;
    if (!card) return;
    const w = await getWord(card.word_id);
    if (!w || card !== queue[0]) return;
    word = w;

    let storyId: number | null = card.context_story ?? null;
    if (!storyId && w.first_story) storyId = Number(w.first_story);
    if (!storyId) return;
    const story = await loadStoryById(storyId);
    if (!story || card !== queue[0]) return;
    const exact = story.sentences[card.context_sentence_idx];
    if (exact && exact.tokens.some((t) => t.word_id === card.word_id)) {
      contextSentence = exact;
      return;
    }
    contextSentence =
      story.sentences.find((s) => s.tokens.some((t) => t.word_id === card.word_id)) ?? null;
  }

  function reveal() {
    revealed = true;
    if (
      learner.state.prefs.audio_on_review_reveal &&
      card &&
      vocabIndex &&
      word
    ) {
      // Audio path is per-story word_audio map; we need the story to look it up.
      loadStoryById(card.context_story).then((story) => {
        if (!story || card !== queue[0]) return;
        const src = story.word_audio?.[card.word_id];
        if (src) {
          try {
            const a = audioFor(src);
            a?.play().catch(() => {});
          } catch {
            /* noop */
          }
        }
      });
    }
  }

  function grade(g: Grade) {
    if (!card) return;
    const wasNew = card.status === 'new';
    const result = applyGrade(card, g, new Date(), learner.state.prefs.target_retention);
    learner.state.srs[card.word_id] = result.card;
    learner.pushHistory(result.log);
    if (wasNew) learner.state.daily.new_introduced += 1;
    learner.save();
    revealed = false;
    queue = queue.slice(1);
    if (queue.length === 0) rebuildQueue();
    lastUndoable = true;
  }

  function undo() {
    const restored = learner.popHistory();
    if (!restored) return;
    learner.save();
    rebuildQueue();
  }

  function onKeydown(e: KeyboardEvent) {
    if (!card) return;
    if (e.target && (e.target as HTMLElement).tagName === 'INPUT') return;
    if (!revealed) {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        reveal();
      }
      return;
    }
    if (e.key === '1') grade(GRADES.AGAIN);
    else if (e.key === '2') grade(GRADES.GOOD);
    else if (e.key === '3') grade(GRADES.EASY);
    else if (e.key.toLowerCase() === 'u') undo();
  }

  onMount(() => {
    document.addEventListener('keydown', onKeydown);
    return () => document.removeEventListener('keydown', onKeydown);
  });
</script>

<div id="view-review" class="view active">
  <div id="review-container" class="review-container">
    {#if !learner.ready || !vocabIndex}
      <p class="empty-state">Loading…</p>
    {:else}
      <div class="review-header">
        <span class="review-stat" title="Learning + Relearning">⚡ {queueStats.learning}</span>
        <span class="review-stat" title="Reviews due">↻ {queueStats.reviews}</span>
        <span class="review-stat" title="New cards this session">+ {queueStats.news}</span>
        <span class="review-stat-spacer"></span>
        <span class="review-stat-muted">
          today: {learner.state.daily.reviewed}/{learner.state.prefs.daily_max_reviews}
        </span>
        {#if lastUndoable}
          <button class="review-undo" onclick={undo} title="Undo last review (U)">↶ Undo</button>
        {/if}
      </div>

      {#if !card}
        {#if learner.state.daily.reviewed > 0}
          <p class="empty-state">All caught up. {learner.state.daily.reviewed} reviews done today.</p>
        {:else}
          <p class="empty-state">Nothing due. Read the next story or come back later.</p>
        {/if}
      {:else if !word}
        <p class="empty-state">Loading card…</p>
      {:else}
        <div class="review-card">
          <div class="review-sentence" lang="ja">
            {#if contextSentence}
              {#each contextSentence.tokens as tok, ti (ti)}
                {#if tok.word_id === card.word_id}
                  <span class="review-highlight">{tok.t}</span>
                {:else}
                  <span>{tok.t}</span>
                {/if}
              {/each}
            {:else}
              <span class="review-highlight">{word.surface}</span>
            {/if}
          </div>
          {#if contextSentence}
            <div class="review-source">
              — Story {card.context_story}, sentence {card.context_sentence_idx + 1}
            </div>
          {/if}
          <div class="review-answer" class:visible={revealed} id="review-answer">
            <div class="review-word-jp" lang="ja">{word.surface}</div>
            <div class="review-word-reading">{word.kana} / {word.reading} /</div>
            <div class="review-word-meaning">{word.meanings.join('; ')}</div>
            {#if contextSentence}
              <div class="review-gloss">{contextSentence.gloss_en}</div>
            {/if}
          </div>
        </div>

        {#if !revealed}
          <button class="btn-reveal" onclick={reveal}>Show answer <kbd>Space</kbd></button>
        {:else}
          <div class="grade-buttons">
            <button class="grade-btn" onclick={() => grade(GRADES.AGAIN)}>
              Again<span class="grade-label">1</span>
            </button>
            <button class="grade-btn" onclick={() => grade(GRADES.GOOD)}>
              Good<span class="grade-label">2</span>
            </button>
            <button class="grade-btn" onclick={() => grade(GRADES.EASY)}>
              Easy<span class="grade-label">3</span>
            </button>
          </div>
        {/if}
      {/if}
    {/if}
  </div>
</div>

<style>
  .review-header {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.4rem 0.6rem 0.6rem;
    color: var(--text-muted);
    font-size: 0.8rem;
  }
  .review-stat {
    font-variant-numeric: tabular-nums;
  }
  .review-stat-spacer {
    flex: 1;
  }
  .review-stat-muted {
    color: var(--text-light);
    font-variant-numeric: tabular-nums;
  }
  .review-undo {
    background: none;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.2rem 0.5rem;
    color: var(--text-muted);
    font-size: 0.78rem;
    cursor: pointer;
  }
  .review-undo:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .btn-reveal kbd {
    margin-left: 0.5rem;
    padding: 0.05rem 0.35rem;
    font-size: 0.7rem;
    border: 1px solid currentColor;
    border-radius: 3px;
    opacity: 0.7;
  }
</style>
