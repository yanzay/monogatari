<script lang="ts">
  import { onMount } from 'svelte';
  import { learner } from '$lib/state/learner.svelte';
  import { loadStoryById, getWord, loadVocabIndex } from '$lib/data/corpus';
  import { audioFor } from '$lib/data/audio';
  import { applyGrade, buildQueue, GRADES } from '$lib/state/srs';
  import { resolveReviewKey } from '$lib/util/review-keymap';
  import type { Sentence, Word, VocabIndex } from '$lib/data/types';
  import type { Card, Grade } from '$lib/state/types';

  import { countDueCards } from '$lib/util/due-count';

  let queue = $state<Card[]>([]);
  let revealed = $state(false);
  let contextSentence = $state<Sentence | null>(null);
  let word = $state<Word | null>(null);
  let vocabIndex = $state<VocabIndex | null>(null);
  let lastUndoable = $state(false);
  /** Number of cards in the SRS map whose `due` is in the past, regardless
   *  of daily caps. This is the same predicate as the menu badge. When it
   *  diverges from `queue.length` the queue was clipped by a daily cap and
   *  we owe the user an honest explanation rather than "All caught up."
   *  See the empty-state branches below. */
  let trueDueCount = $state(0);
  /** Per-card audio source captured at load time so Replay/Show-text don't
   *  need to reload the story. Null = no audio available for this card. */
  let cardAudioSrc = $state<string | null>(null);
  /** True when the current card is in listening-first mode AND audio is
   *  available AND the user hasn't yet bailed to text. The sentence is
   *  hidden until the user reveals or hits "Show text". */
  let textHidden = $state(false);

  onMount(async () => {
    vocabIndex = await loadVocabIndex();
    rebuildQueue();
  });

  function rebuildQueue() {
    learner.rolloverDailyIfNeeded();
    // Only the optional review cap (null = no cap) is honored. The
    // previous `maxNew` cap was removed: in a graded reader the user
    // has already opted into every word in the SRS map by reading the
    // story it came from, so throttling those cards is the app
    // overruling its own user.
    const reviewCap = learner.state.prefs.daily_max_reviews;
    const remainingReviews =
      reviewCap === null || reviewCap === undefined
        ? Infinity
        : Math.max(0, reviewCap - (learner.state.daily.reviewed ?? 0));
    queue = buildQueue(learner.state.srs ?? {}, {
      maxReviews: remainingReviews,
      newPerReview: learner.state.prefs.new_per_review ?? 4,
    });
    // Use the same predicate as the menu badge so the two views can
    // never disagree about "is anything due?".
    trueDueCount = countDueCards(learner.state.srs, new Date());
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
    cardAudioSrc = null;
    textHidden = false;
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
    } else {
      contextSentence =
        story.sentences.find((s) => s.tokens.some((t) => t.word_id === card.word_id)) ?? null;
    }
    cardAudioSrc = story.word_audio?.[card.word_id] ?? null;

    // Listen-first: hide text + autoplay audio, but ONLY if audio exists.
    // Cards without audio fall back to normal text-first presentation.
    if (learner.state.prefs.audio_listen_first && cardAudioSrc) {
      textHidden = true;
      // Small delay so the autoplay isn't lost to the page-mount race.
      setTimeout(() => playCardAudio(), 80);
    }
  }

  function playCardAudio() {
    if (!cardAudioSrc) return;
    try {
      const a = audioFor(cardAudioSrc);
      a?.play().catch(() => {});
    } catch {
      /* noop */
    }
  }

  function showText() {
    textHidden = false;
  }

  function reveal() {
    revealed = true;
    textHidden = false; // any reveal forces text to show
    if (learner.state.prefs.audio_on_review_reveal && card && word) {
      playCardAudio();
    }
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
    const restored = learner.popHistory();
    if (!restored) return;
    learner.save();
    rebuildQueue();
  }

  function onKeydown(e: KeyboardEvent) {
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
          today: {learner.state.daily.reviewed}{#if learner.state.prefs.daily_max_reviews != null}/{learner.state.prefs.daily_max_reviews}{/if}
        </span>
        {#if lastUndoable}
          <button class="review-undo" onclick={undo} title="Undo last review (U)">↶ Undo</button>
        {/if}
      </div>

      {#if !card}
        {#if trueDueCount === 0}
          <!-- Genuinely caught up: nothing due in the SRS map. -->
          {#if learner.state.daily.reviewed > 0}
            <p class="empty-state">All caught up. {learner.state.daily.reviewed} reviews done today.</p>
          {:else}
            <p class="empty-state">Nothing due. Read the next story or come back later.</p>
          {/if}
        {:else if learner.state.prefs.daily_max_reviews != null}
          <!-- The user opted into a self-imposed review cap and has hit it.
               The badge correctly shows the true due count; we explain
               why this session is empty and how to lift the cap. -->
          <p class="empty-state">
            Daily review limit reached
            ({learner.state.daily.reviewed}/{learner.state.prefs.daily_max_reviews}).
            {trueDueCount} card{trueDueCount === 1 ? '' : 's'} still due — come back tomorrow,
            or raise <code>daily_max_reviews</code> in Stats &amp; settings (or set it
            blank for no cap).
          </p>
        {:else}
          <!-- No cap set, yet there are due cards but the queue is empty.
               This would be a genuine bug. Surface it loudly rather than
               silently lying to the user with "All caught up". -->
          <p class="empty-state">
            {trueDueCount} card{trueDueCount === 1 ? '' : 's'} due, but the session queue
            came up empty. Try refreshing — if this persists, please report it.
          </p>
        {/if}
      {:else if !word}
        <p class="empty-state">Loading card…</p>
      {:else}
        <div class="review-card">
          {#if textHidden}
            <!-- Listen-first mode: sentence is hidden, audio replaces it. -->
            <div class="review-listen-prompt" aria-live="polite">
              <button class="btn-audio review-listen-replay" onclick={playCardAudio}>
                ▶ Replay
              </button>
              <button class="review-listen-show" onclick={showText}>
                Show text
              </button>
              <p class="review-listen-hint">
                Listen, then press <kbd>Space</kbd> to reveal.
              </p>
            </div>
          {:else}
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
  /* Listen-first mode UI */
  .review-listen-prompt {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
    padding: 1.5rem 0;
    min-height: 6rem;
    justify-content: center;
  }
  .review-listen-replay {
    font-size: 1rem;
    padding: 0.55rem 1.4rem;
  }
  .review-listen-show {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-muted);
    background: none;
    text-decoration: underline;
    cursor: pointer;
  }
  .review-listen-show:hover { color: var(--text); }
  .review-listen-hint {
    font-size: 0.78rem;
    color: var(--text-muted);
    font-style: italic;
    margin: 0.3rem 0 0;
  }
  .review-listen-hint kbd {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    padding: 0.05rem 0.35rem;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 3px;
  }
</style>
