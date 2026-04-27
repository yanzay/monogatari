<script lang="ts" generics="T">
  /**
   * Lightweight virtualized list. Renders only the visible window plus a
   * small overscan, computed from a fixed item height and the scroll
   * container's geometry. Designed for the Library and Vocab views, which
   * grow linearly with corpus size and previously rendered every row into
   * the DOM.
   *
   * No external dependencies, ~80 lines.
   */
  import type { Snippet } from 'svelte';

  interface Props {
    items: T[];
    /** Height of one row in CSS pixels. Must be constant. */
    itemHeight: number;
    /** Height of the scroll viewport. */
    height: number;
    /** Extra rows to render outside the viewport for smoother scrolling. */
    overscan?: number;
    children: Snippet<[T, number]>;
    /** Optional class for the outer scroll container. */
    class?: string;
  }
  let {
    items,
    itemHeight,
    height,
    overscan = 6,
    children,
    class: cls = '',
  }: Props = $props();

  let scrollTop = $state(0);
  let viewport = $state<HTMLDivElement | undefined>();

  let totalHeight = $derived(items.length * itemHeight);
  let firstVisible = $derived(Math.max(0, Math.floor(scrollTop / itemHeight) - overscan));
  let visibleCount = $derived(Math.ceil(height / itemHeight) + overscan * 2);
  let lastVisible = $derived(Math.min(items.length, firstVisible + visibleCount));
  let offsetTop = $derived(firstVisible * itemHeight);
  let visibleSlice = $derived(items.slice(firstVisible, lastVisible));

  function onScroll(e: Event) {
    scrollTop = (e.target as HTMLDivElement).scrollTop;
  }
</script>

<div
  class="vlist {cls}"
  style="height:{height}px;overflow-y:auto;position:relative;"
  bind:this={viewport}
  onscroll={onScroll}
>
  <div style="height:{totalHeight}px;position:relative;">
    <div style="position:absolute;top:{offsetTop}px;left:0;right:0;">
      {#each visibleSlice as item, i (firstVisible + i)}
        <div style="height:{itemHeight}px;">
          {@render children(item, firstVisible + i)}
        </div>
      {/each}
    </div>
  </div>
</div>
