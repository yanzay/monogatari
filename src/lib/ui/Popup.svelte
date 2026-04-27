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

<style>
  .popup-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 200;
    backdrop-filter: blur(2px);
  }
  .popup {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 201;
    background: var(--bg);
    border-top: 1px solid var(--border);
    border-radius: var(--radius) var(--radius) 0 0;
    box-shadow: var(--shadow-lg);
    padding: 1.5rem 1.5rem 2rem;
    max-height: 70dvh;
    overflow-y: auto;
    animation: slideUp 0.22s ease-out;
  }
  @keyframes slideUp {
    from { transform: translateY(100%); opacity: 0; }
    to   { transform: translateY(0);    opacity: 1; }
  }
  @media (min-width: 600px) {
    .popup {
      top: 50%;
      left: 50%;
      bottom: auto;
      right: auto;
      transform: translate(-50%, -50%);
      width: min(560px, 92vw);
      max-height: min(80dvh, 720px);
      border-top: 1px solid var(--border);
      border-radius: var(--radius);
      animation: fadeScaleIn 0.18s ease-out;
    }
    @keyframes fadeScaleIn {
      from { opacity: 0; transform: translate(-50%, -50%) scale(0.96); }
      to   { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    }
  }
  .popup-close {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    background: none;
    border: none;
    font-size: 1rem;
    cursor: pointer;
    color: var(--text-muted);
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: background 0.15s;
  }
  .popup-close:hover { background: var(--surface2); }
</style>
