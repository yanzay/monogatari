<script lang="ts">
  import { onMount } from 'svelte';
  import { learner } from '$lib/state/learner.svelte';
  import { loadVocab, loadStoryById } from '$lib/data/corpus';
  import { applyGrade, isDue, type Card, type Grade } from '$lib/state/srs';
  import type { VocabState, Sentence, Story } from '$lib/data/types';

  let vocab = $state<VocabState | null>(null);
  let queue = $state<Card[]>([]);
  let idx = $state(0);
  let revealed = $state(false);
  let contextSentence = $state<Sentence | null>(null);

  onMount(async () => {
    vocab = await loadVocab();
    rebuildQueue();
  });

  function rebuildQueue() {
    queue = Object.values(learner.state.srs ?? {}).filter((c) => isDue(c));
    idx = 0;
    revealed = false;
    if (queue.length) loadContext();
  }

  let card = $derived<Card | null>(queue[idx] ?? null);
  let word = $derived(card && vocab ? vocab.words[card.word_id] : null);

  $effect(() => {
    if (card) loadContext();
  });

  async function loadContext() {
    contextSentence = null;
    if (!card || !vocab) return;
    let storyId: number | null = card.context_story ?? null;
    // Backfill from word.first_story for legacy cards
    const w = vocab.words[card.word_id];
    if ((!storyId || storyId === card.first_learned_story) && w?.first_story) {
      storyId = Number(w.first_story);
    }
    if (!storyId) return;
    const story = await loadStoryById(storyId);
    if (!story) return;
    const exact = story.sentences[card.context_sentence_idx];
    if (exact && exact.tokens.some((t) => t.word_id === card.word_id)) {
      contextSentence = exact;
      return;
    }
    contextSentence = story.sentences.find((s) => s.tokens.some((t) => t.word_id === card.word_id)) ?? null;
  }

  function grade(g: Grade) {
    if (!card) return;
    const updated = applyGrade(card, g);
    learner.state.srs[card.word_id] = updated;
    learner.save();
    revealed = false;
    idx += 1;
    if (idx >= queue.length) rebuildQueue();
  }
</script>

<div id="view-review" class="view active">
  <div id="review-container" class="review-container">
    {#if !learner.ready || !vocab}
      <p class="empty-state">Loading…</p>
    {:else if !queue.length}
      <p class="empty-state">Nothing due. Read the next story or come back later.</p>
    {:else if !card || !word}
      <p class="empty-state">Session complete! Come back later.</p>
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
        <button class="btn-reveal" onclick={() => (revealed = true)}>Show answer</button>
      {:else}
        <div class="grade-buttons">
          <button class="grade-btn" onclick={() => grade(0)}>
            Again<span class="grade-label">&lt;10m</span>
          </button>
          <button class="grade-btn" onclick={() => grade(1)}>
            Hard<span class="grade-label">×1.2</span>
          </button>
          <button class="grade-btn" onclick={() => grade(2)}>
            Good<span class="grade-label">✓</span>
          </button>
          <button class="grade-btn" onclick={() => grade(3)}>
            Easy<span class="grade-label">×1.3</span>
          </button>
        </div>
      {/if}
    {/if}
  </div>
</div>
