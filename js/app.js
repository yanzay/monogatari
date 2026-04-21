/**
 * Monogatari — M1 Reader App
 * Vanilla JS, no build step, ES modules.
 */

// ── State ────────────────────────────────────────────────────────
let vocabState   = null;   // data/vocab_state.json
let grammarState = null;   // data/grammar_state.json
let story        = null;   // stories/story_N.json
let learnerState = loadLearnerState();
let currentStoryId = learnerState.current_story ?? 1;

// ── Boot ─────────────────────────────────────────────────────────
const VALID_VIEWS = ['read', 'library', 'review', 'vocab', 'grammar'];

/**
 * Parse window.location.hash into { view, story }.
 * Format: `#view` or `#view?story=N` (e.g. `#vocab`, `#read?story=3`).
 * Falls back gracefully when the hash is empty or malformed.
 */
function parseHash() {
  const raw = (location.hash || '').replace(/^#/, '');
  if (!raw) return { view: null, story: null };
  const [viewPart, query] = raw.split('?');
  const view = VALID_VIEWS.includes(viewPart) ? viewPart : null;
  let story = null;
  if (query) {
    const params = new URLSearchParams(query);
    const s = parseInt(params.get('story') || '', 10);
    if (Number.isFinite(s) && s > 0) story = s;
  }
  return { view, story };
}

/**
 * Write `{ view, story }` into the URL hash without adding history entries
 * (we use replaceState so refresh picks up the same view but Back doesn't
 * step through every nav click).
 */
function setHash({ view, story }, { replace = true } = {}) {
  const next = `#${view}${(view === 'read' && story) ? `?story=${story}` : ''}`;
  if (location.hash === next) return;
  const url = location.pathname + location.search + next;
  if (replace) history.replaceState(null, '', url);
  else         history.pushState(null, '', url);
}

async function boot() {
  // Wire up popup close handlers now that DOM is ready
  document.getElementById('popup-close').addEventListener('click', closePopup);
  document.getElementById('popup-overlay').addEventListener('click', closePopup);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closePopup(); });

  try {
    [vocabState, grammarState] = await Promise.all([
      fetchJSON('data/vocab_state.json'),
      fetchJSON('data/grammar_state.json'),
    ]);

    // Initial view + story come from URL hash if present, else from
    // persisted learner state, else defaults.
    const fromHash = parseHash();
    const initialStory = fromHash.story ?? currentStoryId;
    const initialView  = fromHash.view  ?? 'read';

    await loadStory(initialStory);
    setupNav();
    setupExportImport();
    renderVocabView();
    renderGrammarView();
    renderReviewView();
    renderLibraryView();

    // Apply initial view (without re-pushing history)
    switchView(initialView, { updateHash: true, replace: true });

    // React to browser back/forward — keep view in sync with URL.
    window.addEventListener('popstate', async () => {
      const h = parseHash();
      if (h.story && h.story !== currentStoryId) {
        await loadStory(h.story);
        renderLibraryView();
      }
      switchView(h.view ?? 'read', { updateHash: false });
    });
  } catch (e) {
    console.error('Boot failed:', e);
    document.getElementById('sentences-container').textContent =
      'Error loading story data. Please serve via HTTP (not file://).';
  }
}

// ── Data loading ─────────────────────────────────────────────────
const MANIFEST_CACHE = { promise: null, value: null };

/**
 * Load `stories/index.json`. The pipeline regenerates it on every ship.
 * If the manifest is missing (older deploy), we transparently fall back
 * to a small HEAD-probe so the reader keeps working.
 */
async function loadStoryManifest() {
  if (MANIFEST_CACHE.value) return MANIFEST_CACHE.value;
  if (MANIFEST_CACHE.promise) return MANIFEST_CACHE.promise;
  MANIFEST_CACHE.promise = (async () => {
    try {
      const res = await fetch('stories/index.json');
      if (res.ok) {
        const data = await res.json();
        MANIFEST_CACHE.value = data;
        return data;
      }
    } catch { /* fall through to probe */ }
    // Fallback: HEAD-probe up to 50 stories.
    const stories = [];
    for (let n = 1; n <= 50; n++) {
      try {
        const r = await fetch(`stories/story_${n}.json`, { method: 'HEAD' });
        if (!r.ok) break;
        stories.push({ story_id: n, path: `stories/story_${n}.json` });
      } catch { break; }
    }
    const data = { version: 0, stories };
    MANIFEST_CACHE.value = data;
    return data;
  })();
  return MANIFEST_CACHE.promise;
}

// Cache per-story JSON so repeated review lookups don't re-hit the network.
// Service worker also caches these, but in-memory avoids the round trip.
const STORY_CACHE = new Map();   // story_id → Promise<story-json>

async function loadStoryById(id) {
  if (!id) return null;
  if (STORY_CACHE.has(id)) return STORY_CACHE.get(id);
  const p = (async () => {
    try { return await fetchJSON(`stories/story_${id}.json`); }
    catch { return null; }
  })();
  STORY_CACHE.set(id, p);
  return p;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
  return r.json();
}

async function loadStory(id) {
  try {
    story = await fetchJSON(`stories/story_${id}.json`);
    currentStoryId = id;
    learnerState.current_story = id;
    saveLearnerState();
    renderReadView();
    // Keep the URL hash in sync so a refresh re-opens this exact story.
    // Only update if we're on the read view (the hash for other views
    // should not silently change to read).
    const currentView = parseHash().view;
    if (currentView === null || currentView === 'read') {
      setHash({ view: 'read', story: id }, { replace: true });
    }
  } catch (e) {
    console.error(e);
  }
}

// ── Nav ───────────────────────────────────────────────────────────
function setupNav() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      switchView(view, { updateHash: true });
    });
  });
}

// ── Library view ──────────────────────────────────────────────────
async function renderLibraryView() {
  const grid = document.getElementById('library-grid');
  if (!grid) return;
  grid.innerHTML = '<p class="empty-state">Loading library…</p>';
  let manifest;
  try {
    manifest = await loadStoryManifest();
  } catch {
    grid.innerHTML = '<p class="empty-state">Could not load library.</p>';
    return;
  }
  if (!manifest.stories.length) {
    grid.innerHTML = '<p class="empty-state">No stories yet.</p>';
    return;
  }
  grid.innerHTML = '';
  for (const entry of manifest.stories) {
    const id        = entry.story_id;
    const isCurrent = id === currentStoryId;
    const progress  = learnerState.story_progress?.[id] ?? {};
    const sentencesRead = (progress.sentences_read ?? []).length;
    const totalSentences = entry.n_sentences ?? 0;
    const completed = !!progress.completed;
    const readingMin = estimateReadingMinutes(entry);
    const pct = totalSentences ? Math.round((sentencesRead / totalSentences) * 100) : 0;

    const card = document.createElement('div');
    card.className = 'story-card' + (isCurrent ? ' current' : '');
    card.innerHTML = `
      <span class="story-card-id">Story ${id}</span>
      <div class="story-card-title-jp">${entry.title_jp || `Story ${id}`}</div>
      <div class="story-card-title-en">${entry.title_en || ''}</div>
      <div class="story-card-progress" title="${sentencesRead}/${totalSentences} sentences"><span style="width:${pct}%"></span></div>
      <div class="story-card-meta">
        <span>${totalSentences} sentences · ~${readingMin} min</span>
        <span class="story-card-badge${completed ? ' done' : ''}">${completed ? '✓ done' : isCurrent ? 'reading' : 'unread'}</span>
      </div>
    `;
    card.addEventListener('click', async () => {
      await loadStory(id);
      switchView('read', { updateHash: true });
    });
    grid.appendChild(card);
  }
}

/** Reading-time heuristic for graded readers: ~25 content tokens per minute,
 *  with a 0.5-min floor so very short stories don't say "0 min". */
function estimateReadingMinutes(entry) {
  const tokens = entry.n_content_tokens ?? entry.n_sentences * 6 ?? 0;
  return Math.max(1, Math.round(tokens / 25));
}

function switchView(name, { updateHash = true, replace = true } = {}) {
  if (!VALID_VIEWS.includes(name)) name = 'read';
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const target = document.getElementById(`view-${name}`);
  if (target) target.classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.view === name);
  });
  if (updateHash) {
    setHash({ view: name, story: name === 'read' ? currentStoryId : null }, { replace });
  }
}

// ── Read View ─────────────────────────────────────────────────────
function renderReadView() {
  if (!story) return;

  // Header — build title/subtitle as interactive ruby tokens
  document.getElementById('story-title-en').textContent   = story.title.en;
  document.getElementById('story-id-label').textContent   = `Story ${story.story_id}`;

  const titleEl = document.getElementById('story-title-jp');
  titleEl.innerHTML = '';
  buildRubyHeader(story.title, titleEl);

  const subtitleEl = document.getElementById('story-subtitle-jp');
  subtitleEl.innerHTML = '';
  buildRubyHeader(story.subtitle, subtitleEl);

  // Story nav buttons (Next is gated until every sentence has been opened or
  // the story has been marked completed at least once).
  const progress = learnerState.story_progress?.[story.story_id] ?? {};
  const completed = !!progress.completed;
  const sentencesRead = new Set(progress.sentences_read ?? []);
  const allSentencesRead = sentencesRead.size >= story.sentences.length;

  const prevBtn = document.getElementById('btn-prev-story');
  const nextBtn = document.getElementById('btn-next-story');
  prevBtn.disabled = story.story_id <= 1;
  nextBtn.disabled = !(completed || allSentencesRead);
  nextBtn.title = nextBtn.disabled
    ? 'Open every sentence (or mark as read) to unlock the next story'
    : '';
  prevBtn.onclick = () => loadStory(currentStoryId - 1);
  nextBtn.onclick = () => loadStory(currentStoryId + 1);

  // Sentences container — declared before gloss closure so it's in scope
  const container = document.getElementById('sentences-container');

  // "EN translation" — toggle a paragraph below the story
  const glossPanel = document.getElementById('gloss-panel');
  glossPanel.textContent = story.sentences.map(s => s.gloss_en).join(' ');
  const glossBtn = document.getElementById('btn-gloss-all');
  let glossVisible = false;
  glossPanel.hidden = true;
  const newGlossBtn = glossBtn.cloneNode(true);
  glossBtn.parentNode.replaceChild(newGlossBtn, glossBtn);
  newGlossBtn.addEventListener('click', () => {
    glossVisible = !glossVisible;
    glossPanel.hidden = !glossVisible;
    newGlossBtn.classList.toggle('active', glossVisible);
  });

  container.innerHTML = '';

  // Track which word_ids have already appeared in this story
  const seenInStory = new Set();

  story.sentences.forEach((sentence, i) => {
    // Each sentence is an inline span — flows as book paragraph
    const wrap = document.createElement('span');
    wrap.className = 'sentence-wrap clickable';
    wrap.dataset.sentenceIdx = String(i);

    sentence.tokens.forEach(tok => {
      wrap.appendChild(buildTokenElement(tok, seenInStory));
      if (tok.word_id) seenInStory.add(tok.word_id);
    });

    // Click sentence → mark read + show its translation in popup
    wrap.addEventListener('click', e => {
      // Tokens handle their own popups; just record progress here.
      markSentenceRead(story.story_id, i);
      if (e.target.closest('.token.clickable')) return;
      showPopup(`
        <div style="font-family:var(--font-jp);font-size:1.4rem;margin-bottom:0.75rem;line-height:1.8;">${sentence.tokens.map(t => t.t).join('')}</div>
        <div style="font-family:var(--font-en);font-style:italic;font-size:1rem;color:var(--text-muted);">${sentence.gloss_en}</div>
      `);
    });

    container.appendChild(wrap);

    // Paragraph gap every 3 sentences
    if ((i + 1) % 3 === 0 && i < story.sentences.length - 1) {
      container.appendChild(document.createElement('br'));
      const gap = document.createElement('span');
      gap.className = 'story-para-break';
      container.appendChild(gap);
    }
  });

  // Sentence progress dots
  renderProgressDots();

  // Audio controls
  setupAudioControls();

  // New words panel
  renderNewWordsPanel();

  // "Mark as read" — adds new words to SRS queue
  renderMarkAsRead();
}

// ── Sentence progress ──────────────────────────────────────────────
function markSentenceRead(storyId, idx) {
  if (!learnerState.story_progress) learnerState.story_progress = {};
  const p = learnerState.story_progress[storyId] ?? {};
  const set = new Set(p.sentences_read ?? []);
  if (set.has(idx)) return;
  set.add(idx);
  p.sentences_read = Array.from(set).sort((a, b) => a - b);
  learnerState.story_progress[storyId] = p;
  saveLearnerState();
  renderProgressDots();
  // Re-evaluate Next gating without re-rendering the whole story
  const next = document.getElementById('btn-next-story');
  if (next && p.sentences_read.length >= story.sentences.length) {
    next.disabled = false;
    next.title = '';
  }
}

// ── Audio playback ─────────────────────────────────────────────────
const AUDIO_CACHE = new Map();   // src → HTMLAudioElement
const AUDIO_STATE = { current: null, sequencePlaying: false };

function getAudio(src) {
  if (!src) return null;
  let a = AUDIO_CACHE.get(src);
  if (!a) {
    a = new Audio(src);
    a.preload = 'auto';
    AUDIO_CACHE.set(src, a);
  }
  return a;
}

function stopCurrentAudio() {
  if (AUDIO_STATE.current) {
    try { AUDIO_STATE.current.pause(); AUDIO_STATE.current.currentTime = 0; } catch {}
    AUDIO_STATE.current = null;
  }
  document.querySelectorAll('.sentence-wrap.playing').forEach(el => el.classList.remove('playing'));
  const btn = document.getElementById('btn-play-story');
  if (btn) btn.classList.remove('playing');
}

function playSentenceAudio(sentenceIdx, { onEnd } = {}) {
  if (!story) return;
  const sent = story.sentences[sentenceIdx];
  if (!sent || !sent.audio) return;
  stopCurrentAudio();
  const a = getAudio(sent.audio);
  if (!a) return;
  AUDIO_STATE.current = a;
  const wrap = document.querySelector(`.sentence-wrap[data-sentence-idx="${sentenceIdx}"]`);
  if (wrap) wrap.classList.add('playing');
  // Mark read on play (counts toward progress + Next gating)
  markSentenceRead(story.story_id, sentenceIdx);
  a.onended = () => {
    if (wrap) wrap.classList.remove('playing');
    AUDIO_STATE.current = null;
    if (onEnd) onEnd();
  };
  a.currentTime = 0;
  a.play().catch(() => { /* user-gesture restrictions, fail silently */ });
}

function playStoryFromIndex(startIdx) {
  if (!story) return;
  AUDIO_STATE.sequencePlaying = true;
  const btn = document.getElementById('btn-play-story');
  if (btn) btn.classList.add('playing');
  const playNext = (i) => {
    if (!AUDIO_STATE.sequencePlaying || i >= story.sentences.length) {
      AUDIO_STATE.sequencePlaying = false;
      if (btn) btn.classList.remove('playing');
      return;
    }
    playSentenceAudio(i, { onEnd: () => playNext(i + 1) });
  };
  playNext(startIdx);
}

function playWordAudio(wordId) {
  if (!story?.word_audio?.[wordId]) return;
  const a = getAudio(story.word_audio[wordId]);
  if (!a) return;
  try { a.currentTime = 0; a.play(); } catch {}
}
// Expose to inline handlers (the popup HTML uses onclick="playWordAudio(...)")
window.playWordAudio = playWordAudio;

function setupAudioControls() {
  const playBtn  = document.getElementById('btn-play-story');
  const autoChk  = document.getElementById('chk-autoplay');
  if (autoChk) {
    autoChk.checked = !!(learnerState.prefs?.audio_autoplay);
    autoChk.onchange = () => {
      if (!learnerState.prefs) learnerState.prefs = {};
      learnerState.prefs.audio_autoplay = autoChk.checked;
      saveLearnerState();
    };
  }
  if (playBtn) {
    playBtn.onclick = () => {
      if (AUDIO_STATE.sequencePlaying) {
        AUDIO_STATE.sequencePlaying = false;
        stopCurrentAudio();
      } else {
        playStoryFromIndex(0);
      }
    };
  }
  // Add per-sentence ▶ icons
  document.querySelectorAll('.sentence-wrap').forEach(wrap => {
    const idx = Number(wrap.dataset.sentenceIdx);
    const sent = story.sentences[idx];
    if (!sent?.audio) return;
    const icon = document.createElement('span');
    icon.className = 'sentence-audio-icon';
    icon.textContent = '▶';
    icon.title = 'Play this sentence';
    icon.addEventListener('click', e => {
      e.stopPropagation();
      if (learnerState.prefs?.audio_autoplay) {
        AUDIO_STATE.sequencePlaying = true;
        const btn = document.getElementById('btn-play-story');
        if (btn) btn.classList.add('playing');
        const playFromHere = (i) => {
          if (!AUDIO_STATE.sequencePlaying || i >= story.sentences.length) {
            AUDIO_STATE.sequencePlaying = false;
            if (btn) btn.classList.remove('playing');
            return;
          }
          playSentenceAudio(i, { onEnd: () => playFromHere(i + 1) });
        };
        playFromHere(idx);
      } else {
        playSentenceAudio(idx);
      }
    });
    wrap.appendChild(icon);
  });
}

function renderProgressDots() {
  const dots = document.getElementById('progress-dots');
  if (!dots || !story) return;
  dots.innerHTML = '';
  const p = learnerState.story_progress?.[story.story_id] ?? {};
  const read = new Set(p.sentences_read ?? []);
  story.sentences.forEach((_, i) => {
    const dot = document.createElement('span');
    dot.className = 'progress-dot';
    if (read.has(i)) dot.classList.add('read');
    dot.title = `Sentence ${i + 1}${read.has(i) ? ' (read)' : ''}`;
    dot.addEventListener('click', () => {
      const wrap = document.querySelector(`.sentence-wrap[data-sentence-idx="${i}"]`);
      if (wrap) wrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    dots.appendChild(dot);
  });
}

function renderMarkAsRead() {
  const existing = document.getElementById('btn-mark-read');
  if (existing) existing.remove();

  const progress = learnerState.story_progress?.[story.story_id] ?? {};
  const alreadyDone = progress.completed;

  const btn = document.createElement('button');
  btn.id = 'btn-mark-read';
  btn.className = 'btn-mark-read';
  btn.textContent = alreadyDone ? '✓ Already added to review' : 'Mark as read → add to SRS';
  btn.disabled = alreadyDone;

  btn.addEventListener('click', () => {
    addStoryToSRS(story);
    if (!learnerState.story_progress) learnerState.story_progress = {};
    learnerState.story_progress[story.story_id] = { completed: true };
    saveLearnerState();
    btn.textContent = '✓ Added to review';
    btn.disabled = true;
    renderReviewView();
    renderVocabView();
  });

  // Insert before new-words-panel
  const panel = document.getElementById('new-words-panel');
  panel.parentNode.insertBefore(btn, panel);
}

function addStoryToSRS(s) {
  if (!learnerState.srs) learnerState.srs = {};
  s.new_words.forEach(wid => {
    if (learnerState.srs[wid]) return; // already in SRS
    // Find first context sentence containing this word
    const sentIdx = s.sentences.findIndex(sent =>
      sent.tokens.some(t => t.word_id === wid)
    );
    learnerState.srs[wid] = {
      word_id: wid,
      first_learned_story: s.story_id,
      context_story: s.story_id,
      context_sentence_idx: sentIdx,
      interval_days: 0,
      ease: 2.5,
      reps: 0,
      lapses: 0,
      due: new Date().toISOString(),
      status: 'new',
    };
  });
}

// Build interactive ruby tokens for title/subtitle from a {jp, en, tokens?} object.
// If no tokens array, fall back to a single ruby span using jp/kana fields.
function buildRubyHeader(titleObj, container) {
  if (titleObj.tokens) {
    const seen = new Set();
    titleObj.tokens.forEach(tok => {
      container.appendChild(buildTokenElement(tok, seen));
      if (tok.word_id) seen.add(tok.word_id);
    });
  } else {
    // No token breakdown — render each character, grouping kanji runs
    // with a ruby if a reading is provided
    if (titleObj.r) {
      const ruby = document.createElement('ruby');
      ruby.className = 'token clickable';
      ruby.dataset.role = 'content';
      ruby.appendChild(document.createTextNode(titleObj.jp));
      const rt = document.createElement('rt');
      rt.textContent = titleObj.r;
      ruby.appendChild(rt);
      if (titleObj.word_id) {
        ruby.addEventListener('click', () => openWordPopup(titleObj.word_id, titleObj));
      }
      container.appendChild(ruby);
    } else {
      // Plain text — no interactivity
      container.appendChild(document.createTextNode(titleObj.jp));
    }
  }
}

function buildTokenElement(tok, seenInStory) {
  // For tokens with a reading (kanji), make <ruby> the root element so
  // the browser's native ruby layout places the <rt> above the base text.
  // For all others, use a plain <span>.
  let el;

  if (tok.role === 'punct') {
    el = document.createElement('span');
    el.className = 'token';
    el.dataset.role = 'punct';
    el.textContent = tok.t;
    return el;
  }

  if (tok.r) {
    el = document.createElement('ruby');
    el.appendChild(document.createTextNode(tok.t));
    const rt = document.createElement('rt');
    rt.textContent = tok.r;
    el.appendChild(rt);
  } else {
    el = document.createElement('span');
    el.textContent = tok.t;
  }

  el.className = 'token';
  el.dataset.role = tok.role;

  if (tok.word_id) {
    el.classList.add('clickable');
    const isFirstInStory = !seenInStory.has(tok.word_id);
    if (isFirstInStory && tok.is_new) {
      el.dataset.new = 'true';
    }
    el.addEventListener('click', () => openWordPopup(tok.word_id, tok));
  } else if (tok.grammar_id) {
    el.classList.add('clickable');
    el.addEventListener('click', () => openGrammarPopup(tok.grammar_id));
  }

  return el;
}

function renderNewWordsPanel() {
  const chips = document.getElementById('new-words-chips');
  chips.innerHTML = '';
  (story.new_words ?? []).forEach(wid => {
    const word = vocabState.words[wid];
    if (!word) return;
    const chip = document.createElement('button');
    chip.className = 'word-chip';
    chip.innerHTML = `
      <span class="word-chip-jp">${word.surface}</span>
      <span class="word-chip-en">${word.meanings[0]}</span>
    `;
    chip.addEventListener('click', () => openWordPopup(wid, null));
    chips.appendChild(chip);
  });
}

// ── Popups ────────────────────────────────────────────────────────
function openWordPopup(wordId, tok) {
  const word = vocabState.words[wordId];
  if (!word) return;

  const srs = learnerState.srs?.[wordId];
  const isNew = story?.new_words?.includes(wordId);
  const inflection = tok?.inflection;

  // Auto-play word audio if available and autoplay enabled
  if (story?.word_audio?.[wordId] && learnerState.prefs?.audio_autoplay) {
    playWordAudio(wordId);
  }

  let html = '';

  // Always offer a playable ▶ chip when word audio exists
  if (story?.word_audio?.[wordId]) {
    html += `<button class="btn-audio" style="margin-bottom:0.5rem;" onclick="playWordAudio('${wordId}')">▶ play word</button>`;
  }

  if (isNew) html += `<div class="badge-new">New word</div>`;

  // Show kanji form large, with kana reading beside it
  const hasKanji = word.surface !== word.kana;
  html += `<div class="popup-word">${word.surface}${hasKanji ? `<span style="font-size:1.1rem;font-weight:400;color:var(--text-muted);margin-left:0.5rem;">${word.kana}</span>` : ''}</div>`;
  html += `<div class="popup-reading">
    <span>/ ${word.reading} /</span>
  </div>`;
  html += `<div class="popup-pos">${word.pos}${word.verb_class ? ' · ' + word.verb_class : ''}${word.adj_class ? ' · ' + word.adj_class + '-adj' : ''}</div>`;
  html += `<div class="popup-meanings">${word.meanings.join('; ')}</div>`;

  if (inflection) {
    html += `<hr class="popup-divider"/>`;
    html += `<div class="popup-pos">inflection · ${inflection.form}</div>`;
    html += `<div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:0.5rem;">Base form: ${inflection.base}</div>`;
    const gp = grammarState.points[inflection.grammar_id];
    if (gp) {
      html += `<div style="font-size:0.82rem;color:var(--text-muted);font-style:italic;">${gp.short}</div>`;
    }
  }

  html += `<hr class="popup-divider"/>`;
  html += `<div class="popup-meta">`;
  html += `<span>First seen: Story ${word.first_story}</span>`;
  html += `<span>Seen ${word.occurrences}×</span>`;
  if (srs) html += `<span>SRS: ${srs.status}</span>`;
  html += `</div>`;

  // Grammar tags
  if (word.grammar_tags?.length) {
    const tags = word.grammar_tags.map(gid => {
      const gp = grammarState.points[gid];
      return gp ? `<span class="popup-pos" style="cursor:pointer" onclick="openGrammarPopup('${gid}')">${gp.title}</span>` : '';
    }).join(' ');
    html += `<div>${tags}</div>`;
  }

  showPopup(html);
}

// Detect a grammar entry that the state-updater scaffold left half-filled.
// Mirrors GRAMMAR_PLACEHOLDER_SHORTS in pipeline/validate_state.py.
function isGrammarEntryIncomplete(gp) {
  if (!gp) return true;
  const placeholderShorts = new Set([
    '(added by state updater — fill in description)',
    '(added by state updater)',
    'TODO',
    '',
  ]);
  if (gp._needs_review) return true;
  if (!gp.title || gp.title.trim() === gp.id) return true;
  if (!gp.short || placeholderShorts.has(gp.short.trim())) return true;
  if (!gp.long || !gp.long.trim()) return true;
  return false;
}

function openGrammarPopup(grammarId) {
  const gp = grammarState.points[grammarId];
  if (!gp) return;

  const incomplete = isGrammarEntryIncomplete(gp);
  let html = '';
  if (incomplete) {
    html += `<div class="badge-warn" title="Definition is missing — please fix data/grammar_state.json">⚠ Definition incomplete</div>`;
  }
  html += `<div class="popup-grammar-title">${gp.title || gp.id}</div>`;
  html += `<div class="popup-grammar-short">${gp.short || '(no short description)'}</div>`;
  html += `<hr class="popup-divider"/>`;
  html += `<div class="popup-grammar-long">${gp.long || '(no long description)'}</div>`;
  if (gp.genki_ref) html += `<div class="popup-grammar-ref">Genki ${gp.genki_ref}</div>`;
  if (gp.prerequisites?.length) {
    html += `<div class="popup-grammar-ref" style="margin-top:0.4rem;">Requires: ${gp.prerequisites.join(', ')}</div>`;
  }

  showPopup(html);
}

function showPopup(html) {
  const overlay = document.getElementById('popup-overlay');
  const popup   = document.getElementById('popup');
  const content = document.getElementById('popup-content');
  content.innerHTML = html;
  overlay.hidden = false;
  popup.hidden   = false;
  popup.focus();
}

function closePopup() {
  document.getElementById('popup-overlay').hidden = true;
  document.getElementById('popup').hidden = true;
}

// These are wired up inside boot() after DOM is confirmed ready

// ── Vocab View ────────────────────────────────────────────────────
function renderVocabView() {
  if (!vocabState) return;
  const words = Object.values(vocabState.words);

  // Stats
  const stats = { total: words.length, new: 0, learning: 0, young: 0, mature: 0, leech: 0 };
  words.forEach(w => {
    const srs = learnerState.srs?.[w.id];
    const status = srs?.status ?? 'new';
    if (stats[status] !== undefined) stats[status]++;
    else stats.new++;
  });

  const statsEl = document.getElementById('vocab-stats');
  statsEl.innerHTML = [
    ['Total', stats.total],
    ['New', stats.new],
    ['Learning', stats.learning],
    ['Young', stats.young],
    ['Mature', stats.mature],
  ].map(([label, n]) => `
    <div class="stat-card">
      <span class="stat-number">${n}</span>
      <span class="stat-label">${label}</span>
    </div>
  `).join('');

  // Populate story filter
  const storyFilter = document.getElementById('vocab-story-filter');
  if (storyFilter && storyFilter.options.length <= 1) {
    const stories = Array.from(new Set(words.map(w => w.first_story).filter(Boolean))).sort((a, b) => a - b);
    stories.forEach(n => {
      const opt = document.createElement('option');
      opt.value = String(n);
      opt.textContent = `Story ${n}`;
      storyFilter.appendChild(opt);
    });
  }

  const searchEl = document.getElementById('vocab-search');
  const statusEl = document.getElementById('vocab-status-filter');

  function applyFilters() {
    const q = (searchEl?.value ?? '').toLowerCase().trim();
    const status = statusEl?.value ?? 'all';
    const story = storyFilter?.value ?? 'all';
    const filtered = words.filter(w => {
      const srs = learnerState.srs?.[w.id];
      const wStatus = srs?.status ?? 'new';
      if (status !== 'all' && wStatus !== status) return false;
      if (story !== 'all' && String(w.first_story) !== story) return false;
      if (q && !(
        w.surface.includes(q) ||
        w.kana.includes(q) ||
        w.reading.toLowerCase().includes(q) ||
        w.meanings.some(m => m.toLowerCase().includes(q))
      )) return false;
      return true;
    });
    renderVocabList(filtered);
  }

  // Wire (idempotent — replace handler so re-renders don't stack listeners)
  if (searchEl)  searchEl.oninput  = applyFilters;
  if (statusEl)  statusEl.onchange = applyFilters;
  if (storyFilter) storyFilter.onchange = applyFilters;

  applyFilters();
}

function renderVocabList(words) {
  const listEl = document.getElementById('vocab-list');
  listEl.innerHTML = '';
  words.forEach(word => {
    const srs = learnerState.srs?.[word.id];
    const status = srs?.status ?? 'new';
    const row = document.createElement('div');
    row.className = 'vocab-row';
    row.innerHTML = `
      <span class="vocab-row-jp">${word.surface}</span>
      <span class="vocab-row-reading">${word.reading}</span>
      <span class="vocab-row-meaning">${word.meanings[0]}</span>
      <span class="status-dot" data-status="${status}" title="${status}"></span>
    `;
    row.addEventListener('click', () => openWordPopup(word.id, null));
    listEl.appendChild(row);
  });
}

// ── Grammar View ──────────────────────────────────────────────────
const GRAMMAR_EXAMPLES_CACHE = { byId: null };

async function buildGrammarExamplesIndex() {
  if (GRAMMAR_EXAMPLES_CACHE.byId) return GRAMMAR_EXAMPLES_CACHE.byId;
  const byId = {};
  const manifest = await loadStoryManifest();
  for (const entry of manifest.stories) {
    let s;
    try {
      const res = await fetch(entry.path);
      if (!res.ok) continue;
      s = await res.json();
    } catch { continue; }
    s.sentences.forEach((sent, idx) => {
      const grammarHere = new Set();
      sent.tokens.forEach(tok => {
        if (tok.grammar_id) grammarHere.add(tok.grammar_id);
        if (tok.inflection?.grammar_id) grammarHere.add(tok.inflection.grammar_id);
      });
      grammarHere.forEach(gid => {
        (byId[gid] ??= []).push({
          story_id: s.story_id,
          sentence_idx: idx,
          jp: sent.tokens.map(t => t.t).join(''),
          gloss_en: sent.gloss_en,
        });
      });
    });
  }
  GRAMMAR_EXAMPLES_CACHE.byId = byId;
  return byId;
}

function renderGrammarView() {
  if (!grammarState) return;
  const listEl = document.getElementById('grammar-list');
  listEl.innerHTML = '';

  Object.values(grammarState.points).forEach(gp => {
    const incomplete = isGrammarEntryIncomplete(gp);
    const item = document.createElement('div');
    item.className = 'grammar-item' + (incomplete ? ' incomplete' : '');
    item.innerHTML = `
      <div class="grammar-item-header">
        <span class="grammar-item-id">${gp.id}</span>
        <span class="grammar-item-title">${gp.title || '(no title)'}</span>
        ${incomplete ? '<span class="badge-warn-inline" title="Definition is missing — please fix data/grammar_state.json">⚠</span>' : ''}
        <span class="grammar-item-chevron">▼</span>
      </div>
      <div class="grammar-item-body">
        ${incomplete ? '<p class="grammar-incomplete-note">This grammar entry is incomplete. Update <code>data/grammar_state.json</code> with title / short / long.</p>' : ''}
        <p class="grammar-item-short">${gp.short || '(no short description)'}</p>
        <p class="grammar-item-long">${gp.long || '(no long description)'}</p>
        ${gp.genki_ref ? `<p class="grammar-genki">Genki ${gp.genki_ref}</p>` : ''}
        <div class="grammar-examples" data-grammar-id="${gp.id}"></div>
      </div>
    `;
    item.querySelector('.grammar-item-header').addEventListener('click', async () => {
      const wasOpen = item.classList.contains('open');
      item.classList.toggle('open');
      if (!wasOpen) {
        const target = item.querySelector('.grammar-examples');
        if (target && target.dataset.loaded !== 'true') {
          target.dataset.loaded = 'true';
          target.innerHTML = '<small>loading examples…</small>';
          const idx = await buildGrammarExamplesIndex();
          const examples = idx[gp.id] ?? [];
          target.innerHTML = examples.length
            ? examples.slice(0, 5).map(ex => `
                <div class="grammar-example">
                  <small>S${ex.story_id}·${ex.sentence_idx + 1}</small>${ex.jp}
                  <div style="font-family:var(--font-en);font-style:italic;font-size:0.78rem;color:var(--text-muted);margin-left:2.6rem;">${ex.gloss_en}</div>
                </div>`).join('')
            : '<small>No appearances yet.</small>';
        }
      }
    });
    listEl.appendChild(item);
  });
}

// ── Review View ───────────────────────────────────────────────────
function renderReviewView() {
  const due = getDueItems();
  updateReviewBadge(due.length);

  const container = document.getElementById('review-container');
  container.innerHTML = '';

  if (due.length === 0) {
    container.innerHTML = '<p class="empty-state">Nothing due. Read the next story or come back later.</p>';
    return;
  }

  let idx = 0;
  renderReviewCard(due, idx, container);
}

function getDueItems() {
  const now = new Date();
  return Object.values(learnerState.srs ?? {}).filter(card => {
    if (!card.due) return true; // never reviewed → always due
    return new Date(card.due) <= now;
  });
}

function updateReviewBadge(count) {
  const badge = document.getElementById('review-count');
  if (count > 0) {
    badge.textContent = count;
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

async function renderReviewCard(queue, idx, container) {
  if (idx >= queue.length) {
    container.innerHTML = '<p class="empty-state">Session complete! Come back later.</p>';
    updateReviewBadge(0);
    return;
  }

  const card = queue[idx];
  const word = vocabState.words[card.word_id];
  if (!word) { renderReviewCard(queue, idx + 1, container); return; }

  // Backfill context_story for legacy cards saved before this fix landed.
  // Old cards may have context_story === currentStoryId (whichever story
  // was open when they were added), so for those we trust the vocab's
  // first_story field instead.
  if (!card.context_story || card.context_story === card.first_learned_story) {
    if (word.first_story) {
      card.context_story = word.first_story;
    }
  }

  // Look up the context sentence in the *correct* story (not the
  // currently-open one). The lookup is async because that story file
  // may not be loaded yet — the in-memory STORY_CACHE makes the second
  // call free.
  const sentence = await findContextSentence(card);

  // While we were awaiting, the user may have advanced past this card.
  // We render unconditionally; the next click just renders the next one.

  container.innerHTML = '';

  const cardEl = document.createElement('div');
  cardEl.className = 'review-card';

  // Sentence with word highlighted
  let sentenceHtml = '';
  if (sentence) {
    sentenceHtml = sentence.tokens.map(tok => {
      if (tok.word_id === card.word_id) {
        return `<span class="review-highlight">${tok.t}</span>`;
      }
      return `<span>${tok.t}</span>`;
    }).join('');
  } else {
    // No sentence available → show just the word large, but keep a hint
    // so the missing context is visible (helps debugging).
    sentenceHtml = `<span class="review-highlight">${word.surface}</span>`;
  }

  const sourceLabel = sentence
    ? `<div class="review-source">— Story ${card.context_story}, sentence ${card.context_sentence_idx + 1}</div>`
    : '';

  cardEl.innerHTML = `
    <div class="review-sentence">${sentenceHtml}</div>
    ${sourceLabel}
    <div class="review-answer" id="review-answer">
      <div class="review-word-jp">${word.surface}</div>
      <div class="review-word-reading">${word.kana} / ${word.reading} /</div>
      <div class="review-word-meaning">${word.meanings.join('; ')}</div>
      ${sentence ? `<div class="review-gloss">${sentence.gloss_en}</div>` : ''}
    </div>
  `;

  const revealBtn = document.createElement('button');
  revealBtn.className = 'btn-reveal';
  revealBtn.textContent = 'Show answer';

  const gradeButtons = document.createElement('div');
  gradeButtons.className = 'grade-buttons';
  gradeButtons.hidden = true;
  gradeButtons.innerHTML = `
    <button class="grade-btn" data-grade="0">Again<span class="grade-label">&lt;10m</span></button>
    <button class="grade-btn" data-grade="1">Hard<span class="grade-label">×1.2</span></button>
    <button class="grade-btn" data-grade="2">Good<span class="grade-label">✓</span></button>
    <button class="grade-btn" data-grade="3">Easy<span class="grade-label">×1.3</span></button>
  `;

  revealBtn.addEventListener('click', () => {
    document.getElementById('review-answer').classList.add('visible');
    revealBtn.hidden = true;
    gradeButtons.hidden = false;
  });

  gradeButtons.querySelectorAll('.grade-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const grade = parseInt(btn.dataset.grade, 10);
      applyGrade(card, grade);
      saveLearnerState();
      // Refresh vocab stats silently
      renderVocabView();
      renderReviewCard(queue, idx + 1, container);
    });
  });

  container.append(cardEl, revealBtn, gradeButtons);
}

/**
 * Look up the example sentence for an SRS card.
 * Order:
 *   1. The card's own context_story / context_sentence_idx (the story
 *      this word was first introduced in).
 *   2. Any sentence in that story that contains the word_id.
 *   3. Any sentence in the currently-open story that contains it
 *      (handy when the learner just opened a new story that re-uses it).
 *   4. null — caller renders the bare headword.
 */
async function findContextSentence(card) {
  // 1 + 2: load the card's own context story
  const ctxStoryId = card.context_story;
  if (ctxStoryId) {
    const s = await loadStoryById(ctxStoryId);
    if (s) {
      const exact = s.sentences[card.context_sentence_idx];
      if (exact && exact.tokens.some(t => t.word_id === card.word_id)) return exact;
      const any = s.sentences.find(sent =>
        sent.tokens.some(t => t.word_id === card.word_id));
      if (any) return any;
    }
  }
  // 3: fallback to the currently-loaded story (still useful for retention)
  if (story) {
    const inCurrent = story.sentences.find(sent =>
      sent.tokens.some(t => t.word_id === card.word_id));
    if (inCurrent) return inCurrent;
  }
  return null;
}

// ── SRS Scheduler ─────────────────────────────────────────────────
function applyGrade(card, grade) {
  const now = new Date();
  let { interval_days = 0, ease = 2.5, reps = 0, lapses = 0 } = card;

  if (grade === 0) {
    // Again
    reps = 0;
    interval_days = 10 / (60 * 24); // 10 minutes in days
    ease = Math.max(1.3, ease - 0.20);
    lapses += 1;
  } else if (grade === 1) {
    // Hard
    interval_days = Math.max(1, Math.round(interval_days * 1.2));
    ease = Math.max(1.3, ease - 0.15);
  } else if (grade === 2) {
    // Good
    if (reps === 0) interval_days = 1;
    else if (reps === 1) interval_days = 3;
    else interval_days = Math.round(interval_days * ease);
    reps += 1;
  } else if (grade === 3) {
    // Easy
    if (reps === 0) interval_days = 1;
    else if (reps === 1) interval_days = 3;
    else interval_days = Math.round(interval_days * ease);
    reps += 1;
    interval_days = Math.round(interval_days * 1.3);
    ease = Math.min(ease + 0.10, 4.0);
  }

  // Status
  let status;
  if (lapses >= 6) status = 'leech';
  else if (interval_days < 1) status = 'learning';
  else if (interval_days < 21) status = 'young';
  else status = 'mature';

  const due = new Date(now.getTime() + interval_days * 24 * 60 * 60 * 1000);

  Object.assign(card, { interval_days, ease, reps, lapses, status, due: due.toISOString() });
}

// ── Learner State ─────────────────────────────────────────────────
function loadLearnerState() {
  try {
    const raw = localStorage.getItem('monogatari_learner');
    if (raw) return JSON.parse(raw);
  } catch {}
  return {
    version: 1,
    current_story: 1,
    last_opened: new Date().toISOString(),
    srs: {},
    story_progress: {},
    prefs: {
      show_gloss_by_default: false,
      audio_autoplay: false,
    },
  };
}

let _saveTimer = null;
function saveLearnerState() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => {
    learnerState.last_opened = new Date().toISOString();
    localStorage.setItem('monogatari_learner', JSON.stringify(learnerState));
  }, 500);
}

// ── Export / Import ───────────────────────────────────────────────
function setupExportImport() {
  document.getElementById('btn-export').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify(learnerState, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `monogatari_progress_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });

  document.getElementById('input-import').addEventListener('change', e => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      try {
        const imported = JSON.parse(ev.target.result);
        if (!imported.version || !imported.srs) throw new Error('Invalid file');
        Object.assign(learnerState, imported);
        saveLearnerState();
        renderReviewView();
        renderVocabView();
        alert('Progress imported successfully!');
      } catch {
        alert('Invalid progress file.');
      }
    };
    reader.readAsText(file);
    e.target.value = ''; // reset so same file can be re-imported
  });
}

// ── Go ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', boot);

// ── Service worker (offline support) ───────────────────────────────────────
// Registers sw.js and shows a small "update available" toast when a newer
// version of the app is downloaded in the background.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('./sw.js');
      reg.addEventListener('updatefound', () => {
        const installing = reg.installing;
        if (!installing) return;
        installing.addEventListener('statechange', () => {
          if (installing.state === 'installed' && navigator.serviceWorker.controller) {
            showUpdateToast(reg);
          }
        });
      });
    } catch (e) {
      // Offline-first is a progressive enhancement; failing to register is fine.
      console.warn('Service worker registration failed:', e);
    }
  });
}

function showUpdateToast(reg) {
  let toast = document.getElementById('sw-update-toast');
  if (toast) return;
  toast = document.createElement('div');
  toast.id = 'sw-update-toast';
  toast.className = 'sw-update-toast';
  toast.innerHTML = `
    <span>A new version of Monogatari is ready.</span>
    <button class="btn-audio" id="btn-sw-reload">Reload</button>
  `;
  document.body.appendChild(toast);
  document.getElementById('btn-sw-reload').onclick = () => {
    if (reg.waiting) reg.waiting.postMessage({ type: 'SKIP_WAITING' });
    // Reload as soon as the new SW takes control
    navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload(), { once: true });
  };
}
