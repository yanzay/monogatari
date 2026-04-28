/**
 * Pure helper: derive a word's audio path from its id.
 *
 * Every minted word in the corpus has a per-word audio file written
 * by `pipeline/audio_builder.py` to:
 *
 *     audio/words/<word_id>.mp3
 *
 * Audio is intentionally DECOUPLED from any story: a word can appear
 * in any number of stories (and in the vocab list, library, review
 * queue, popup-from-anywhere) so storing it under the introducing
 * story's directory was an unfortunate coupling that made the audio
 * undiscoverable from non-read contexts. Sentence audio remains
 * story-scoped (`audio/story_<n>/s<idx>.mp3`).
 *
 * Returns null when we can't determine the path (missing word, missing
 * id, empty id).
 */
export function wordAudioPath(word: {
  id?: string;
} | null | undefined): string | null {
  if (!word) return null;
  const id = word.id;
  if (!id || typeof id !== 'string' || !id.trim()) return null;
  return `audio/words/${id}.mp3`;
}
