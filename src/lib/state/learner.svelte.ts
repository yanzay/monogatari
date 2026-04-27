import { browser } from '$app/environment';
import { get, set } from 'idb-keyval';
import { migrateCard, type Card } from './srs';

const IDB_KEY = 'monogatari_learner';
const LS_KEY = 'monogatari_learner';
const TOMBSTONE = 'monogatari_learner__migrated_to_idb';

const ALLOWED_KEYS = [
  'version',
  'current_story',
  'last_opened',
  'srs',
  'story_progress',
  'prefs',
] as const;

export interface Prefs {
  show_gloss_by_default: boolean;
  audio_autoplay: boolean;
  theme?: 'auto' | 'light' | 'dark';
}

export interface LearnerState {
  version: number;
  current_story: number;
  last_opened: string;
  srs: Record<string, Card>;
  story_progress: Record<string, { completed: boolean }>;
  prefs: Prefs;
}

function defaultState(): LearnerState {
  return {
    version: 2,
    current_story: 1,
    last_opened: new Date().toISOString(),
    srs: {},
    story_progress: {},
    prefs: {
      show_gloss_by_default: false,
      audio_autoplay: false,
      theme: 'auto',
    },
  };
}

export function sanitizeImported(raw: unknown): LearnerState {
  if (!raw || typeof raw !== 'object') {
    throw new Error('Imported state is not an object');
  }
  const r = raw as Record<string, unknown>;
  const out = defaultState();
  for (const key of ALLOWED_KEYS) {
    if (!(key in r)) continue;
    const value = r[key];
    if (value === null || value === undefined) continue;
    switch (key) {
      case 'version':
        out.version = typeof value === 'number' ? value : out.version;
        break;
      case 'current_story':
        out.current_story = typeof value === 'number' ? value : out.current_story;
        break;
      case 'last_opened':
        out.last_opened = typeof value === 'string' ? value : out.last_opened;
        break;
      case 'srs': {
        const srs: Record<string, Card> = {};
        if (value && typeof value === 'object') {
          for (const [wid, card] of Object.entries(value as Record<string, unknown>)) {
            if (!card || typeof card !== 'object') continue;
            try {
              srs[wid] = migrateCard({ word_id: wid, ...(card as object) });
            } catch {
              /* skip malformed card */
            }
          }
        }
        out.srs = srs;
        break;
      }
      case 'story_progress': {
        const sp: Record<string, { completed: boolean }> = {};
        if (value && typeof value === 'object') {
          for (const [sid, p] of Object.entries(value as Record<string, unknown>)) {
            if (p && typeof p === 'object' && (p as any).completed) {
              sp[sid] = { completed: true };
            }
          }
        }
        out.story_progress = sp;
        break;
      }
      case 'prefs': {
        const p = value as Record<string, unknown>;
        out.prefs = {
          show_gloss_by_default: !!p.show_gloss_by_default,
          audio_autoplay: !!p.audio_autoplay,
          theme:
            p.theme === 'light' || p.theme === 'dark' || p.theme === 'auto'
              ? p.theme
              : 'auto',
        };
        break;
      }
    }
  }
  // Migrate any pre-existing srs cards already on `out.srs` (no-op for new objects).
  for (const [wid, card] of Object.entries(out.srs)) {
    out.srs[wid] = migrateCard(card);
  }
  return out;
}

async function loadFromStorage(): Promise<LearnerState> {
  if (!browser) return defaultState();
  // 1. IDB first.
  try {
    const fromIdb = await get<unknown>(IDB_KEY);
    if (fromIdb) return sanitizeImported(fromIdb);
  } catch {
    /* fall through */
  }
  // 2. Migrate from localStorage (one-shot).
  try {
    const tombstone = localStorage.getItem(TOMBSTONE);
    const raw = localStorage.getItem(LS_KEY);
    if (raw && !tombstone) {
      const parsed = JSON.parse(raw);
      const sanitized = sanitizeImported(parsed);
      try {
        await set(IDB_KEY, sanitized);
        localStorage.setItem(TOMBSTONE, new Date().toISOString());
      } catch {
        /* IDB write failed; we still return the parsed state */
      }
      return sanitized;
    }
  } catch {
    /* corrupt localStorage; ignore */
  }
  return defaultState();
}

/* ── Reactive store (Svelte 5 runes) ─────────────────────────────── */

class LearnerStore {
  state = $state<LearnerState>(defaultState());
  ready = $state(false);
  private saveTimer: ReturnType<typeof setTimeout> | null = null;

  async init(): Promise<void> {
    if (this.ready) return;
    this.state = await loadFromStorage();
    this.ready = true;
  }

  /** Debounced persist to IndexedDB. */
  save(): void {
    if (!browser) return;
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(async () => {
      this.state.last_opened = new Date().toISOString();
      try {
        await set(IDB_KEY, $state.snapshot(this.state));
      } catch (e) {
        console.warn('Failed to persist learner state:', e);
      }
    }, 500);
  }

  replace(next: LearnerState): void {
    this.state = next;
    this.save();
  }

  exportJSON(): string {
    return JSON.stringify($state.snapshot(this.state), null, 2);
  }
}

export const learner = new LearnerStore();
