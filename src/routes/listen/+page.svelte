<script lang="ts">
  import { onMount } from 'svelte';
  import { learner } from '$lib/state/learner.svelte';
  import { loadStoryById, loadVocabIndex } from '$lib/data/corpus';
  import { playOnce } from '$lib/data/audio';
  import { applyGrade, buildQueue, GRADES, tickListeningMinting } from '$lib/state/srs';
  import { resolveReviewKey } from '$lib/util/review-keymap';
  import { countDueByKind } from '$lib/util/due-count';
  import type { Sentence, VocabIndex } from '$lib/data/types';
  import type { Card, Grade } from '$lib/state/types';
  import { cardKind } from '$lib/state/types';

  let queue = $state<Card[]>([]);
  let revealed = $state(false);
  let contextSentence = $state<Sentence | null>(null);
  let vocabIndex = $state<VocabIndex | null>(null);
  let lastUndoable = $state(false);
  let sentenceAudioSrc = $state<string | null>(null);
  /** True due-count for the empty-state honest message (same as nav badge). */
  let trueDueCount = $state(0);

  onMount(async () => {
    vocabIndex = await loadVocabIndex();
    rebuildQueue();
  });

  function rebuildQueue() {
    learner.rolloverDailyIfNeeded();
    // Listening tab: listening-only queue. No reading cards, no cap
    // (listening sessions are typically short — unlocking is the
    // bottleneck, not session length).
    queue = buildQueue(learner.state.srs ?? {}, {
      // Pass Infinity for listening; set reading to 0 by using a
      // negative listeningPerReview ratio trick. Actually: we build
      // the queue with listeningPerReview = Infinity so ALL listening
      // cards come through, and drop all reading cards by setting
      // their budget to 0 via maxReviews = 0 + a pure-listening filter
      // applied post-hoc. Simpler: just filter the queue by kind.
      listeningPerReview: 1, // 1 listening per 0 reading = all listening
      newPerReview: 0,       // No reading news
      maxReviews: 0,         // No reading reviews
    }).filter((c) => cardKind(c) === 'listening');
    trueDueCount = countDueByKind(learner.state.srs, new Date(), 'listening');
    revealed = false;
    lastUndoable = (learner.state.history?.length ?? 0) > 0;
  }

  let card = $derived<Card | null>(queue[0] ?? null);
  let queueStats = $derived.by(() => {
    let learning = 0, reviews = 0, news = 0;
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
    sentenceAudioSrc = null;
    if (!card) return;
    const story = await loadStoryById(card.context_story);
    if (!story || card !== queue[0]) return;
    const sent = story.sentences[card.context_sentence_idx] ?? null;
    contextSentence = sent;
    sentenceAudioSrc = sent?.audio ?? null;
    // Auto-play the sentence audio as the prompt.
    if (sentenceAudioSrc) {
      setTimeout(() => playSentenceAudio(), 80);
    }
  }

  function playSentenceAudio() {
    if (!sentenceAudioSrc) return;
    playOnce(sentenceAudioSrc);
  }

  function reveal() {
    revealed = true;
  }

  function grade(g: Grade) {
    if (!card) return;
    const result = applyGrade(card, g, new Date(), learner.state.prefs.target_retention);
    learner.state.srs[card.word_id] = result.card;
    learner.pushHistory(result.log);
    learner.save();
    revealed = false;
    queue = queue.slice(1);
    if (queue.length === 0) rebuildQueue();
    lastUndoable = true;
  }

  function undo() {
    // popHistory pops the last review-log entry AND restores the prior
    // card state inside the SRS map (single source of truth — see
    // LearnerStore.popHistory). We just re-derive the queue.
    const restored = learner.popHistory();
    if (!restored) return;
    learner.save();
    rebuildQueue();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (!card) return;
    const focusedTag = (e.target as HTMLElement | null)?.tagName;
    const action = resolveReviewKey(e.key, revealed, focusedTag);
    switch (action.kind) {
      case 'ignore':
        return;
      case 'reveal':
        if (action.preventDefault) e.preventDefault();
        reveal();
        return;
      case 'grade':
        if (action.preventDefault) e.preventDefault();
        if (action.grade === 'again') grade(GRADES.AGAIN);
        else if (action.grade === 'good') grade(GRADES.GOOD);
        else if (action.grade === 'easy') grade(GRADES.EASY);
        return;
      case 'undo':
        undo();
        return;
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div id="view-listen" class="view active">
  <div id="listen-container" class="listen-container">
    {#if !learner.ready || !vocabIndex}
      <p class="empty-state">Loading…</p>
    {:else}
      <div class="listen-header">
        <div class="listen-stats">
          {#if queueStats.total > 0}
            <span class="stat-pill">{queueStats.news} new</span>
            <span class="stat-pill">{queueStats.learning} learning</span>
            <span class="stat-pill">{queueStats.reviews} review</span>
          {/if}
        </div>
        <div class="listen-actions">
          {#if lastUndoable}
            <button class="btn-undo" onclick={undo} title="Undo last grade">↩ Undo</button>
          {/if}
        </div>
      </div>

      {#if !card}
        {#if trueDueCount === 0 && queue.length === 0}
          <div class="empty-state listen-empty">
            <p class="listen-empty-title">🎧 No listening cards yet</p>
            <p class="listen-empty-body">
              Listening cards unlock sentence by sentence as the words in each sentence
              become <strong>mature</strong> in your reading deck — meaning every word
              has been reviewed long enough that FSRS schedules it out ≥ 3 weeks.
            </p>
            <p class="listen-empty-body">
              Keep reviewing in the <strong>Review</strong> tab. When a sentence's
              words all mature, its listening card appears here automatically.
            </p>
          </div>
        {:else}
          <div class="empty-state">
            <p>All caught up! 🎧</p>
            {#if trueDueCount > queue.length}
              <p class="empty-hint">
                {trueDueCount - queue.length} card{trueDueCount - queue.length !== 1 ? 's' : ''}
                were hidden by the daily review cap. Increase the cap in Settings.
              </p>
            {/if}
          </div>
        {/if}
      {:else}
        <!-- LISTENING CARD: audio prompt → JP text + gloss reveal -->
        <div class="listen-card">
          <div class="listen-card-kind" aria-label="Card type">🎧 Listening</div>
          <div class="listen-prompt" aria-live="polite">
            {#if sentenceAudioSrc}
              <button class="btn-audio listen-replay" onclick={playSentenceAudio}>
                ▶ Replay
              </button>
              <p class="listen-hint">
                Listen, then press <kbd>Space</kbd> to reveal.
              </p>
            {:else}
              <p class="listen-hint">
                No audio for this sentence — press <kbd>Space</kbd> to reveal and grade.
              </p>
            {/if}
          </div>
          <div class="listen-answer" class:visible={revealed} id="listen-answer">
            {#if contextSentence}
              <div class="listen-sentence" lang="ja">
                {#each contextSentence.tokens as tok, ti (ti)}
                  <span>{tok.t}</span>
                {/each}
              </div>
              <div class="listen-gloss">{contextSentence.gloss_en}</div>
              <div class="listen-source">
                — Story {card.context_story}, sentence {card.context_sentence_idx + 1}
              </div>
            {/if}
          </div>
        </div>

        {#if !revealed}
          <button class="btn-reveal" onclick={reveal}>Show text <kbd>Space</kbd></button>
        {:else}
          <div class="grade-buttons">
            <button class="grade-btn" onclick={() => grade(GRADES.AGAIN)}>
              Again<span class="grade-label">1</span>
            </button>
            <button class="grade-btn" onclick={() => grade(GRADES.GOOD)}>
              Good<span class="grade-label">2 / Space</span>
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
  .listen-container {
    max-width: 640px;
    margin: 0 auto;
    padding: 2rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    min-height: 60vh;
  }

  .listen-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .listen-stats {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
  }

  .stat-pill {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    background: var(--surface2);
    border-radius: 12px;
    padding: 0.2rem 0.65rem;
    color: var(--text-muted);
  }

  .listen-actions {
    display: flex;
    gap: 0.5rem;
  }

  .btn-undo {
    font-size: 0.8rem;
    color: var(--text-muted);
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.3rem 0.75rem;
    cursor: pointer;
  }
  .btn-undo:hover { background: var(--surface2); }

  /* ── Card ─────────────────────────────────────────────────────── */
  .listen-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem 1.75rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .listen-card-kind {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    background: var(--surface2);
    border-radius: 4px;
    padding: 0.15rem 0.55rem;
    align-self: flex-start;
  }

  .listen-prompt {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    padding: 1.25rem 0;
  }

  .listen-replay {
    font-size: 1.1rem;
    padding: 0.6rem 1.6rem;
    background: var(--accent, #4f8ef7);
    color: #fff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .listen-replay:hover { opacity: 0.87; }

  .listen-hint {
    font-size: 0.82rem;
    color: var(--text-muted);
    text-align: center;
  }
  .listen-hint kbd {
    font-family: var(--font-mono);
    font-size: 0.75em;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.05rem 0.35rem;
  }

  /* ── Answer (revealed) ───────────────────────────────────────── */
  .listen-answer {
    display: none;
    flex-direction: column;
    gap: 0.6rem;
    border-top: 1px solid var(--border);
    padding-top: 1rem;
  }
  .listen-answer.visible { display: flex; }

  .listen-sentence {
    font-size: 1.35rem;
    line-height: 1.8;
    font-weight: 500;
    letter-spacing: 0.02em;
  }

  .listen-gloss {
    font-size: 0.92rem;
    color: var(--text-muted);
    font-style: italic;
  }

  .listen-source {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--text-muted);
  }

  /* ── Grade buttons (shared semantics, listen-page sizing) ─────── */
  .btn-reveal {
    align-self: center;
    font-size: 1rem;
    padding: 0.65rem 2rem;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-reveal:hover { background: var(--surface3, var(--surface2)); }
  .btn-reveal kbd {
    font-family: var(--font-mono);
    font-size: 0.75em;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.05rem 0.35rem;
    margin-left: 0.3rem;
  }

  .grade-buttons {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
    flex-wrap: wrap;
  }

  .grade-btn {
    min-width: 6rem;
    padding: 0.55rem 1.1rem;
    font-size: 0.95rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface2);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    transition: background 0.12s;
  }
  .grade-btn:hover { background: var(--surface3, var(--surface)); }

  .grade-label {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--text-muted);
  }

  /* ── Empty state ─────────────────────────────────────────────── */
  .listen-empty {
    text-align: left;
    max-width: 480px;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .listen-empty-title {
    font-size: 1.15rem;
    font-weight: 600;
  }
  .listen-empty-body {
    font-size: 0.9rem;
    color: var(--text-muted);
    line-height: 1.6;
  }
</style>
