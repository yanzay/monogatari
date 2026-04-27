<script lang="ts">
  import { onMount } from 'svelte';
  import { loadGrammar, loadManifest, loadStoryById } from '$lib/data/corpus';
  import { isGrammarEntryIncomplete } from '$lib/util/grammar';
  import type { GrammarState, GrammarPoint, Story } from '$lib/data/types';

  let grammar = $state<GrammarState | null>(null);
  let openIds = $state<Set<string>>(new Set());
  let examplesByGrammar = $state<Record<string, ExampleRow[]>>({});
  let exampleLoading = $state<Record<string, boolean>>({});
  let manifestLoaded = $state(false);

  interface ExampleRow {
    story_id: number;
    sentence_idx: number;
    jp: string;
    gloss_en: string;
  }

  onMount(async () => {
    grammar = await loadGrammar();
  });

  async function loadExamplesFor(gid: string) {
    if (examplesByGrammar[gid] || exampleLoading[gid]) return;
    exampleLoading = { ...exampleLoading, [gid]: true };
    // Lazy crawl: first time anyone opens any example accordion, fetch the
    // manifest and crawl through stories. Cap at 5 examples.
    // (Phase C will replace this with a build-time grammar_examples.json.)
    if (!manifestLoaded) {
      const manifest = await loadManifest();
      const found: Record<string, ExampleRow[]> = {};
      for (const entry of manifest.stories) {
        const s = await loadStoryById(entry.story_id);
        if (!s) continue;
        s.sentences.forEach((sent, idx) => {
          const gset = new Set<string>();
          for (const tok of sent.tokens) {
            if (tok.grammar_id) gset.add(tok.grammar_id);
            if (tok.inflection?.grammar_id) gset.add(tok.inflection.grammar_id);
          }
          for (const g of gset) {
            (found[g] ??= []).push({
              story_id: s.story_id,
              sentence_idx: idx,
              jp: sent.tokens.map((t) => t.t).join(''),
              gloss_en: sent.gloss_en,
            });
          }
        });
      }
      examplesByGrammar = found;
      manifestLoaded = true;
    }
    exampleLoading = { ...exampleLoading, [gid]: false };
  }

  function toggle(gp: GrammarPoint) {
    const next = new Set(openIds);
    if (next.has(gp.id)) {
      next.delete(gp.id);
    } else {
      next.add(gp.id);
      loadExamplesFor(gp.id);
    }
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
            <div class="grammar-examples">
              {#if isOpen}
                {#if exampleLoading[gp.id]}
                  <small>loading examples…</small>
                {:else}
                  {@const exs = (examplesByGrammar[gp.id] ?? []).slice(0, 5)}
                  {#if exs.length}
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
                {/if}
              {/if}
            </div>
          </div>
        </div>
      {/each}
    {/if}
  </div>
</div>
