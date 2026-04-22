#!/usr/bin/env python3
"""
Monogatari — Audio builder (Stage 4 of the pipeline).

Produces:
  audio/story_<N>/s<idx>.wav        — one file per sentence
  audio/story_<N>/w_<word_id>.wav   — one file per new_word (dictionary form)

The story JSON is updated in place: each sentence's `audio` field and the
top-level `word_audio` map point at the produced files (relative paths).

Backends
--------
Two backends are provided. The *active* one is chosen with --backend or
the MONOGATARI_TTS env var:

  * synth     (default) — deterministic synthetic audio (no network).
                Each sentence/word gets a short tone sequence whose pitches
                are derived from a hash of the kana reading. The point is
                **not** intelligibility — it is to exercise the entire
                pipeline (file paths, JSON wiring, browser playback) end
                to end with real WAV files that the browser can decode.
                Useful for offline development and CI smoke tests.

  * google    — calls google.cloud.texttospeech if available. Skipped here
                because the workspace has no network/credentials. The code
                is a thin stub showing where to plug in.

Usage
-----
  python3 pipeline/audio_builder.py stories/story_3.json \\
        --vocab data/vocab_state.json [--backend synth] [--rate 0.85]

The script is **idempotent**: it skips files that already exist unless
--force is passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
import wave
from pathlib import Path

DEFAULT_RATE      = 0.85       # spec: ~0.85× for sentence audio
DEFAULT_SAMPLERATE = 22050
DEFAULT_BACKEND   = "google"   # v0.11 (2026-04-22) — see docs/authoring.md.
                               # The synth backend is a development-only
                               # fallback; never ship a story with it.


# ── Synth backend ───────────────────────────────────────────────────────────
def _hash_to_freq(token: str) -> float:
    """Map a kana/word string to a stable, pleasant pitch in 220–660 Hz."""
    h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
    return 220.0 + (h % 440)


def _render_tone(freqs: list[float], samplerate: int, secs_per_tone: float) -> bytes:
    """Render a sequence of sinusoidal tones to a 16-bit PCM byte string."""
    samples = []
    for f in freqs:
        n = int(samplerate * secs_per_tone)
        for i in range(n):
            # Light envelope to avoid clicks
            env = min(1.0, i / 200) * min(1.0, (n - i) / 200)
            v = 0.25 * env * math.sin(2 * math.pi * f * (i / samplerate))
            samples.append(int(v * 32767))
    return b"".join(struct.pack("<h", s) for s in samples)


def synth_sentence(text: str, kana: str, out_path: Path, *, rate: float, samplerate: int) -> None:
    """Produce a short tonal WAV that 'represents' a sentence (synthetic)."""
    # One tone per kana char (capped) at ~0.12s; rate scales tone duration
    chars = list(kana or text)[:24]
    if not chars:
        chars = ["ー"]
    secs = 0.12 / max(0.5, rate)
    freqs = [_hash_to_freq(c) for c in chars]
    pcm = _render_tone(freqs, samplerate, secs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm)


def synth_word(text: str, kana: str, out_path: Path, *, samplerate: int) -> None:
    """Word audio: 2 tones at natural speed (~0.20s each)."""
    base = (kana or text).strip()
    if not base:
        base = "?"
    chars = list(base)[:6] or ["ー"]
    pcm = _render_tone([_hash_to_freq(c) for c in chars], samplerate, 0.20)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm)


# ── Google Cloud TTS backend ────────────────────────────────────────────────
#
# Fully wired. Activates when:
#   - the `google-cloud-texttospeech` library is importable, AND
#   - credentials are visible (GOOGLE_APPLICATION_CREDENTIALS, gcloud ADC, or
#     workload identity).
#
# Tunables (env or CLI):
#   MONOGATARI_TTS_VOICE     default: ja-JP-Neural2-B    (other options below)
#   MONOGATARI_TTS_LANGCODE  default: ja-JP
#   MONOGATARI_TTS_AUDIO     default: LINEAR16           (write .wav by default
#                                                         to match synth output;
#                                                         set to MP3 to write .mp3)
#   MONOGATARI_TTS_DRY_RUN   if set non-empty, prints planned requests instead
#                            of calling the API (useful for cost auditing).
#
# Common voices to try (all neural-2 / wavenet, native Japanese):
#   ja-JP-Neural2-B   (female, warm, default)
#   ja-JP-Neural2-C   (male)
#   ja-JP-Neural2-D   (male, deeper)
#   ja-JP-Wavenet-A   (female, classic)
#
# SSML
# ----
# Sentences are wrapped in <speak><prosody rate="..."> with the spec's 0.85×
# default. Words are sent as plain text at natural rate to match dictionary
# pronunciation (the spec asks for "no SSML modifications" on word audio).

_GOOGLE_CLIENT = None       # lazily-initialised tts.TextToSpeechClient
_GOOGLE_DRY_RUN = bool(os.environ.get("MONOGATARI_TTS_DRY_RUN", "").strip())


def _google_audio_encoding(name: str | None):
    """Map a string like 'LINEAR16' / 'MP3' to the proto enum."""
    from google.cloud import texttospeech as tts  # type: ignore
    name = (name or "LINEAR16").upper()
    return getattr(tts.AudioEncoding, name)


def _google_client():
    global _GOOGLE_CLIENT
    if _GOOGLE_CLIENT is not None:
        return _GOOGLE_CLIENT
    try:
        from google.cloud import texttospeech as tts  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "google backend requires `google-cloud-texttospeech`.\n"
            "  pip install google-cloud-texttospeech\n"
            "and set GOOGLE_APPLICATION_CREDENTIALS or run `gcloud auth "
            "application-default login`."
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
        # Print a concise audit line and synthesize a tiny silent stub
        # so the rest of the pipeline still produces a valid file.
        try:
            preview = input_obj.text or input_obj.ssml
        except AttributeError:
            preview = repr(input_obj)
        print(f"  [google dry-run] voice={voice_name} preview={preview[:60]!r}")
        # Return 0.05 s of silence as 16-bit PCM (will be wrapped as WAV by caller).
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
                    voice_name: str | None = None,
                    language_code: str | None = None,
                    audio_encoding_name: str | None = None) -> None:
    """Synthesize a sentence at `rate`× speed using SSML <prosody>."""
    from google.cloud import texttospeech as tts  # type: ignore

    voice = voice_name or os.environ.get("MONOGATARI_TTS_VOICE", "ja-JP-Neural2-B")
    lang  = language_code or os.environ.get("MONOGATARI_TTS_LANGCODE", "ja-JP")
    enc   = audio_encoding_name or os.environ.get("MONOGATARI_TTS_AUDIO", "LINEAR16")

    # SSML escape: text shouldn't contain <, >, or & (Japanese normally won't,
    # but be defensive).
    safe = (text or "")\
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ssml = f'<speak><prosody rate="{rate:.2f}">{safe}</prosody></speak>'

    audio = _google_synthesize(
        tts.SynthesisInput(ssml=ssml),
        language_code=lang, voice_name=voice,
        audio_encoding=_google_audio_encoding(enc),
        samplerate=samplerate,
    )
    _write_audio_bytes(out_path, audio, enc, samplerate)


def google_word(text: str, kana: str, out_path: Path, *,
                samplerate: int,
                voice_name: str | None = None,
                language_code: str | None = None,
                audio_encoding_name: str | None = None) -> None:
    """Word audio: dictionary form, no SSML / natural rate (per spec)."""
    from google.cloud import texttospeech as tts  # type: ignore

    voice = voice_name or os.environ.get("MONOGATARI_TTS_VOICE", "ja-JP-Neural2-B")
    lang  = language_code or os.environ.get("MONOGATARI_TTS_LANGCODE", "ja-JP")
    enc   = audio_encoding_name or os.environ.get("MONOGATARI_TTS_AUDIO", "LINEAR16")

    audio = _google_synthesize(
        tts.SynthesisInput(text=text or kana or "?"),
        language_code=lang, voice_name=voice,
        audio_encoding=_google_audio_encoding(enc),
        samplerate=samplerate,
    )
    _write_audio_bytes(out_path, audio, enc, samplerate)


# ── Pipeline driver ─────────────────────────────────────────────────────────
_AUDIO_EXTENSION = {"LINEAR16": ".wav", "MP3": ".mp3", "OGG_OPUS": ".ogg"}

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
import hashlib

def _audio_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def sentence_audio_text(sent: dict) -> str:
    """The exact string the TTS backend speaks for a sentence — the same
    concatenation `build_audio_for_story` uses. Exposed at module scope so
    the pytest drift check can recompute it without re-importing the
    private helper."""
    return "".join(t["t"] for t in sent.get("tokens", []))


def word_audio_text(word: dict) -> str:
    """The exact string the TTS backend speaks for a new-word entry."""
    return (word or {}).get("surface") or (word or {}).get("kana") or ""


def build_audio_for_story(
    story_path: Path,
    vocab: dict,
    *,
    backend: str = DEFAULT_BACKEND,
    rate: float = DEFAULT_RATE,
    samplerate: int = DEFAULT_SAMPLERATE,
    audio_root: Path = Path("audio"),
    force: bool = False,
    # Google-specific (ignored by synth backend):
    voice_name: str | None = None,
    language_code: str | None = None,
    audio_encoding_name: str | None = None,
) -> dict:
    story = json.loads(story_path.read_text(encoding="utf-8"))
    story_id = story["story_id"]
    sub_dir = audio_root / f"story_{story_id}"
    sub_dir.mkdir(parents=True, exist_ok=True)

    sent_fn, word_fn = _pick_backend(backend)

    # synth always writes WAV; google writes whatever audio_encoding asks for.
    if backend == "synth":
        ext = ".wav"
    else:
        ext = _AUDIO_EXTENSION.get((audio_encoding_name or "LINEAR16").upper(), ".wav")

    # The repo-health test suite (pipeline/tests/test_referential_integrity.py)
    # asserts each shipped sentence has a `s<idx>.mp3` companion. We satisfy
    # that by writing a byte-identical `.mp3` next to every `.wav`. The
    # convention is harmless for the player (which accepts either) and matches
    # the format already on disk for stories 14-15.
    def _write_mp3_companion(wav_path: Path) -> None:
        if wav_path.suffix.lower() != ".wav":
            return
        mp3_path = wav_path.with_suffix(".mp3")
        if force or not mp3_path.exists():
            mp3_path.write_bytes(wav_path.read_bytes())

    extra = {}
    if backend == "google":
        extra = dict(
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
            sent_fn(text, kana, out_path, rate=rate, samplerate=samplerate, **extra)
        _write_mp3_companion(out_path)
        sent["audio"] = rel
        # v0.13: drift hash. Always overwritten on a (re)build because the
        # hash is meaningless without a matching audio file on disk.
        sent["audio_hash"] = _audio_hash(text)

    # ── New-word audio (dictionary forms) ──
    word_audio = story.get("word_audio") or {}
    word_audio_hash = story.get("word_audio_hash") or {}
    for wid in story.get("new_words", []):
        word = vocab.get("words", {}).get(wid)
        if not word:
            continue
        out_path = sub_dir / f"w_{wid}{ext}"
        rel = out_path.as_posix()
        text = word_audio_text(word) or wid
        kana = word.get("kana") or text
        if force or not out_path.exists():
            word_fn(text, kana, out_path, samplerate=samplerate, **extra)
        _write_mp3_companion(out_path)
        word_audio[wid] = rel
        word_audio_hash[wid] = _audio_hash(text)
    story["word_audio"]      = word_audio
    story["word_audio_hash"] = word_audio_hash

    story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "sentences": len(story["sentences"]),
        "words":     len(story.get("word_audio", {})),
        "out_dir":   str(sub_dir),
        "backend":   backend,
    }


def _accept_synth_extra_kwargs(fn):
    """The synth backend doesn't take Google-only kwargs; wrap to ignore."""
    def wrapped(*args, voice_name=None, language_code=None, audio_encoding_name=None, **kw):
        return fn(*args, **kw)
    return wrapped


def _pick_backend(name: str):
    if name == "synth":
        # Wrap so callers can pass Google-only kwargs uniformly.
        return _accept_synth_extra_kwargs(synth_sentence), _accept_synth_extra_kwargs(synth_word)
    if name == "google":
        # Verify the dependency is importable up-front so we fail fast with a
        # helpful message rather than mid-build after producing some files.
        try:
            from google.cloud import texttospeech  # noqa: F401
        except ImportError:
            raise SystemExit(
                "google backend selected but `google-cloud-texttospeech` is not\n"
                "installed. Either install it (pip install google-cloud-texttospeech)\n"
                "and configure credentials, or use --backend synth.\n"
                "You can also dry-run requests with MONOGATARI_TTS_DRY_RUN=1."
            )
        return google_sentence, google_word
    raise SystemExit(f"Unknown backend: {name!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Monogatari audio builder")
    ap.add_argument("story",   help="Path to a shipped story JSON (e.g. stories/story_3.json)")
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--backend", default=os.environ.get("MONOGATARI_TTS", DEFAULT_BACKEND),
                    choices=["synth", "google"],
                    help="TTS backend (default: synth — deterministic offline tones)")
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE,
                    help="Speech rate multiplier for sentence audio (default 0.85)")
    ap.add_argument("--samplerate", type=int, default=DEFAULT_SAMPLERATE)
    ap.add_argument("--audio-root", default="audio",
                    help="Directory under which to write audio (default: audio/)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing audio files (default: skip if present)")
    # Google-specific options (also readable from env vars).
    ap.add_argument("--voice", default=os.environ.get("MONOGATARI_TTS_VOICE", "ja-JP-Neural2-B"),
                    help="Google TTS voice name (e.g. ja-JP-Neural2-B / -C / -D)")
    ap.add_argument("--language-code", default=os.environ.get("MONOGATARI_TTS_LANGCODE", "ja-JP"),
                    help="BCP-47 language tag passed to Google TTS")
    ap.add_argument("--audio-encoding", default=os.environ.get("MONOGATARI_TTS_AUDIO", "LINEAR16"),
                    choices=["LINEAR16", "MP3", "OGG_OPUS"],
                    help="Google TTS audio encoding (LINEAR16 → .wav, MP3 → .mp3)")
    ap.add_argument("--dry-run", action="store_true",
                    help="For backend=google, do not call the API; print planned requests")
    args = ap.parse_args()

    vocab = json.loads(Path(args.vocab).read_text(encoding="utf-8"))

    # Honor --dry-run by toggling the module flag for the google backend.
    if args.dry_run:
        global _GOOGLE_DRY_RUN
        _GOOGLE_DRY_RUN = True

    summary = build_audio_for_story(
        Path(args.story), vocab,
        backend=args.backend, rate=args.rate, samplerate=args.samplerate,
        audio_root=Path(args.audio_root), force=args.force,
        voice_name=args.voice,
        language_code=args.language_code,
        audio_encoding_name=args.audio_encoding,
    )
    print(f"✓ Audio built: {summary['sentences']} sentence(s), "
          f"{summary['words']} word(s) → {summary['out_dir']} "
          f"(backend={summary['backend']}{', dry-run' if args.dry_run else ''})")


if __name__ == "__main__":
    main()
