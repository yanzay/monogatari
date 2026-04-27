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
  import { newCard, dribbleOffset, isDue } from '$lib/state/srs';
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
    if (learner.state.prefs.audio_autoplay) {
      sequencePlayback = true;
      setSequencePlaying(true);
      playFrom(i);
    } else {
      playingIdx = i;
      playOnce(sent.audio, { onEnd: () => (playingIdx = null) });
    }
  }

  function showSentencePopup(i: number) {
    if (!story) return;
    popup.openSentence(story.story_id, i, story.sentences[i]);
  }

  function markAsRead() {
    if (!story) return;
    if (!learner.state.srs) learner.state.srs = {};
    const now = Date.now();
    let i = 0;
    // Dribble: stagger `due` times so a 30-word story doesn't dump all
    // 30 cards into the next review session at the exact same instant.
    for (const wid of story.new_words) {
      if (learner.state.srs[wid]) continue;
      const sentIdx = story.sentences.findIndex((s) => s.tokens.some((t) => t.word_id === wid));
      const card = newCard({
        word_id: wid,
        story_id: story.story_id,
        context_sentence_idx: sentIdx,
      });
      // Push due forward by a few minutes per card.
      const dueMs = now + dribbleOffset(i);
      card.due = new Date(dueMs).toISOString();
      learner.state.srs[wid] = card;
      i += 1;
    }
    if (!learner.state.story_progress) learner.state.story_progress = {};
    learner.state.story_progress[String(story.story_id)] = { completed: true };
    learner.save();
  }

  // Story-level "review N due here?" CTA.
  let dueInThisStory = $derived.by(() => {
    if (!story || !learner.state.srs) return 0;
    const idsInStory = new Set<string>();
    for (const sent of story.sentences) {
      for (const tok of sent.tokens) {
        if (tok.word_id) idsInStory.add(tok.word_id);
      }
    }
    let n = 0;
    for (const id of idsInStory) {
      const card = learner.state.srs[id];
      if (card && isDue(card)) n += 1;
    }
    return n;
  });

  function prevStory() {
    if (!story || story.story_id <= 1) return;
    goto(`${base}/read?story=${story.story_id - 1}`);
  }
  function nextStory() {
    if (!story) return;
    goto(`${base}/read?story=${story.story_id + 1}`);
  }
</script>

<div id="view-read" class="view active">
  {#if storyError}
    <p class="empty-state" style="padding:2rem;">{storyError}</p>
  {:else if !story}
    <p class="empty-state" style="padding:2rem;">Loading story…</p>
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
      <label class="autoplay-toggle">
        <input
          type="checkbox"
          checked={learner.state.prefs.audio_autoplay}
          onchange={(e) => {
            learner.state.prefs.audio_autoplay = (e.target as HTMLInputElement).checked;
            learner.save();
          }}
        />
        <span>Autoplay next sentence</span>
      </label>
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
          {#each sb.tokens as tok, ti (ti)}
            <TokenEl {tok} onWord={openWord} onGrammar={openGrammar} />
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
      {completed ? '✓ Already added to review' : 'Mark as read → add to SRS'}
    </button>

    <div class="story-nav">
      <button
        class="story-nav-btn"
        disabled={story.story_id <= 1}
        onclick={prevStory}>← Previous</button
      >
      <span class="story-id-label">Story {story.story_id}</span>
      <button class="story-nav-btn" onclick={nextStory}>Next →</button>
    </div>
  {/if}
</div>
