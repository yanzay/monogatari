<script lang="ts">
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';

  interface Props {
    open: boolean;
    onClose: () => void;
    children: Snippet;
    title?: string;
  }
  let { open, onClose, children, title = 'Detail' }: Props = $props();

  let popupEl: HTMLDivElement | undefined = $state();
  let lastFocused: HTMLElement | null = null;

  $effect(() => {
    if (open) {
      lastFocused = document.activeElement as HTMLElement | null;
      // Focus the first focusable child after the popup paints
      queueMicrotask(() => {
        const focusable = popupEl?.querySelector<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        (focusable ?? popupEl)?.focus();
      });
    } else if (lastFocused && document.contains(lastFocused)) {
      lastFocused.focus();
      lastFocused = null;
    }
  });

  function onKey(e: KeyboardEvent) {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== 'Tab' || !popupEl) return;
    const focusables = Array.from(
      popupEl.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute('disabled'));
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  onMount(() => {
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });
</script>

{#if open}
  <div
    class="popup-overlay"
    onclick={onClose}
    onkeydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClose();
      }
    }}
    role="presentation"
  ></div>
  <div
    class="popup"
    role="dialog"
    aria-modal="true"
    aria-label={title}
    bind:this={popupEl}
    tabindex="-1"
  >
    <button class="popup-close" onclick={onClose} aria-label="Close">✕</button>
    <div class="popup-content">
      {@render children()}
    </div>
  </div>
{/if}
