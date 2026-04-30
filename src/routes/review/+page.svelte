<script lang="ts">
  import { onMount } from 'svelte';
  import { learner } from '$lib/state/learner.svelte';
  import { loadStoryById, getWord, loadVocabIndex, findSentenceForWord } from '$lib/data/corpus';
  import { audioFor, playOnce } from '$lib/data/audio';
  import { applyGrade, buildQueue, GRADES, tickListeningMinting } from '$lib/state/srs';
  import { resolveReviewKey } from '$lib/util/review-keymap';
  import type { Sentence, Word, VocabIndex } from '$lib/data/types';
  import type { Card, Grade } from '$lib/state/types';
  import { cardKind } from '$lib/state/types';

  import { countDueByKind } from '$lib/util/due-count';

  let queue = $state<Card[]>([]);
  let revealed = $state(false);
  let contextSentence = $state<Sentence | null>(null);
  /** The full story object the current card belongs to, kept around
   *  so the listening card can grab its sentence audio path and so
   *  the echo step can fire after grading without a second fetch. */
  let contextStory = $state<Awaited<ReturnType<typeof loadStoryById>>>(null);
  /** Reading cards have a Word; listening cards leave this null. */
  let word = $state<Word | null>(null);
  let vocabIndex = $state<VocabIndex | null>(null);
  let lastUndoable = $state(false);
  /** Number of cards in the SRS map whose `due` is in the past, regardless
   *  of daily caps. This is the same predicate as the menu badge. When it
   *  diverges from `queue.length` the queue was clipped by a daily cap and
   *  we owe the user an honest explanation rather than "All caught up."
   *  See the empty-state branches below. */
  let trueDueCount = $state(0);
  /** Per-word audio source for reading cards (post-reveal replay).
   *  Null when no per-word audio is available. */
  let cardAudioSrc = $state<string | null>(null);
  /** Per-sentence audio source — used by listening cards as the prompt
   *  AND by reading cards' echo step after a successful grade. Null
   *  when the story / sentence has no audio. */
  let sentenceAudioSrc = $state<string | null>(null);

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
    // Review tab is reading-only. Listening cards live in the /listen
    // tab with their own queue. Setting listeningPerReview to 0 ensures
    // none leak into this session even if the SRS map contains them.
    queue = buildQueue(learner.state.srs ?? {}, {
      maxReviews: remainingReviews,
      newPerReview: learner.state.prefs.new_per_review ?? 4,
      listeningPerReview: 0,
    });
    // Badge uses reading-only count to match the nav badge.
    trueDueCount = countDueByKind(learner.state.srs, new Date(), 'reading');
    revealed = false;
    lastUndoable = (learner.state.history?.length ?? 0) > 0;
  }

  let card = $derived<Card | null>(queue[0] ?? null);
  /** Discriminator used throughout the template. Listening cards lack
   *  a `word` and reveal the sentence text + gloss instead of a word
   *  meaning. Reading cards behave exactly as before. */
  let isListening = $derived(card ? cardKind(card) === 'listening' : false);
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
    contextStory = null;
    word = null;
    cardAudioSrc = null;
    sentenceAudioSrc = null;
    if (!card) return;

    // Resolve story_id. Reading cards always carry context_story;
    // listening card ids encode (story, sentence) too.
    const storyId = card.context_story;
    if (!storyId) return;
    const story = await loadStoryById(storyId);
    if (!story || card !== queue[0]) return;
    contextStory = story;

    if (cardKind(card) === 'listening') {
      // Listening card: prompt is the sentence audio. The sentence text
      // (and gloss) become the answer revealed on Space.
      const sent = story.sentences[card.context_sentence_idx] ?? null;
      contextSentence = sent;
      sentenceAudioSrc = sent?.audio ?? null;
      // Auto-play once on load so the prompt is present immediately.
      // Browsers may block until the user has interacted with the page;
      // the on-screen Replay button is the recovery path.
      if (sentenceAudioSrc) {
        // Tiny delay so the audio dispatch doesn't race the
        // component's first paint (same trick as the legacy code).
        setTimeout(() => playSentenceAudio(), 80);
      }
      return;
    }

    // Reading card path. The card stores a (story, sentence_idx) hint
    // captured at mint time; usually the hint resolves directly. If it
    // doesn't (e.g. the corpus was rewritten and the word was renumbered
    // or moved between stories), `findSentenceForWord` walks the corpus
    // to recover a valid (story, sentence) pair so the user never sees
    // an isolated, contextless word card. Found locations that differ
    // from the card's stored hint are written back so subsequent reviews
    // skip the recovery walk.
    const w = await getWord(card.word_id);
    if (!w || card !== queue[0]) return;
    word = w;
    const found = await findSentenceForWord(
      card.word_id,
      card.context_story,
      card.context_sentence_idx,
    );
    if (card !== queue[0]) return;
    if (found) {
      contextStory = found.story;
      contextSentence = found.sentence;
      // Self-heal the SRS card if its hint pointed somewhere stale.
      // This survives the next save() (which happens on every grade).
      if (
        found.story.story_id !== card.context_story ||
        found.sentenceIdx !== card.context_sentence_idx
      ) {
        const stored = learner.state.srs[card.word_id];
        if (stored) {
          stored.context_story = found.story.story_id;
          stored.context_sentence_idx = found.sentenceIdx;
        }
      }
    } else {
      // No sentence anywhere in the corpus contains this word_id. Leave
      // contextSentence null; the template renders a graceful fallback
      // rather than silently lying about context.
      contextSentence = null;
    }
    cardAudioSrc = contextStory?.word_audio?.[card.word_id] ?? null;
    sentenceAudioSrc = contextSentence?.audio ?? null;
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

  /** Listening-card prompt + Replay button + post-grade echo all share
   *  this dispatcher. Uses playOnce so a second press cleanly stops the
   *  first attempt (no overlapping audio when the user mashes buttons). */
  function playSentenceAudio() {
    if (!sentenceAudioSrc) return;
    playOnce(sentenceAudioSrc);
  }

  function reveal() {
    revealed = true;
    if (learner.state.prefs.audio_on_review_reveal && card && word) {
      playCardAudio();
    }
  }

  /**
   * Should the post-grade ECHO (variant B) fire on this card?
   *
   *   - Only after Good (1) or Easy (2) — never Again. The echo is a
   *     reward for recognition, not a do-over.
   *   - Only on READING cards. Listening cards already played the
   *     sentence audio as their prompt; replaying after grading would
   *     just be noise.
   *   - Only when sentence audio actually exists (cardAudioSrc is the
   *     per-word path; we use sentenceAudioSrc for the echo so the
   *     learner gets prosody, not isolated word audio).
   *   - Policy `'never'` always returns false; `'always'` always returns
   *     true (subject to the other gates); `'mature_only'` requires the
   *     PRE-grade card status to be `young` or `mature` so brand-new
   *     and learning cards don't get distracted by sentence audio
   *     whose meaning the user just looked up.
   */
  function shouldEchoAfterGrade(c: Card, g: Grade): boolean {
    if (g === GRADES.AGAIN) return false;
    if (cardKind(c) === 'listening') return false;
    if (!sentenceAudioSrc) return false;
    const policy = learner.state.prefs.audio_echo_on_grade ?? 'mature_only';
    if (policy === 'never') return false;
    if (policy === 'always') return true;
    // 'mature_only': only echo on cards that have already graduated.
    return c.status === 'young' || c.status === 'mature';
  }

  function grade(g: Grade) {
    if (!card) return;
    // Capture the echo decision against the PRE-grade card snapshot —
    // applyGrade may flip the status (e.g. mature → relearning on
    // Again, which is moot since Again skips echo, or new → learning
    // on Good, which we explicitly want to NOT echo on). Reading the
    // post-grade status would defeat the point of `mature_only`.
    const echo = shouldEchoAfterGrade(card, g);
    const echoSrc = sentenceAudioSrc;
    const gradedStory = contextStory; // captured for tick below
    const result = applyGrade(card, g, new Date(), learner.state.prefs.target_retention);
    learner.state.srs[card.word_id] = result.card;
    learner.pushHistory(result.log);
    // After grading, check whether any listening cards in the current
    // story have become eligible (their words may have just hit mature
    // thanks to this grade). tickListeningMinting is O(sentences) and
    // pure (copy-on-write), so this is cheap and safe.
    if (gradedStory) {
      const ticked = tickListeningMinting(gradedStory, learner.state.srs);
      if (ticked !== learner.state.srs) learner.state.srs = ticked;
    }
    learner.save();
    revealed = false;
    queue = queue.slice(1);
    if (queue.length === 0) rebuildQueue();
    lastUndoable = true;
    // Echo the sentence audio AFTER state mutation but with a tiny
    // delay so the new card's loadCurrent autoplay (listening cards)
    // doesn't race against ours. The echo is interruptible — pressing
    // grade on the next card calls stopCurrent via playOnce / playCardAudio.
    if (echo && echoSrc) {
      setTimeout(() => {
        // Only fire if the user hasn't already triggered fresh audio
        // (e.g. by landing on a listening card whose autoplay started).
        // playOnce calls stopCurrent internally so worst case is a
        // sub-second overlap; the explicit guard keeps it cleaner.
        playOnce(echoSrc);
      }, 60);
    }
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
      {:else if isListening}
        <!-- LISTENING card (variant A): sentence audio is the prompt;
             the JP text and gloss are the revealed answer. The card
             tests sentence-level comprehension as a separate retention
             track from word recognition (different SRS row, same FSRS).

             NOTE: this branch must precede the `!word` guard below —
             listening cards never load a Word and would otherwise be
             stuck on "Loading card…" forever. -->
        <div class="review-card">
          <div class="review-card-kind" aria-label="Card type">🎧 Listening</div>
          <div class="review-listen-prompt" aria-live="polite">
            {#if sentenceAudioSrc}
              <button class="btn-audio review-listen-replay" onclick={playSentenceAudio}>
                ▶ Replay
              </button>
              <p class="review-listen-hint">
                Listen, then press <kbd>Space</kbd> to reveal.
              </p>
            {:else}
              <p class="review-listen-hint">
                No audio available for this sentence — press <kbd>Space</kbd> to reveal and grade.
              </p>
            {/if}
          </div>
          <div class="review-answer" class:visible={revealed} id="review-answer">
            {#if contextSentence}
              <div class="review-sentence review-sentence-listen" lang="ja">
                {#each contextSentence.tokens as tok, ti (ti)}
                  <span>{tok.t}</span>
                {/each}
              </div>
              <div class="review-gloss">{contextSentence.gloss_en}</div>
              <div class="review-source">
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
      {:else if !word}
        <!-- Reading card: word data still in flight. -->
        <p class="empty-state">Loading card…</p>
      {:else}
        <!-- READING card (the original deck). Highlighted word in its
             native sentence; reveal exposes word details + gloss. -->
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
              <!-- Fallback: no sentence in the corpus contains this
                   word_id. This should never happen in a healthy corpus,
                   but is possible if state and stories drift apart
                   (e.g. mid-rewrite). Surface the situation honestly
                   rather than pretending the bare word is the prompt. -->
              <span class="review-highlight">{word.surface}</span>
              <div class="review-no-context-note">
                No example sentence found in the current corpus for this card.
              </div>
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
  /* Card-kind chip on the listening branch — small, muted, top-aligned
     so the user can tell at a glance that this is the second modality
     and not a broken reading card. */
  .review-card-kind {
    display: inline-block;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    background: var(--surface2);
    border-radius: 4px;
    padding: 0.15rem 0.55rem;
    margin-bottom: 0.7rem;
  }
  /* Listening-card revealed sentence: slightly smaller than the
     reading card's centered sentence so the gloss + source line
     don't crowd. */
  .review-sentence-listen {
    font-size: 1.15rem;
    line-height: 1.85;
    margin-top: 0.4rem;
  }
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
  /* Surfaced when the corpus has no sentence containing this card's
     word_id at all — distinct from the normal "show the word in its
     sentence" path. Keeps the user oriented instead of leaving them
     staring at a single character with no explanation. */
  .review-no-context-note {
    margin-top: 0.6rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
  }
</style>
