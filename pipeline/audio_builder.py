#!/usr/bin/env python3
"""
Monogatari — Audio builder (Stage 4 of the pipeline).

Produces:
  audio/story_<N>/s<idx>.<ext>      — one file per sentence
  audio/story_<N>/w_<word_id>.<ext> — one file per new_word (dictionary form)

The story JSON is updated in place: each sentence's `audio` field and the
top-level `word_audio` map point at the produced files (relative paths).

Backend
-------
Google Cloud Text-to-Speech is the *only* backend. It activates when:
  - the `google-cloud-texttospeech` library is importable, AND
  - credentials are visible (GOOGLE_APPLICATION_CREDENTIALS, gcloud ADC, or
    workload identity).

Tunables (env or CLI):
  MONOGATARI_TTS_VOICE     default: ja-JP-Neural2-B    (other options below)
  MONOGATARI_TTS_LANGCODE  default: ja-JP
  MONOGATARI_TTS_AUDIO     default: MP3                (MP3 → .mp3, LINEAR16 → .wav)
  MONOGATARI_TTS_DRY_RUN   if set non-empty, prints planned requests instead
                           of calling the API (useful for cost auditing).

Common voices to try (all neural-2 / wavenet, native Japanese):
  ja-JP-Neural2-B   (female, warm, default)
  ja-JP-Neural2-C   (male)
  ja-JP-Neural2-D   (male, deeper)
  ja-JP-Wavenet-A   (female, classic)

SSML
----
Sentences are wrapped in <speak><prosody rate="..."> with the spec's 0.85×
default. Words are sent as plain text at natural rate to match dictionary
pronunciation (the spec asks for "no SSML modifications" on word audio).

Usage
-----
  python3 pipeline/audio_builder.py stories/story_3.json \\
        --vocab data/vocab_state.json [--rate 0.85]

  # Audit costs without calling the API:
  MONOGATARI_TTS_DRY_RUN=1 python3 pipeline/audio_builder.py stories/story_3.json \\
        --vocab data/vocab_state.json

The script is **idempotent**: it skips files that already exist unless
--force is passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import wave
from pathlib import Path

DEFAULT_RATE       = 0.85       # spec: ~0.85× for sentence audio
DEFAULT_SAMPLERATE = 22050
DEFAULT_AUDIO_ENC  = "MP3"      # MP3 keeps the shipped format; .mp3 on disk

_AUDIO_EXTENSION = {"LINEAR16": ".wav", "MP3": ".mp3", "OGG_OPUS": ".ogg"}


# ── Google Cloud TTS backend ────────────────────────────────────────────────

_GOOGLE_CLIENT = None       # lazily-initialised tts.TextToSpeechClient
_GOOGLE_DRY_RUN = bool(os.environ.get("MONOGATARI_TTS_DRY_RUN", "").strip())


def _google_audio_encoding(name: str | None):
    """Map a string like 'LINEAR16' / 'MP3' to the proto enum."""
    from google.cloud import texttospeech as tts  # type: ignore
    name = (name or DEFAULT_AUDIO_ENC).upper()
    return getattr(tts.AudioEncoding, name)


def _google_client():
    global _GOOGLE_CLIENT
    if _GOOGLE_CLIENT is not None:
        return _GOOGLE_CLIENT
    try:
        from google.cloud import texttospeech as tts  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "Audio builder requires `google-cloud-texttospeech`.\n"
            "  pip install google-cloud-texttospeech\n"
            "and set GOOGLE_APPLICATION_CREDENTIALS or run\n"
            "  gcloud auth application-default login"
        ) from e
    _GOOGLE_CLIENT = tts.TextToSpeechClient()
    return _GOOGLE_CLIENT


def _google_synthesize(input_obj, *, language_code: str, voice_name: str,
                       audio_encoding, samplerate: int) -> bytes:
    """Single round-trip to Google TTS; returns raw audio bytes."""
    from google.cloud import texttospeech as tts  # type: ignore

    voice = tts.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name,
    )
    audio_config = tts.AudioConfig(
        audio_encoding=audio_encoding,
        sample_rate_hertz=samplerate,
    )

    if _GOOGLE_DRY_RUN:
        # Print a concise audit line and return a tiny silent stub
        # so the rest of the pipeline still produces a valid file.
        try:
            preview = input_obj.text or input_obj.ssml
        except AttributeError:
            preview = repr(input_obj)
        print(f"  [dry-run] voice={voice_name} preview={preview[:60]!r}")
        # Return 0.05 s of silence as 16-bit PCM (will be wrapped as WAV
        # by the caller when audio_encoding=LINEAR16; for MP3/OGG the
        # bytes are written as-is, which yields an unplayable but
        # cost-free placeholder — acceptable for dry-run audits).
        n = max(1, int(samplerate * 0.05))
        return b"\x00\x00" * n

    client = _google_client()
    response = client.synthesize_speech(
        input=input_obj, voice=voice, audio_config=audio_config
    )
    return response.audio_content


def _write_audio_bytes(out_path: Path, audio_bytes: bytes,
                       audio_encoding_name: str, samplerate: int) -> None:
    """If the encoding is LINEAR16 we already have raw PCM and need to wrap
    it in a WAV container. For MP3 / OGG_OPUS, just write the bytes."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    name = audio_encoding_name.upper()
    if name == "LINEAR16":
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(samplerate)
            w.writeframes(audio_bytes)
    else:
        out_path.write_bytes(audio_bytes)


def google_sentence(text: str, kana: str, out_path: Path, *,
                    rate: float, samplerate: int,
                    voice_name: str, language_code: str,
                    audio_encoding_name: str) -> None:
    """Synthesize a sentence at `rate`× speed using SSML <prosody>."""
    from google.cloud import texttospeech as tts  # type: ignore

    # SSML escape: text shouldn't contain <, >, or & (Japanese normally won't,
    # but be defensive).
    safe = (text or "")\
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ssml = f'<speak><prosody rate="{rate:.2f}">{safe}</prosody></speak>'

    audio = _google_synthesize(
        tts.SynthesisInput(ssml=ssml),
        language_code=language_code, voice_name=voice_name,
        audio_encoding=_google_audio_encoding(audio_encoding_name),
        samplerate=samplerate,
    )
    _write_audio_bytes(out_path, audio, audio_encoding_name, samplerate)


def google_word(text: str, kana: str, out_path: Path, *,
                samplerate: int,
                voice_name: str, language_code: str,
                audio_encoding_name: str) -> None:
    """Word audio: dictionary form, no SSML / natural rate (per spec)."""
    from google.cloud import texttospeech as tts  # type: ignore

    audio = _google_synthesize(
        tts.SynthesisInput(text=text or kana or "?"),
        language_code=language_code, voice_name=voice_name,
        audio_encoding=_google_audio_encoding(audio_encoding_name),
        samplerate=samplerate,
    )
    _write_audio_bytes(out_path, audio, audio_encoding_name, samplerate)


# ── Pipeline driver ─────────────────────────────────────────────────────────
#
# v0.13 (2026-04-22) — content-vs-audio drift detection.
#
# Each sentence and each shipped word audio gets an `audio_hash` field
# derived from the exact string sent to the TTS backend (the concatenation
# of token surfaces). The repo-health pytest suite recomputes the hash on
# every run and fails the build if any stored hash no longer matches its
# source — surfacing exactly the failure mode that cost us a silent audio
# defect on stories 7/8/12 (the 2026-04-22 audit changed JP tokens but
# nobody regenerated the matching mp3s).
#
# We deliberately use a short hex prefix (12 chars of SHA-256). It is long
# enough that accidental collisions in a corpus of < 10⁴ sentences are
# astronomically unlikely, and short enough that diffs of story_N.json
# remain readable.

def _audio_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def sentence_audio_text(sent: dict) -> str:
    """The exact string the TTS backend speaks for a sentence — the same
    concatenation `build_audio_for_story` uses. Exposed at module scope so
    the pytest drift check can recompute it without re-importing the
    private helper."""
    return "".join(t["t"] for t in sent.get("tokens", []))


def word_audio_text(word: dict) -> str:
    """The exact string the TTS backend speaks for a new-word entry.

    Prefers KANA over surface so single-kanji words are pronounced with
    the intended reading instead of TTS's default on-yomi guess. The
    canonical example: 道 in isolation. Sent as the surface string,
    Google's ja-JP-Neural2-B reads 「どう」 (on-yomi). Sent as 「みち」
    (the kana field), it correctly reads 「みち」 (kun-yomi). Same
    failure mode applies to any single-kanji entry where surface and
    kana differ — 月 → 「がつ」 vs 「つき」, 手 → 「しゅ」 vs 「て」,
    家 → 「か」 vs 「いえ」, etc.

    This is safe for multi-character entries too: 友達 → 「ともだち」
    is unambiguous, and pure-kana entries already have surface == kana.

    The function still falls back to surface when kana is missing
    (extremely rare; surface should never be) and finally to the empty
    string so the caller can substitute the word_id.
    """
    if not word:
        return ""
    return word.get("kana") or word.get("surface") or ""


def build_audio_for_story(
    story_path: Path,
    vocab: dict,
    *,
    rate: float = DEFAULT_RATE,
    samplerate: int = DEFAULT_SAMPLERATE,
    audio_root: Path = Path("audio"),
    force: bool = False,
    voice_name: str = "ja-JP-Neural2-B",
    language_code: str = "ja-JP",
    audio_encoding_name: str = DEFAULT_AUDIO_ENC,
) -> dict:
    story = json.loads(story_path.read_text(encoding="utf-8"))
    story_id = story["story_id"]
    sub_dir = audio_root / f"story_{story_id}"
    sub_dir.mkdir(parents=True, exist_ok=True)

    ext = _AUDIO_EXTENSION.get(audio_encoding_name.upper(), ".mp3")

    common = dict(
        voice_name=voice_name,
        language_code=language_code,
        audio_encoding_name=audio_encoding_name,
    )

    # ── Sentences ──
    for sent in story["sentences"]:
        idx = sent["idx"]
        out_path = sub_dir / f"s{idx}{ext}"
        rel = out_path.as_posix()
        text = sentence_audio_text(sent)
        kana = "".join(t.get("r", t["t"]) for t in sent["tokens"] if t.get("role") != "punct")
        if force or not out_path.exists():
            google_sentence(text, kana, out_path,
                            rate=rate, samplerate=samplerate, **common)
        sent["audio"] = rel
        # v0.13: drift hash. Always overwritten on a (re)build because the
        # hash is meaningless without a matching audio file on disk.
        sent["audio_hash"] = _audio_hash(text)

    # ── New-word audio (dictionary forms) ──
    # As of 2026-04-29: word audio lives in a flat per-word directory
    # `audio/words/<id>.mp3`, NOT in the introducing story's folder.
    # The decoupling matters because words appear all over the UI
    # (vocab list, library, review, popups from any story) and tying
    # the audio path to first_story made the audio undiscoverable from
    # those contexts (and broke after corpus rewrites that change a
    # word's introducing story). Sentence audio remains story-scoped.
    words_dir = audio_root / "words"
    words_dir.mkdir(parents=True, exist_ok=True)
    word_audio = story.get("word_audio") or {}
    word_audio_hash = story.get("word_audio_hash") or {}
    for wid in story.get("new_words", []):
        word = vocab.get("words", {}).get(wid)
        if not word:
            continue
        out_path = words_dir / f"{wid}{ext}"
        rel = out_path.as_posix()
        text = word_audio_text(word) or wid
        kana = word.get("kana") or text
        if force or not out_path.exists():
            google_word(text, kana, out_path,
                        samplerate=samplerate, **common)
        word_audio[wid] = rel
        word_audio_hash[wid] = _audio_hash(text)
    story["word_audio"]      = word_audio
    story["word_audio_hash"] = word_audio_hash

    story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "sentences": len(story["sentences"]),
        "words":     len(story.get("word_audio", {})),
        "out_dir":   str(sub_dir),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Monogatari audio builder (Google Cloud TTS)"
    )
    ap.add_argument("story",   help="Path to a shipped story JSON (e.g. stories/story_3.json)")
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE,
                    help="Speech rate multiplier for sentence audio (default 0.85)")
    ap.add_argument("--samplerate", type=int, default=DEFAULT_SAMPLERATE)
    ap.add_argument("--audio-root", default="audio",
                    help="Directory under which to write audio (default: audio/)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing audio files (default: skip if present)")
    ap.add_argument("--voice", default=os.environ.get("MONOGATARI_TTS_VOICE", "ja-JP-Neural2-B"),
                    help="Google TTS voice name (e.g. ja-JP-Neural2-B / -C / -D)")
    ap.add_argument("--language-code", default=os.environ.get("MONOGATARI_TTS_LANGCODE", "ja-JP"),
                    help="BCP-47 language tag passed to Google TTS")
    ap.add_argument("--audio-encoding",
                    default=os.environ.get("MONOGATARI_TTS_AUDIO", DEFAULT_AUDIO_ENC),
                    choices=["LINEAR16", "MP3", "OGG_OPUS"],
                    help="Google TTS audio encoding (MP3 → .mp3, LINEAR16 → .wav)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Do not call the API; print planned requests instead")
    args = ap.parse_args()

    vocab = json.loads(Path(args.vocab).read_text(encoding="utf-8"))

    # Honor --dry-run by toggling the module flag.
    if args.dry_run:
        global _GOOGLE_DRY_RUN
        _GOOGLE_DRY_RUN = True

    summary = build_audio_for_story(
        Path(args.story), vocab,
        rate=args.rate, samplerate=args.samplerate,
        audio_root=Path(args.audio_root), force=args.force,
        voice_name=args.voice,
        language_code=args.language_code,
        audio_encoding_name=args.audio_encoding,
    )
    print(f"✓ Audio built: {summary['sentences']} sentence(s), "
          f"{summary['words']} word(s) → {summary['out_dir']}"
          f"{' (dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
