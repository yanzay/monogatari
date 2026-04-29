<script lang="ts">
  import { learner } from '$lib/state/learner.svelte';
  import { dueForecast, statusCounts, trueRetention } from '$lib/state/srs';

  let counts = $derived(statusCounts(learner.state.srs ?? {}));
  let retention = $derived(trueRetention(learner.state.history ?? [], 30));
  let forecast = $derived(dueForecast(learner.state.srs ?? {}, 14));
  let maxForecast = $derived(Math.max(1, ...forecast.map((b) => b.count)));

  // Settings (live binding to prefs)
  let prefs = $derived(learner.state.prefs);

  function bindRetention(e: Event) {
    const v = parseFloat((e.target as HTMLInputElement).value);
    if (Number.isFinite(v)) {
      learner.state.prefs.target_retention = v;
      learner.save();
    }
  }
  function bindNum(key: 'new_per_review' | 'listening_per_review', e: Event) {
    const v = parseInt((e.target as HTMLInputElement).value, 10);
    if (Number.isFinite(v) && v >= 0) {
      learner.state.prefs[key] = v;
      learner.save();
    }
  }
  /** Bind the EchoPolicy select. The pref is a string union — we
   *  defend against arbitrary input by ignoring anything off the
   *  whitelist (which can only happen if a user hand-edits the DOM). */
  function bindEchoPolicy(e: Event) {
    const v = (e.target as HTMLSelectElement).value;
    if (v === 'never' || v === 'mature_only' || v === 'always') {
      learner.state.prefs.audio_echo_on_grade = v;
      learner.save();
    }
  }
  /**
   * Bind the optional review cap. The pref is `number | null` where null
   * means "no cap" (the default). The number input emits an empty string
   * when cleared; we coerce that — and any zero/negative — back to null
   * so the user has a clean way to opt out of throttling entirely.
   */
  function bindReviewCap(e: Event) {
    const raw = (e.target as HTMLInputElement).value;
    if (raw === '') {
      learner.state.prefs.daily_max_reviews = null;
    } else {
      const v = parseInt(raw, 10);
      learner.state.prefs.daily_max_reviews =
        Number.isFinite(v) && v > 0 ? v : null;
    }
    learner.save();
  }
  function bindBool(
    key: 'audio_on_review_reveal',
    e: Event,
  ) {
    learner.state.prefs[key] = (e.target as HTMLInputElement).checked;
    learner.save();
  }
</script>

<div class="view active stats-view">
  <h2 class="library-heading">Stats &amp; settings</h2>

  <section class="stats-section">
    <h3 class="panel-label">SRS status</h3>
    <div class="vocab-stats">
      <div class="stat-card">
        <span class="stat-number">{counts.new}</span><span class="stat-label">New</span>
      </div>
      <div class="stat-card">
        <span class="stat-number">{counts.learning + counts.relearning}</span>
        <span class="stat-label">Learning</span>
      </div>
      <div class="stat-card">
        <span class="stat-number">{counts.young}</span><span class="stat-label">Young</span>
      </div>
      <div class="stat-card">
        <span class="stat-number">{counts.mature}</span><span class="stat-label">Mature</span>
      </div>
      <div class="stat-card">
        <span class="stat-number">{counts.leech}</span><span class="stat-label">Leech</span>
      </div>
    </div>
  </section>

  <section class="stats-section">
    <h3 class="panel-label">True retention (last 30 days)</h3>
    {#if retention.reviewed === 0}
      <p class="stats-empty">Not enough reviews yet.</p>
    {:else}
      <p class="stats-big">{(retention.rate * 100).toFixed(1)}%</p>
      <p class="stats-sub">
        {retention.remembered} remembered / {retention.reviewed} reviews · target
        {Math.round((prefs.target_retention ?? 0.9) * 100)}%
      </p>
    {/if}
  </section>

  <section class="stats-section">
    <h3 class="panel-label">Due in the next 14 days</h3>
    <div class="forecast-row" role="img" aria-label="Due-cards bar chart">
      {#each forecast as bucket, i (bucket.day)}
        <div class="forecast-bar-wrap" title="{bucket.day}: {bucket.count} due">
          <div class="forecast-bar" style="height:{(bucket.count / maxForecast) * 100}%"></div>
          {#if i === 0 || i === forecast.length - 1 || i % 7 === 0}
            <span class="forecast-bar-label">{bucket.day.slice(5)}</span>
          {/if}
        </div>
      {/each}
    </div>
  </section>

  <section class="stats-section">
    <h3 class="panel-label">Settings</h3>
    <div class="settings-grid">
      <label class="settings-row">
        <span>Target retention</span>
        <input
          type="range"
          min="0.7"
          max="0.97"
          step="0.01"
          value={prefs.target_retention ?? 0.9}
          oninput={bindRetention}
        />
        <span class="settings-value">{Math.round((prefs.target_retention ?? 0.9) * 100)}%</span>
      </label>
      <label class="settings-row">
        <span>
          Daily max reviews
          <small class="settings-hint">
            Optional self-imposed cap on review cards per day. Leave blank
            for no cap (the default). New cards from stories you've read
            are never throttled — they enter the SRS map the moment you
            press "Save for review", which is consent enough.
          </small>
        </span>
        <input
          type="number"
          min="1"
          max="2000"
          placeholder="no cap"
          value={prefs.daily_max_reviews ?? ''}
          oninput={bindReviewCap}
        />
      </label>
      <label class="settings-row">
        <span>New per review (interleave)</span>
        <input
          type="number"
          min="0"
          max="20"
          value={prefs.new_per_review}
          oninput={(e) => bindNum('new_per_review', e)}
        />
      </label>
      <label class="settings-row settings-row-checkbox">
        <input
          type="checkbox"
          checked={prefs.audio_on_review_reveal}
          onchange={(e) => bindBool('audio_on_review_reveal', e)}
        />
        <span>Play word audio on review reveal</span>
      </label>
      <label class="settings-row">
        <span>
          Listening cards per review
          <small class="settings-hint">
            Listening cards are a separate deck (sentence audio is the
            prompt; the JP text + gloss is the answer). They're WOVEN
            into reading sessions at this rate — e.g. 6 means one
            listening card every 6 reading cards. Set to 0 to drop
            listening cards from sessions entirely (the SRS map keeps
            them so you can flip the rate back on later without losing
            their schedule).
          </small>
        </span>
        <input
          type="number"
          min="0"
          max="20"
          value={prefs.listening_per_review}
          oninput={(e) => bindNum('listening_per_review', e)}
        />
      </label>
      <label class="settings-row">
        <span>
          Sentence audio echo on grade
          <small class="settings-hint">
            After grading a reading card Good or Easy, optionally
            replay the sentence audio. Reinforces sentence prosody on
            words you've just shown you can recognize. Never fires on
            Again grades or on listening cards (where audio was the
            prompt). Default: only on already-graduated cards.
          </small>
        </span>
        <select
          value={prefs.audio_echo_on_grade}
          onchange={bindEchoPolicy}
        >
          <option value="never">Never</option>
          <option value="mature_only">Only on graduated cards</option>
          <option value="always">After every Good / Easy</option>
        </select>
      </label>
    </div>
  </section>
</div>

<style>
  .stats-view { padding: 1rem; max-width: 720px; margin: 0 auto; }
  .stats-section { margin: 1.4rem 0; }
  .stats-big {
    font-family: var(--font-en, serif);
    font-size: 2.6rem;
    font-weight: 600;
    margin: 0.2rem 0;
    color: var(--accent);
  }
  .stats-sub { color: var(--text-muted); font-size: 0.85rem; margin: 0; }
  .stats-empty { color: var(--text-muted); font-style: italic; }
  .forecast-row {
    display: flex;
    align-items: flex-end;
    gap: 4px;
    height: 100px;
    padding: 0.5rem 0 1.5rem;
    border-bottom: 1px solid var(--border);
  }
  .forecast-bar-wrap {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 100%;
    justify-content: flex-end;
    position: relative;
  }
  .forecast-bar {
    width: 100%;
    background: var(--accent);
    opacity: 0.6;
    border-radius: 2px 2px 0 0;
    min-height: 1px;
  }
  .forecast-bar-label {
    position: absolute;
    bottom: -1.2rem;
    font-size: 0.65rem;
    color: var(--text-muted);
  }
  .settings-grid { display: grid; gap: 0.7rem; }
  .settings-row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 0.8rem;
    align-items: center;
    font-size: 0.9rem;
  }
  .settings-row input[type='number'] {
    width: 5rem;
    padding: 0.2rem 0.4rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font: inherit;
  }
  .settings-row input[type='range'] { width: 12rem; }
  .settings-value { font-variant-numeric: tabular-nums; color: var(--text-muted); }
  .settings-hint {
    display: block;
    font-size: 0.7rem;
    color: var(--text-muted);
    font-style: italic;
    line-height: 1.4;
    margin-top: 0.2rem;
    max-width: 28rem;
  }
  .settings-row-checkbox {
    grid-template-columns: auto 1fr;
    gap: 0.5rem;
  }
</style>
