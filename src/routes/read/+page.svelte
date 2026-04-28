<script lang="ts">
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';
  import { learner } from '$lib/state/learner.svelte';
  import { loadStoryById, loadVocabIndex } from '$lib/data/corpus';
  import {
    setSequencePlaying,
    stopCurrent,
    playOnce,
  } from '$lib/data/audio';
  import { popup } from '$lib/state/popup.svelte';
  import RubyHeader from '$lib/ui/RubyHeader.svelte';
  import TokenEl from '$lib/ui/Token.svelte';
  import { firstOccurrenceInSentences } from '$lib/util/first-occurrence';
  import {
    isStoryUnlocked,
    highestUnlockedStory,
  } from '$lib/util/story-progression';
  import { mintCardsForStory } from '$lib/state/srs';
  import { countDueCards, nextDueChangeTimestamp } from '$lib/util/due-count';
  import type { Story, VocabIndex } from '$lib/data/types';

  let story = $state<Story | null>(null);
  let glossVisible = $state(false);
  let storyError = $state<string | null>(null);
  let sequencePlayback = $state(false);
  let playingIdx = $state<number | null>(null);
  let vocabIndex = $state<VocabIndex | null>(null);

  let storyIdParam = $derived.by(() => {
    const s = page.url.searchParams.get('story');
    const n = s ? parseInt(s, 10) : NaN;
    return Number.isFinite(n) && n > 0 ? n : null;
  });

  $effect(() => {
    const requested = storyIdParam ?? learner.state.current_story ?? 1;
    if (story?.story_id === requested) return;
    storyError = null;
    // Strict graded-reader gate: a learner cannot deep-link past
    // unread material via the URL bar. If the requested story isn't
    // unlocked, silently redirect to the highest one they've earned.
    // We use a generous cap (10000) for highestUnlockedStory because
    // we don't know the manifest size from inside the read view; the
    // helper walks linearly until it hits a gap so the cap is just an
    // upper bound, never the answer for any real progress shape.
    if (!isStoryUnlocked(requested, learner.state.story_progress)) {
      const allowed = highestUnlockedStory(learner.state.story_progress, 10000);
      if (allowed !== requested) {
        goto(`${base}/read?story=${allowed}`, { replaceState: true });
        return;
      }
    }
    loadStoryById(requested).then((s) => {
      if (!s) {
        storyError = `Could not load story ${requested}.`;
        return;
      }
      story = s;
      learner.state.current_story = s.story_id;
      learner.save();
      const target = `${base}/read?story=${s.story_id}`;
      const path = page.url.pathname + page.url.search;
      const expected = target.replace(base, '');
      if (path !== expected) {
        goto(target, { replaceState: true, keepFocus: true, noScroll: true });
      }
    });
  });

  // Vocab index loaded once for the new-words chips.
  loadVocabIndex().then((vi) => (vocabIndex = vi));

  let progress = $derived(story ? learner.state.story_progress[String(story.story_id)] : undefined);
  let completed = $derived(!!progress?.completed);

  let sentenceBlocks = $derived.by(() => {
    if (!story) return [];
    return story.sentences.map((s, i) => ({
      idx: i,
      tokens: s.tokens,
      gloss: s.gloss_en,
      audio: s.audio,
    }));
  });

  let newWordRows = $derived.by(() => {
    if (!story || !vocabIndex) return [];
    const lookup = new Map(vocabIndex.words.map((r) => [r.id, r]));
    return story.new_words
      .map((wid) => lookup.get(wid))
      .filter((r): r is NonNullable<typeof r> => !!r);
  });

  // Map of sentenceIdx → Set<tokenIdx> for tokens that are the FIRST
  // occurrence of their word_id in the BODY (the title has its own
  // independent scope owned by RubyHeader — see firstOccurrenceInTokens).
  // Drives the red first-occurrence underline via <Token isFirstInStory>.
  let firstOccurrence = $derived.by(() =>
    firstOccurrenceInSentences(story?.sentences),
  );

  function openWord(wordId: string, tok: any) {
    popup.openWord(wordId, tok);
  }
  function openGrammar(gid: string) {
    popup.openGrammar(gid);
  }

  function playStory() {
    if (!story) return;
    if (sequencePlayback) {
      sequencePlayback = false;
      setSequencePlaying(false);
      stopCurrent();
      playingIdx = null;
      return;
    }
    sequencePlayback = true;
    setSequencePlaying(true);
    playFrom(0);
  }

  function playFrom(i: number) {
    if (!story || !sequencePlayback || i >= story.sentences.length) {
      sequencePlayback = false;
      setSequencePlaying(false);
      playingIdx = null;
      return;
    }
    const sent = story.sentences[i];
    if (!sent.audio) {
      playFrom(i + 1);
      return;
    }
    playingIdx = i;
    playOnce(sent.audio, { onEnd: () => playFrom(i + 1) });
  }

  function playSentence(i: number) {
    if (!story) return;
    const sent = story.sentences[i];
    if (!sent.audio) return;
    // Plays exactly one sentence. The "▶ Play story" button is the
    // dedicated affordance for sequential playback; per-sentence
    // triangles always play just the sentence the learner clicked,
    // which matches the intuitive single-tap → single-clip model.
    playingIdx = i;
    playOnce(sent.audio, { onEnd: () => (playingIdx = null) });
  }

  function showSentencePopup(i: number) {
    if (!story) return;
    popup.openSentence(story.story_id, i, story.sentences[i]);
  }

  function markAsRead() {
    if (!story) return;
    if (!learner.state.srs) learner.state.srs = {};
    // Mint fresh SRS cards for every new word in the story (skipping any
    // already in srs from a prior pass). All minted cards are due NOW —
    // the menu's review badge and the in-page "N due word here" CTA both
    // filter by isDue, so any future-`due` shove would silently hide
    // freshly-saved words from the learner. See mintCardsForStory's
    // doc comment for the full rationale.
    learner.state.srs = mintCardsForStory(story, learner.state.srs, new Date());
    if (!learner.state.story_progress) learner.state.story_progress = {};
    learner.state.story_progress[String(story.story_id)] = { completed: true };
    learner.save();
  }

  // Story-level "review N due here?" CTA.
  // Real-time-correct due-count for the in-page "N due word here —
  // review now" CTA. Same event-driven pattern as the menu badge in
  // +layout.svelte (commit 9ba37dc): a reactive nowTick advances at
  // the EXACT moment the next card becomes due, no polling, no
  // staleness, zero wakeups when no cards are pending.
  //
  // We compute the story's "slice" of the srs map first — only cards
  // for words that actually appear in this story — and feed that
  // slice to both helpers. That way the CTA's wakeup schedule is
  // scoped to the story; cards in OTHER stories don't trigger
  // unrelated re-renders of this view.
  let nowTick = $state(Date.now());
  let storySrsSlice = $derived.by(() => {
    if (!story || !learner.state.srs) return {};
    const slice: Record<string, NonNullable<typeof learner.state.srs>[string]> = {};
    const seen = new Set<string>();
    for (const sent of story.sentences) {
      for (const tok of sent.tokens) {
        const wid = tok.word_id;
        if (wid && !seen.has(wid)) {
          seen.add(wid);
          const card = learner.state.srs[wid];
          if (card) slice[wid] = card;
        }
      }
    }
    return slice;
  });
  let dueInThisStory = $derived(countDueCards(storySrsSlice, nowTick));

  $effect(() => {
    const target = nextDueChangeTimestamp(storySrsSlice, nowTick);
    if (target === null) return;
    const wait = Math.max(100, target - Date.now());
    const id = setTimeout(() => {
      nowTick = Date.now();
    }, wait);
    return () => clearTimeout(id);
  });

  function prevStory() {
    if (!story || story.story_id <= 1) return;
    // Stop any in-flight playback before navigating away. Without this,
    // a per-sentence ▶ click followed immediately by "← Previous" leaves
    // the previous story's audio bleeding into the new one until it ends
    // naturally, AND if the user was in sequential play mode the chain's
    // onEnd callback would call playFrom(i+1) against the OLD story
    // index map after the new story loaded — wrong sentence plays. Both
    // failure modes vanish if we cleanly stop before goto().
    stopCurrent();
    setSequencePlaying(false);
    sequencePlayback = false;
    playingIdx = null;
    goto(`${base}/read?story=${story.story_id - 1}`);
  }
  function nextStory() {
    if (!story) return;
    // Same cleanup as prevStory() — see its comment for the rationale.
    stopCurrent();
    setSequencePlaying(false);
    sequencePlayback = false;
    playingIdx = null;
    goto(`${base}/read?story=${story.story_id + 1}`);
  }
</script>

<div id="view-read" class="view active">
  {#if storyError}
    <p class="empty-state">{storyError}</p>
  {:else if !story}
    <p class="empty-state">Loading story…</p>
  {:else}
    <div class="story-header">
      <h1 class="story-title" id="story-title-jp" lang="ja">
        <RubyHeader title={story.title} onWord={openWord} onGrammar={openGrammar} />
      </h1>
      <p class="story-title-en">{story.title.en}</p>
      <div class="story-ornament">❧</div>
    </div>

    <div class="story-gloss-bar">
      <button
        class="btn-gloss-all"
        class:active={glossVisible}
        onclick={() => (glossVisible = !glossVisible)}
      >
        {glossVisible ? 'Hide English' : 'Show English'}
      </button>
      {#if dueInThisStory > 0}
        <a class="btn-review-cta" href="{base}/review">
          ↻ {dueInThisStory} due word{dueInThisStory === 1 ? '' : 's'} here — review now
        </a>
      {/if}
    </div>

    <div class="audio-controls" role="group" aria-label="Audio">
      <button
        id="btn-play-story"
        class="btn-audio"
        class:playing={sequencePlayback}
        onclick={playStory}
        title="Play whole story"
      >
        ▶ Play story
      </button>
    </div>

    <div id="sentences-container" class="story-body" lang="ja">
      {#each sentenceBlocks as sb, i (sb.idx)}
        <span
          class="sentence-wrap clickable"
          class:playing={playingIdx === sb.idx}
          data-sentence-idx={sb.idx}
          role="button"
          tabindex="0"
          onclick={() => showSentencePopup(sb.idx)}
          onkeydown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              showSentencePopup(sb.idx);
            }
          }}
        >
          {#each sb.tokens as tok, ti (`${ti}:${tok.t}`)}
            <!--
              Key is the (token-index, surface-text) pair, not just the
              index, so that re-renders triggered by reactive deps (e.g.
              firstOccurrence map updates, popup-state changes that
              re-mount the parent fragment) don't shift the wrong
              underline onto the wrong token. Pure index keying caused
              the "is_new" red underline to flicker between adjacent
              tokens during rapid popup open/close. Tokens within a
              single story never reorder, so the surface suffix is a
              stable disambiguator at zero render cost.
            -->
            <TokenEl
              {tok}
              isFirstInStory={firstOccurrence.get(sb.idx)?.has(ti) ?? false}
              onWord={openWord}
              onGrammar={openGrammar}
            />
          {/each}
          {#if sb.audio}
            <button
              class="sentence-audio-icon"
              aria-label={`Play sentence ${sb.idx + 1}`}
              onclick={(e) => {
                e.stopPropagation();
                playSentence(sb.idx);
              }}
            >▶</button>
          {/if}
        </span>
        {#if (i + 1) % 3 === 0 && i < sentenceBlocks.length - 1}
          <br /><span class="story-para-break"></span>
        {/if}
      {/each}
    </div>

    {#if glossVisible}
      <div id="gloss-panel" class="gloss-panel">
        {story.sentences.map((s) => s.gloss_en).join(' ')}
      </div>
    {/if}

    <div class="new-words-panel" id="new-words-panel">
      <h3 class="panel-label">New words</h3>
      <div class="new-words-chips" id="new-words-chips">
        {#each newWordRows as row (row.id)}
          <button class="word-chip" onclick={() => popup.openWord(row.id, undefined)}>
            <span class="word-chip-jp" lang="ja">{row.surface}</span>
            <span class="word-chip-en">{row.short_meaning}</span>
          </button>
        {/each}
      </div>
    </div>

    <button
      id="btn-mark-read"
      class="btn-mark-read"
      disabled={completed}
      onclick={markAsRead}
    >
      {completed ? '✓ Saved for review' : "I've read this — save new words for review"}
    </button>

    <div class="story-nav">
      <button
        class="story-nav-btn"
        disabled={story.story_id <= 1}
        onclick={prevStory}>← Previous</button
      >
      <span class="story-id-label">Story {story.story_id}</span>
      <button
        class="story-nav-btn"
        disabled={!completed}
        title={completed ? '' : 'Mark this story as read first'}
        onclick={nextStory}>Next →</button
      >
    </div>
  {/if}
</div>
