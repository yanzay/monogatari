<script lang="ts">
  import { onMount } from 'svelte';
  import { loadGrammar, loadGrammarExamples } from '$lib/data/corpus';
  import { isGrammarEntryIncomplete } from '$lib/util/grammar';
  import { isSeenGrammar } from '$lib/util/known-filters';
  import type { GrammarState, GrammarPoint, GrammarExamplesIndex } from '$lib/data/types';

  let grammar = $state<GrammarState | null>(null);
  let examples = $state<GrammarExamplesIndex | null>(null);
  let openIds = $state<Set<string>>(new Set());
  // Default to the grammar points the learner has actually
  // encountered — i.e. those introduced by some shipped story
  // (intro_in_story is set). The full catalog (currently 49 points,
  // many JLPT N4/N3 placeholders not yet on-curriculum) is available
  // behind a "Show all" toggle for the curious.
  let showAll = $state(false);

  onMount(async () => {
    [grammar, examples] = await Promise.all([loadGrammar(), loadGrammarExamples()]);
  });

  let allPoints = $derived<GrammarPoint[]>(
    grammar ? Object.values(grammar.points) : [],
  );
  let visiblePoints = $derived<GrammarPoint[]>(
    showAll ? allPoints : allPoints.filter(isSeenGrammar),
  );

  function toggle(gp: GrammarPoint) {
    const next = new Set(openIds);
    if (next.has(gp.id)) next.delete(gp.id);
    else next.add(gp.id);
    openIds = next;
  }
</script>

<div id="view-grammar" class="view active">
  <div class="grammar-toolbar">
    <label class="grammar-show-all" title="Include grammar points the corpus hasn't introduced yet">
      <input type="checkbox" bind:checked={showAll} />
      <span>Show all ({allPoints.length})</span>
    </label>
  </div>
  <div class="grammar-list" id="grammar-list">
    {#if !grammar}
      <p class="empty-state">Loading…</p>
    {:else if visiblePoints.length === 0 && !showAll}
      <p class="empty-state">
        You haven't encountered any grammar yet. Read a story to see the
        first grammar point — or
        <button class="link-button" type="button" onclick={() => (showAll = true)}>
          show all {allPoints.length} grammar points in the corpus
        </button>.
      </p>
    {:else}
      {#each visiblePoints as gp (gp.id)}
        {@const incomplete = isGrammarEntryIncomplete(gp)}
        {@const isOpen = openIds.has(gp.id)}
        {@const exs = (examples?.examples?.[gp.id] ?? []).slice(0, 5)}
        <div class="grammar-item" class:incomplete class:open={isOpen}>
          <button
            class="grammar-item-header"
            onclick={() => toggle(gp)}
            aria-expanded={isOpen}
          >
            <span class="grammar-item-id">{gp.id}</span>
            <span class="grammar-item-title">{gp.title || '(no title)'}</span>
            {#if incomplete}
              <span class="badge-warn-inline" title="Definition is missing">⚠</span>
            {/if}
            <span class="grammar-item-chevron">▼</span>
          </button>
          <div class="grammar-item-body">
            {#if incomplete}
              <p class="grammar-incomplete-note">
                This grammar entry is incomplete. Update <code>data/grammar_state.json</code>.
              </p>
            {/if}
            <p class="grammar-item-short">{gp.short || '(no short description)'}</p>
            <p class="grammar-item-long">{gp.long || '(no long description)'}</p>
            {#if gp.genki_ref}<p class="grammar-genki">Genki {gp.genki_ref}</p>{/if}
            {#if isOpen}
              <div class="grammar-examples">
                {#if !examples}
                  <small>loading examples…</small>
                {:else if exs.length}
                  {#each exs as ex (ex.story_id + ':' + ex.sentence_idx)}
                    <div class="grammar-example">
                      <small>S{ex.story_id}·{ex.sentence_idx + 1}</small>
                      <span lang="ja">{ex.jp}</span>
                      <div
                        style="font-family:var(--font-en);font-style:italic;font-size:0.78rem;color:var(--text-muted);margin-left:2.6rem;"
                      >
                        {ex.gloss_en}
                      </div>
                    </div>
                  {/each}
                {:else}
                  <small>No appearances yet.</small>
                {/if}
              </div>
            {/if}
          </div>
        </div>
      {/each}
    {/if}
  </div>
</div>
