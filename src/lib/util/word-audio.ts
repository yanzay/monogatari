/**
 * Pure helper: derive a word's audio path from its metadata.
 *
 * Every minted word in the corpus has a per-word audio file written
 * by `pipeline/audio_builder.py` to:
 *
 *     audio/story_<first_story>/w_<word_id>.mp3
 *
 * Returns null when we can't determine the path (missing word, missing
 * first_story, malformed first_story shape).
 *
 * The shape of `first_story` is historically inconsistent: vocab_state
 * stores it as the string "story_<n>", but some legacy code paths and
 * older index payloads use the bare integer. This helper accepts both.
 */
export function wordAudioPath(word: {
  id?: string;
  first_story?: number | string;
} | null | undefined): string | null {
  if (!word) return null;
  const id = word.id;
  const fs = word.first_story;
  if (!id || fs === undefined || fs === null) return null;
  let n: number | null = null;
  if (typeof fs === 'number') {
    n = Number.isFinite(fs) ? fs : null;
  } else if (typeof fs === 'string') {
    const m = fs.match(/(\d+)$/);
    if (m) n = parseInt(m[1], 10);
  }
  if (n === null || !Number.isFinite(n) || n <= 0) return null;
  return `audio/story_${n}/w_${id}.mp3`;
}
