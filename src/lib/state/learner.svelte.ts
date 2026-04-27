import { browser } from '$app/environment';
import { del, get, set } from 'idb-keyval';
import type { Card, ReviewLogEntry } from './types';
import { DEFAULT_TARGET_RETENTION } from './srs';

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
  'history',
  'daily',
] as const;

/**
 * Schema version. Bumping this drops *all* prior srs cards on next load:
 *   1 → original SM-2 with interval_days
 *   2 → SM-2 with interval_min (Phase A+B)
 *   3 → FSRS-5 with stability/difficulty (current)
 *
 * Migration policy: NONE. Per product call, transition from 2 → 3
 * resets srs + history + daily counters to empty. Story-completion
 * marks and prefs survive (so a learner doesn't lose their bookmark).
 */
const CURRENT_VERSION = 3;

export interface Prefs {
  show_gloss_by_default: boolean;
  audio_autoplay: boolean;
  audio_on_review_reveal: boolean;
  /**
   * Listening-first review mode.
   *
   * When true: on each review card, the sentence text is hidden and the
   * word audio autoplays. The user must recall the word from sound alone
   * before pressing reveal. Drills aural recognition with zero added
   * review volume — the same recognition card is just answered from a
   * different cue. Cards lacking audio fall back to the normal text-first
   * presentation.
   */
  audio_listen_first: boolean;
  theme?: 'auto' | 'light' | 'dark';
  target_retention: number;
  daily_max_new: number;
  daily_max_reviews: number;
  new_per_review: number;
}

export interface DailyCounters {
  /** Local-date string YYYY-MM-DD. Used to roll counters at midnight. */
  date: string;
  reviewed: number;
  new_introduced: number;
}

export interface LearnerState {
  version: number;
  current_story: number;
  last_opened: string;
  srs: Record<string, Card>;
  story_progress: Record<string, { completed: boolean }>;
  prefs: Prefs;
  /** Append-only review log (capped). Last entry is most recent. */
  history: ReviewLogEntry[];
  daily: DailyCounters;
}

const HISTORY_CAP = 500;

function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function defaultPrefs(): Prefs {
  return {
    show_gloss_by_default: false,
    audio_autoplay: false,
    audio_on_review_reveal: true,
    audio_listen_first: false,
    theme: 'auto',
    target_retention: DEFAULT_TARGET_RETENTION,
    daily_max_new: 20,
    daily_max_reviews: 200,
    new_per_review: 4,
  };
}

function defaultDaily(): DailyCounters {
  return { date: todayLocal(), reviewed: 0, new_introduced: 0 };
}

function defaultState(): LearnerState {
  return {
    version: CURRENT_VERSION,
    current_story: 1,
    last_opened: new Date().toISOString(),
    srs: {},
    story_progress: {},
    prefs: defaultPrefs(),
    history: [],
    daily: defaultDaily(),
  };
}

/**
 * Sanitize raw input into a LearnerState.
 *
 * Keys outside ALLOWED_KEYS are dropped. Cards from older schema
 * versions are NOT migrated (per product decision); the entire srs +
 * history is reset on version mismatch.
 */
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
      case 'srs':
        // Only accept SRS if version matches; otherwise drop on the floor.
        if (typeof r.version === 'number' && r.version === CURRENT_VERSION && typeof value === 'object') {
          out.srs = sanitizeSrs(value as Record<string, unknown>);
        }
        break;
      case 'history':
        if (typeof r.version === 'number' && r.version === CURRENT_VERSION && Array.isArray(value)) {
          out.history = (value as ReviewLogEntry[]).filter(isValidHistoryEntry).slice(-HISTORY_CAP);
        }
        break;
      case 'daily':
        if (value && typeof value === 'object') {
          const d = value as Record<string, unknown>;
          if (typeof d.date === 'string' && d.date === todayLocal()) {
            out.daily = {
              date: d.date,
              reviewed: typeof d.reviewed === 'number' ? d.reviewed : 0,
              new_introduced: typeof d.new_introduced === 'number' ? d.new_introduced : 0,
            };
          }
        }
        break;
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
          ...defaultPrefs(),
          show_gloss_by_default: !!p.show_gloss_by_default,
          audio_autoplay: !!p.audio_autoplay,
          audio_on_review_reveal:
            typeof p.audio_on_review_reveal === 'boolean' ? p.audio_on_review_reveal : true,
          audio_listen_first:
            typeof p.audio_listen_first === 'boolean' ? p.audio_listen_first : false,
          theme:
            p.theme === 'light' || p.theme === 'dark' || p.theme === 'auto'
              ? p.theme
              : 'auto',
          target_retention:
            typeof p.target_retention === 'number' &&
            p.target_retention >= 0.7 &&
            p.target_retention <= 0.99
              ? p.target_retention
              : DEFAULT_TARGET_RETENTION,
          daily_max_new:
            typeof p.daily_max_new === 'number' && p.daily_max_new >= 0
              ? Math.floor(p.daily_max_new)
              : 20,
          daily_max_reviews:
            typeof p.daily_max_reviews === 'number' && p.daily_max_reviews >= 0
              ? Math.floor(p.daily_max_reviews)
              : 200,
          new_per_review:
            typeof p.new_per_review === 'number' && p.new_per_review >= 0
              ? Math.floor(p.new_per_review)
              : 4,
        };
        break;
      }
    }
  }
  // Force version to current; we already dropped any incompatible srs.
  out.version = CURRENT_VERSION;
  return out;
}

function sanitizeSrs(raw: Record<string, unknown>): Record<string, Card> {
  const out: Record<string, Card> = {};
  for (const [wid, card] of Object.entries(raw)) {
    if (!card || typeof card !== 'object') continue;
    const c = card as any;
    // Minimum field check; FSRS cards must have these.
    if (
      typeof c.stability !== 'number' ||
      typeof c.difficulty !== 'number' ||
      typeof c.due !== 'string'
    ) {
      continue;
    }
    out[wid] = { ...c, word_id: wid };
  }
  return out;
}

function isValidHistoryEntry(e: any): e is ReviewLogEntry {
  return (
    e &&
    typeof e === 'object' &&
    typeof e.word_id === 'string' &&
    typeof e.grade === 'number' &&
    typeof e.reviewed_at === 'string' &&
    e.card_before &&
    e.card_after
  );
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
  // 2. Migrate from localStorage (one-shot). Only useful for installs
  // that pre-date IDB. New users skip this entirely.
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
    this.rolloverDailyIfNeeded();
    this.ready = true;
  }

  /** Reset daily counters if local date has rolled. */
  rolloverDailyIfNeeded(): void {
    const today = todayLocal();
    if (this.state.daily.date !== today) {
      this.state.daily = { date: today, reviewed: 0, new_introduced: 0 };
    }
  }

  /** Append a review-log entry, capped at HISTORY_CAP. */
  pushHistory(entry: ReviewLogEntry): void {
    this.state.history.push(entry);
    if (this.state.history.length > HISTORY_CAP) {
      this.state.history.splice(0, this.state.history.length - HISTORY_CAP);
    }
    this.state.daily.reviewed += 1;
  }

  /** Pop the last review off history, restoring the prior card snapshot.
   *  Returns the restored entry so the caller can re-display it, or null. */
  popHistory(): ReviewLogEntry | null {
    const entry = this.state.history.pop();
    if (!entry) return null;
    this.state.srs[entry.word_id] = entry.card_before;
    if (this.state.daily.reviewed > 0) this.state.daily.reviewed -= 1;
    return entry;
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

  /**
   * Wipe all learner data. Caller is responsible for confirming with the user
   * BEFORE invoking this.
   */
  async resetAll(): Promise<void> {
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    if (browser) {
      try {
        await del(IDB_KEY);
      } catch (e) {
        console.warn('Failed to delete learner state from IDB:', e);
      }
      try {
        localStorage.removeItem(LS_KEY);
        localStorage.removeItem(TOMBSTONE);
      } catch {
        /* ignore — localStorage may be disabled */
      }
    }
    this.state = defaultState();
  }
}

export const learner = new LearnerStore();
