<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';
  import { learner } from '$lib/state/learner.svelte';
  import { loadStoryById, loadVocab, loadGrammar } from '$lib/data/corpus';
  import {
    audioFor,
    isSequencePlaying,
    setSequencePlaying,
    stopCurrent,
    playOnce,
  } from '$lib/data/audio';
  import { popup } from '$lib/state/popup.svelte';
  import RubyHeader from '$lib/ui/RubyHeader.svelte';
  import TokenEl from '$lib/ui/Token.svelte';
  import { newCard } from '$lib/state/srs';
  import type { Story, VocabState } from '$lib/data/types';

  let story = $state<Story | null>(null);
  let glossVisible = $state(false);
  let storyError = $state<string | null>(null);
  let sequencePlayback = $state(false); // mirror of audio.ts module-level
  let playingIdx = $state<number | null>(null);
  let vocab = $state<VocabState | null>(null);

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
      // Sync URL
      const target = `${base}/read?story=${s.story_id}`;
      if (page.url.pathname + page.url.search !== target.replace(base, '')) {
        goto(target, { replaceState: true, keepFocus: true, noScroll: true });
      }
    });
  });

  onMount(async () => {
    vocab = await loadVocab();
  });

  let progress = $derived(story ? learner.state.story_progress[String(story.story_id)] : undefined);
  let completed = $derived(!!progress?.completed);

  // Group sentences into paragraphs of 3
  let sentenceBlocks = $derived.by(() => {
    if (!story) return [];
    const blocks: { idx: number; tokens: typeof story.sentences[0]['tokens']; gloss: string; audio?: string }[] = [];
    story.sentences.forEach((s, i) => {
      blocks.push({ idx: i, tokens: s.tokens, gloss: s.gloss_en, audio: s.audio });
    });
    return blocks;
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
    const sent = story.sentences[i];
    // Show via the popup controller — we render text in a small custom inline modal.
    // For simplicity: alert the gloss. (Future: dedicated SentencePopup component.)
    alert(`${sent.tokens.map((t) => t.t).join('')}\n\n${sent.gloss_en}`);
  }

  function markAsRead() {
    if (!story) return;
    if (!learner.state.srs) learner.state.srs = {};
    for (const wid of story.new_words) {
      if (learner.state.srs[wid]) continue;
      const sentIdx = story.sentences.findIndex((s) => s.tokens.some((t) => t.word_id === wid));
      learner.state.srs[wid] = newCard({
        word_id: wid,
        story_id: story.story_id,
        context_sentence_idx: sentIdx,
      });
    }
    if (!learner.state.story_progress) learner.state.story_progress = {};
    learner.state.story_progress[String(story.story_id)] = { completed: true };
    learner.save();
  }

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
        {#if vocab}
          {#each story.new_words as wid (wid)}
            {@const w = vocab.words[wid]}
            {#if w}
              <button class="word-chip" onclick={() => popup.openWord(wid, undefined)}>
                <span class="word-chip-jp" lang="ja">{w.surface}</span>
                <span class="word-chip-en">{w.meanings[0]}</span>
              </button>
            {/if}
          {/each}
        {/if}
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
