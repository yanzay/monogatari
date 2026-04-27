<script lang="ts">
  import { onMount } from 'svelte';
  import { loadGrammar, loadGrammarExamples } from '$lib/data/corpus';
  import { isGrammarEntryIncomplete } from '$lib/util/grammar';
  import type { GrammarState, GrammarPoint, GrammarExamplesIndex } from '$lib/data/types';

  let grammar = $state<GrammarState | null>(null);
  let examples = $state<GrammarExamplesIndex | null>(null);
  let openIds = $state<Set<string>>(new Set());

  onMount(async () => {
    [grammar, examples] = await Promise.all([loadGrammar(), loadGrammarExamples()]);
  });

  function toggle(gp: GrammarPoint) {
    const next = new Set(openIds);
    if (next.has(gp.id)) next.delete(gp.id);
    else next.add(gp.id);
    openIds = next;
  }
</script>

<div id="view-grammar" class="view active">
  <div class="grammar-list" id="grammar-list">
    {#if !grammar}
      <p class="empty-state">Loading…</p>
    {:else}
      {#each Object.values(grammar.points) as gp (gp.id)}
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
