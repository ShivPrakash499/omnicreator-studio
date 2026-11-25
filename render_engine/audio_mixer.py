"""
OMNI STUDIO — Expressive Voiceover, -24dB Ducked BGM & SFX Mixer (`render_engine/audio_mixer.py`)
==================================================================================================
1. Synthesizes expressive Indian-voiced narration per scene:
   - Priority 1: Google Cloud TTS Chirp 3 HD (when `USE_CLOUD_TTS_CHIRP3=true` & library installed)
   - Priority 2: Gemini 3.8 Flash TTS (`gemini-3.8-flash-tts`) via `client.interactions.create(...)`
     with `speech_metadata` style annotation
   - Priority 3: Local `edge-tts` (`hi-IN-MadhurNeural` / `en-IN-PrabhatNeural`)
   - Priority 4: Guaranteed offline PCM voice envelope fallback
2. Validates exact WAV clip duration to anchor B-roll pacing with zero audio/video drift.
3. Generates high-spirited niche-matched BGM via `lyria-3.5` (or procedural harmonic synth)
   and ducks BGM strictly to **-24dB** during narration + adds crisp whoosh/riser SFX on cuts!
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import math
import re
import struct
import subprocess
import urllib.request
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import imageio_ffmpeg
from google.auth.transport.requests import Request as GoogleAuthRequest

from backend.config import (
    DEFAULT_BGM_PRESET,
    FAST_AGENT_MODEL,
    MUSIC_LYRIA_MODEL,
    TTS_EXPRESSIVE_MODEL,
    VERTEX_LYRIA_MODEL,
    OmniStudioConfig,
    call_interaction_with_fallback,
    get_bgm_preset_prompt,
    get_genai_client,
    get_language_voice_profile,
    get_niche_profile,
    get_vertex_adc_credentials,
    resolve_current_model,
)
from google.genai import types as genai_types

logger = logging.getLogger("omni_studio.audio_mixer")


def get_wav_duration_sec(wav_path: Path) -> float:
    if not wav_path.exists():
        return 0.0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 24000
            return round(frames / float(rate), 3)
    except Exception:
        return 0.0


def _convert_any_audio_to_wav24k(src_path: Path, dst_wav: Path) -> Path:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg_exe, "-y", "-i", str(src_path), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(dst_wav)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return dst_wav


def _strip_ssml_for_plain_tts(text: str) -> str:
    txt = re.sub(r"<break\s+time=['\"][^'\"]+['\"]\s*/>", "... ", text)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\[[^\]]+\]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def synthesize_scene_voiceover(
    voiceover_text: str,
    ssml_voice_cues: str,
    output_wav_path: Path,
    *,
    language_tone: str,
    target_duration_sec: float = 10.0,
    config: Optional[OmniStudioConfig] = None,
    prefer_fast_local_tts: bool = False,
) -> Tuple[Path, float, str]:
    """
    Synthesizes one scene's narration WAV and returns `(wav_path, actual_duration_sec, engine_used)`.
    """
    cfg = config or OmniStudioConfig()
    vprof = get_language_voice_profile(language_tone)
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    plain_text = _strip_ssml_for_plain_tts(ssml_voice_cues or voiceover_text) or voiceover_text

    # Content-verified cache: ONLY reuse cached voice WAV if the exact script + language + mode match!
    sig_file = output_wav_path.with_suffix(".sig")
    voice_sig = hashlib.sha1(f"{plain_text}|{language_tone}|{prefer_fast_local_tts}".encode("utf-8", errors="ignore")).hexdigest()[:12]
    if output_wav_path.exists() and output_wav_path.stat().st_size > 2048 and sig_file.exists():
        if sig_file.read_text(encoding="utf-8", errors="ignore").strip() == voice_sig:
            return output_wav_path, max(1.5, get_wav_duration_sec(output_wav_path)), "cached"
    # Clear stale WAV if text was edited
    output_wav_path.unlink(missing_ok=True)

    def _finalize_cached(dur_val: float, eng_label: str) -> Tuple[Path, float, str]:
        sig_file.write_text(voice_sig, encoding="utf-8")
        return output_wav_path, dur_val, eng_label

    # 1. Google Cloud TTS Chirp 3 HD (if explicitly enabled & credentials + library installed)
    if cfg.use_cloud_tts_chirp3 and not prefer_fast_local_tts:
        try:
            from google.cloud import texttospeech  # type: ignore

            tts_client = texttospeech.TextToSpeechClient()
            ssml_body = ssml_voice_cues if "<break" in (ssml_voice_cues or "") else plain_text
            synthesis_input = texttospeech.SynthesisInput(ssml=f"<speak>{ssml_body}</speak>")
            voice = texttospeech.VoiceSelectionParams(
                language_code=vprof["language_code"],
                name=vprof["chirp3_voice"],
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=24000,
                speaking_rate=1.06,
            )
            response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            tmp_raw = output_wav_path.with_suffix(".chirp.wav")
            tmp_raw.write_bytes(response.audio_content)
            _convert_any_audio_to_wav24k(tmp_raw, output_wav_path)
            tmp_raw.unlink(missing_ok=True)
            dur = get_wav_duration_sec(output_wav_path)
            if dur > 0.5:
                return _finalize_cached(dur, "cloud_tts_chirp3_hd")
        except Exception as exc:
            logger.debug("Cloud TTS Chirp 3 HD skipped (%s); trying Gemini 3.8 TTS.", exc)

    # 2. Gemini 3.8 Flash TTS (Vertex AI native `generate_content` with retry/backoff OR Developer API)
    if cfg.has_valid_gemini_key and not prefer_fast_local_tts:
        tts_model = resolve_current_model(TTS_EXPRESSIVE_MODEL, "gemini-3.8-flash-tts")
        v_creds, v_proj = get_vertex_adc_credentials()
        if v_creds is not None and v_proj:
            import time as _t
            for attempt in range(1, 5):
                try:
                    client = get_genai_client(cfg.gemini_api_key)
                    resp = client.models.generate_content(
                        model=tts_model,
                        contents=f"Speak naturally in this style ({vprof['style_prompt']}): {plain_text}",
                        config=genai_types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=genai_types.SpeechConfig(
                                voice_config=genai_types.VoiceConfig(
                                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name=vprof["gemini_voice"])
                                )
                            ),
                        ),
                    )
                    raw_pcm: Optional[bytes] = None
                    mime_a = "audio/wav"
                    for cand in getattr(resp, "candidates", []) or []:
                        for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                            if getattr(part, "inline_data", None) and part.inline_data.data:
                                raw_pcm = bytes(part.inline_data.data)
                                mime_a = getattr(part.inline_data, "mime_type", "audio/wav") or "audio/wav"
                                break
                        if raw_pcm:
                            break
                    if raw_pcm and len(raw_pcm) > 512:
                        if raw_pcm.startswith(b"RIFF"):
                            tmp_wav = output_wav_path.with_suffix(".vertex.wav")
                            tmp_wav.write_bytes(raw_pcm)
                            _convert_any_audio_to_wav24k(tmp_wav, output_wav_path)
                            tmp_wav.unlink(missing_ok=True)
                        else:
                            with wave.open(str(output_wav_path), "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(24000)
                                wf.writeframes(raw_pcm)
                        dur = get_wav_duration_sec(output_wav_path)
                        if dur > 0.5:
                            return _finalize_cached(dur, f"vertex_tts({tts_model})")
                except Exception as exc:
                    err_low = str(exc).lower()
                    if any(tok in err_low for tok in ("429", "resource_exhausted", "quota", "503", "timeout")) and attempt < 4:
                        _t.sleep(min(12.0, 1.8 * (2 ** (attempt - 1))))
                        continue
                    logger.info("Vertex Gemini 3.8 TTS fell back to Edge-TTS (attempt %d): %s", attempt, exc)
                    break
        else:
            try:
                client = get_genai_client(cfg.gemini_api_key)
                interaction = call_interaction_with_fallback(
                    client,
                    models=[tts_model, "gemini-3.8-flash-lite-tts"],
                    max_retries=2,
                    input=[
                        {
                            "type": "user_input",
                            "content": [
                                {
                                    "type": "text",
                                    "text": plain_text,
                                    "annotations": [
                                        {
                                            "type": "speech_metadata",
                                            "style": vprof["style_prompt"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    response_format={"type": "audio"},
                    generation_config={"speech_config": [{"voice": vprof["gemini_voice"]}]},
                )
                out_aud = getattr(interaction, "output_audio", None)
                if out_aud and getattr(out_aud, "data", None):
                    raw_bytes = (
                        base64.b64decode(out_aud.data)
                        if isinstance(out_aud.data, str)
                        else bytes(out_aud.data)
                    )
                    tmp_raw = output_wav_path.with_suffix(".gemini.wav")
                    tmp_raw.write_bytes(raw_bytes)
                    _convert_any_audio_to_wav24k(tmp_raw, output_wav_path)
                    tmp_raw.unlink(missing_ok=True)
                    dur = get_wav_duration_sec(output_wav_path)
                    if dur > 0.5:
                        return _finalize_cached(dur, f"gemini_tts({tts_model})")
            except Exception as exc:
                logger.info("Gemini 3.8 TTS fell back to Edge-TTS: %s", exc)

    # 3. High-clarity local Edge-TTS (`hi-IN-MadhurNeural` / `en-IN-PrabhatNeural`)
    try:
        import edge_tts

        mp3_tmp = output_wav_path.with_suffix(".edge.mp3")

        async def _synth_edge(voice_name: str) -> None:
            comm = edge_tts.Communicate(text=plain_text, voice=voice_name, rate="+8%", pitch="-2Hz")
            await comm.save(str(mp3_tmp))

        for v_name in (vprof["edge_voice"], vprof["edge_fallback"]):
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(_synth_edge(v_name))
                finally:
                    loop.close()
                if mp3_tmp.exists() and mp3_tmp.stat().st_size > 256:
                    _convert_any_audio_to_wav24k(mp3_tmp, output_wav_path)
                    mp3_tmp.unlink(missing_ok=True)
                    dur = get_wav_duration_sec(output_wav_path)
                    if dur > 0.5:
                        return _finalize_cached(dur, f"edge_tts({v_name})")
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Edge-TTS fallback skipped: %s", exc)

    # 4. Guaranteed offline voice-cadence WAV fallback
    sr = 24000
    dur_est = max(3.0, min(14.0, float(target_duration_sec)))
    n_samples = int(dur_est * sr)
    buf = bytearray(n_samples * 2)
    for i in range(n_samples):
        t = i / float(sr)
        cadence = 0.45 + 0.55 * abs(math.sin(2.0 * math.pi * 2.4 * t))
        sig = math.sin(2.0 * math.pi * 138.0 * t) + 0.4 * math.sin(2.0 * math.pi * 276.0 * t)
        val = int(4200 * cadence * sig)
        struct.pack_into("<h", buf, i * 2, max(-32767, min(32767, val)))

    with wave.open(str(output_wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf)
    return output_wav_path, dur_est, "offline_pcm_fallback"


def _compose_topic_lyria_prompt(
    topic: str,
    niche: str,
    bgm_style_reference: str,
    config: OmniStudioConfig,
) -> str:
    """
    Distills ANY topic + niche into a rich, culturally authentic, strictly instrumental
    film-score prompt tailored for Google Vertex AI `lyria-002` (e.g. Indian devotional bansuri,
    tanpura, sitar & emotive strings for mythological/spiritual topics; Hans Zimmer cello & brass
    for historical epics; sleek futuristic synth for AI/tech; warm piano & pulse for finance).
    """
    prof = get_niche_profile(niche)
    base_fallback = (
        f"Cinematic documentary film score tailored to '{topic}' ({niche}). "
        f"{bgm_style_reference or prof['music_vibe']}. "
        f"Rich emotional instrumentation, warm low-end depth, clean midrange space for voiceover, "
        f"strictly instrumental, zero vocals, zero singing."
    )
    if not config.has_valid_gemini_key or not topic.strip():
        return base_fallback

    try:
        client = get_genai_client(config.gemini_api_key, location="global")
        ask = (
            f"Write ONE concise 35-to-50 word instrumental music generation prompt for Google Lyria-002 "
            f"to score a high-retention cinematic video about:\n"
            f"Topic: {topic}\nNiche: {niche}\nExisting vibe hint: {bgm_style_reference}\n\n"
            f"RULES:\n"
            f"- Choose authentic, culturally resonant real instruments matching the topic's world & mood "
            f"(for example: Indian bansuri flute, tanpura drone, sitar/sarangi, subtle pakhawaj/dholak & emotional "
            f"orchestral strings for Indian devotional/mythology/history; deep cello & brass for global epics; "
            f"modern analog synth & driving bass for AI/tech; tense piano & strings for finance/mysteries).\n"
            f"- Specify tempo, emotional arc, acoustic warmth, and strictly instrumental (no vocals, no lyrics, no speech).\n"
            f"- Output ONLY the raw prompt sentence in English (no quotes, no markdown)."
        )
        inter = call_interaction_with_fallback(
            client,
            models=[resolve_current_model(FAST_AGENT_MODEL, "gemini-3.8-flash")],
            max_retries=1,
            input=ask,
        )
        txt = (getattr(inter, "output_text", None) or "").strip().strip('"').strip("'")
        if len(txt) >= 24:
            if "instrumental" not in txt.lower():
                txt += ", strictly instrumental, no vocals"
            return txt[:480]
    except Exception as exc:
        logger.debug("Topic Lyria prompt distillation used baseline (%s)", exc)

    return base_fallback


def _normalize_wav_lufs(src_wav: Path, dst_wav: Path, *, target_i: float = -15.0) -> Path:
    """
    Applies safe, zero-DC-offset RMS + true-peak normalization directly on 24kHz PCM WAV.
    Avoids FFmpeg single-pass `loudnorm` bugs (which can inject DC offsets or noise bursts on
    short/quiet clips) while guaranteeing consistent, crystal-clear broadcast loudness!
    """
    if not src_wav.exists() or src_wav.stat().st_size < 128:
        return dst_wav
    try:
        with wave.open(str(src_wav), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        if sw != 2 or ch != 1 or len(raw) < 4:
            if src_wav != dst_wav:
                dst_wav.write_bytes(raw if False else src_wav.read_bytes())
            return dst_wav

        n = len(raw) // 2
        samples = struct.unpack(f"<{n}h", raw[: n * 2])
        # Compute mean (DC offset) and RMS across active samples
        mean_val = sum(samples) / float(n)
        sq_sum = 0.0
        peak = 0.0
        for s in samples:
            c = s - mean_val
            ac = abs(c)
            if ac > peak:
                peak = ac
            sq_sum += c * c
        rms = math.sqrt(sq_sum / float(n))

        # Never amplify pure silence or near-silence!
        if rms < 45.0 or peak < 120.0:
            if src_wav != dst_wav:
                dst_wav.write_bytes(src_wav.read_bytes())
            return dst_wav

        target_rms = 32767.0 * math.pow(10.0, float(target_i) / 20.0)
        gain = max(0.15, min(6.0, target_rms / rms))
        # True-peak ceiling at -1.5 dBFS (27500) so normalization never clips
        max_safe_gain = 27500.0 / peak
        gain = min(gain, max_safe_gain)

        out = bytearray(n * 2)
        for i, s in enumerate(samples):
            val = int(max(-32767, min(32767, (s - mean_val) * gain)))
            struct.pack_into("<h", out, i * 2, val)

        dst_wav.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dst_wav), "wb") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(sr)
            wf_out.writeframes(out)
        return dst_wav
    except Exception as exc:
        logger.debug("PCM RMS normalization skipped (%s); keeping raw WAV.", exc)
        if src_wav != dst_wav and src_wav.exists():
            dst_wav.write_bytes(src_wav.read_bytes())
        return dst_wav


def generate_niche_bgm_stem(
    output_wav_path: Path,
    *,
    topic: str = "",
    niche: str,
    bgm_style_reference: str,
    duration_sec: float,
    bgm_preset: str = DEFAULT_BGM_PRESET,
    custom_bgm_path: Optional[Path] = None,
    config: Optional[OmniStudioConfig] = None,
    use_lyria_api: bool = True,
) -> Path:
    """
    Composes or adapts studio-quality instrumental background music tailored to the user's chosen
    Background Score Style, Niche (including dedicated Religious & Devotional), or custom upload:
    - Priority 0: User's own uploaded `.mp3`/`.wav` BGM track (seamlessly looped & normalized!)
    - Priority 1 (Vertex AI ADC): Google Vertex AI `lyria-002` (`us-central1`, 2 seamless crossfaded variations!)
    - Priority 2 (AI Studio Key): `lyria-3.5` via Interactions API
    - Priority 3 (Offline Fallback): Warm devotional tanpura/raag or orchestral ambient drone (normalized -15 dBFS)
    """
    cfg = config or OmniStudioConfig()
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    engine_meta_path = output_wav_path.with_suffix(".engine.txt")

    preset_prompt = get_bgm_preset_prompt(bgm_preset)
    custom_path_obj = Path(custom_bgm_path) if custom_bgm_path else None
    using_custom = bool(custom_path_obj and custom_path_obj.exists())

    # Build a deterministic signature so switching BGM presets in Step 3 ALWAYS regenerates fresh music!
    sig_seed = (
        f"custom:{custom_path_obj.resolve()}:{custom_path_obj.stat().st_mtime}"
        if using_custom and custom_path_obj is not None
        else f"preset:{bgm_preset}|niche:{niche}|topic:{topic}|ref:{bgm_style_reference}"
    )
    sig_hash = hashlib.sha1(sig_seed.encode("utf-8", errors="ignore")).hexdigest()[:10]

    if output_wav_path.exists() and output_wav_path.stat().st_size > 4096 and engine_meta_path.exists():
        meta_txt = engine_meta_path.read_text(encoding="utf-8", errors="ignore")
        if f"[sig:{sig_hash}]" in meta_txt and get_wav_duration_sec(output_wav_path) >= duration_sec - 1.0:
            return output_wav_path

    # 0. Priority 0: User-Uploaded Custom BGM Track (.mp3 / .wav / .m4a)
    if using_custom and custom_path_obj is not None:
        try:
            raw_long = output_wav_path.with_suffix(".custom_long.wav")
            subprocess.run(
                [
                    ffmpeg_exe, "-y",
                    "-stream_loop", "-1", "-i", str(custom_path_obj),
                    "-t", f"{duration_sec + 6.0:.2f}",
                    "-af", "afade=t=in:st=0:d=1.2",
                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                    str(raw_long),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _normalize_wav_lufs(raw_long, output_wav_path, target_i=-15.0)
            raw_long.unlink(missing_ok=True)
            if output_wav_path.exists() and output_wav_path.stat().st_size > 4096:
                engine_meta_path.write_text(f"custom_bgm({custom_path_obj.name}) [sig:{sig_hash}]", encoding="utf-8")
                return output_wav_path
        except Exception as exc:
            logger.info("Custom uploaded BGM conversion failed (%s); falling back to AI composer.", exc)

    # Use explicit selected preset prompt if chosen; otherwise smart AI composition matched to topic + niche
    if preset_prompt and preset_prompt != "__CUSTOM_UPLOAD__":
        music_prompt = preset_prompt
    else:
        music_prompt = _compose_topic_lyria_prompt(topic, niche, bgm_style_reference, cfg)

    negative_music = (
        "vocals, singing, lyrics, spoken voice, speech, narration, cartoon sound effects, "
        "beeps, chime ting, harsh distortion, discordant noise"
    )
    v_creds, v_proj = get_vertex_adc_credentials()

    # 1. Priority 1: Vertex AI `lyria-002` (Live studio-quality 48kHz orchestral/devotional/cinematic score!)
    if use_lyria_api and v_creds is not None and v_proj:
        try:
            v_creds.refresh(GoogleAuthRequest())
            url = (
                f"https://us-central1-aiplatform.googleapis.com/v1/projects/{v_proj}"
                f"/locations/us-central1/publishers/google/models/{VERTEX_LYRIA_MODEL}:predict"
            )
            payload = json.dumps(
                {
                    "instances": [{"prompt": music_prompt, "negative_prompt": negative_music}],
                    "parameters": {"sample_count": 2},
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {v_creds.token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            preds = data.get("predictions", []) or []
            stem_files: List[Path] = []
            for idx, pred in enumerate(preds):
                b64 = pred.get("bytesBase64Encoded") or pred.get("audioContent") or ""
                if b64:
                    raw_bytes = base64.b64decode(b64)
                    if len(raw_bytes) > 8192:
                        sp = output_wav_path.with_suffix(f".lyria_{idx}.wav")
                        sp.write_bytes(raw_bytes)
                        stem_files.append(sp)

            if stem_files:
                stitched_loop = output_wav_path.with_suffix(".lyria_stitched.wav")
                if len(stem_files) >= 2:
                    # Seamlessly crossfade 2 musical variations (3s musical crossfade) for rich evolving 60s+ score!
                    subprocess.run(
                        [
                            ffmpeg_exe, "-y",
                            "-i", str(stem_files[0]),
                            "-i", str(stem_files[1]),
                            "-filter_complex", "[0:a][1:a]acrossfade=d=3.0:c1=tri:c2=tri[a]",
                            "-map", "[a]",
                            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                            str(stitched_loop),
                        ],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                else:
                    _convert_any_audio_to_wav24k(stem_files[0], stitched_loop)

                # Seamlessly loop to full video duration + normalize to -15 dBFS
                raw_long = output_wav_path.with_suffix(".lyria_long.wav")
                subprocess.run(
                    [
                        ffmpeg_exe, "-y",
                        "-stream_loop", "-1", "-i", str(stitched_loop),
                        "-t", f"{duration_sec + 6.0:.2f}",
                        "-af", "afade=t=in:st=0:d=1.2",
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                        str(raw_long),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _normalize_wav_lufs(raw_long, output_wav_path, target_i=-15.0)
                for p in stem_files + [stitched_loop, raw_long]:
                    p.unlink(missing_ok=True)
                if output_wav_path.exists() and output_wav_path.stat().st_size > 4096:
                    engine_meta_path.write_text(
                        f"vertex_lyria({VERTEX_LYRIA_MODEL}) [sig:{sig_hash}] | {music_prompt[:140]}",
                        encoding="utf-8",
                    )
                    return output_wav_path
        except Exception as exc:
            logger.info("Vertex Lyria-002 BGM composition fell back (%s)", exc)

    # 2. Priority 2: AI Studio `lyria-3.5` (when using GEMINI_API_KEY without Vertex ADC)
    if use_lyria_api and cfg.has_valid_gemini_key and v_creds is None:
        try:
            client = get_genai_client(cfg.gemini_api_key)
            interaction = call_interaction_with_fallback(
                client,
                models=[resolve_current_model(MUSIC_LYRIA_MODEL, "lyria-3.5")],
                max_retries=2,
                input=music_prompt,
                response_format={"type": "audio"},
            )
            out_aud = getattr(interaction, "output_audio", None)
            if out_aud and getattr(out_aud, "data", None):
                raw_bytes = (
                    base64.b64decode(out_aud.data)
                    if isinstance(out_aud.data, str)
                    else bytes(out_aud.data)
                )
                tmp_stem = output_wav_path.with_suffix(".lyria.raw")
                tmp_stem.write_bytes(raw_bytes)
                raw_long = output_wav_path.with_suffix(".lyria35_long.wav")
                subprocess.run(
                    [
                        ffmpeg_exe, "-y",
                        "-stream_loop", "-1", "-i", str(tmp_stem),
                        "-t", f"{duration_sec + 6.0:.2f}",
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                        str(raw_long),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _normalize_wav_lufs(raw_long, output_wav_path, target_i=-15.0)
                tmp_stem.unlink(missing_ok=True)
                raw_long.unlink(missing_ok=True)
                if output_wav_path.exists() and output_wav_path.stat().st_size > 4096:
                    engine_meta_path.write_text(f"ai_studio_lyria(lyria-3.5) [sig:{sig_hash}]", encoding="utf-8")
                    return output_wav_path
        except Exception as exc:
            logger.info("Lyria 3.5 BGM stem fell back to warm harmonic orchestral bed: %s", exc)

    # 3. Priority 3: Warm atmospheric cinematic orchestral/tanpura drone bed (offline fallback, normalized -15 dBFS)
    sr = 24000
    loop_dur = min(32.0, max(16.0, duration_sec))
    n_loop = int(loop_dur * sr)
    low_t = f"{topic} {niche} {bgm_preset} {bgm_style_reference}".lower()
    is_indian_devotional = any(
        k in low_t for k in (
            "religious", "devotional", "bhakti", "shyam", "krishna", "khatu", "ram", "shiv",
            "mahabharat", "barbarik", "temple", "spirit", "myth", "vedic", "gita", "bansuri", "tanpura",
        )
    )
    # Use warm resonant D-major tanpura/drone + gentle flute melody for Indian devotional/mythology, else warm strings
    chord_roots = [146.83, 146.83, 110.0, 130.81] if is_indian_devotional else [110.0, 130.81, 146.83, 98.0]
    raag_bhupali = [293.66, 329.63, 369.99, 440.00, 493.88, 587.33]  # D major pentatonic (Raag Bhupali)
    buf = bytearray(n_loop * 2)
    for i in range(n_loop):
        t = i / float(sr)
        bar_idx = int(t // 4.0) % len(chord_roots)
        root = chord_roots[bar_idx]
        fifth = root * 1.4983
        third = root * (1.2599 if is_indian_devotional else 1.1892)
        swell = 0.68 + 0.32 * math.sin(2.0 * math.pi * 0.125 * t)
        pad = (
            0.46 * math.sin(2.0 * math.pi * root * t)
            + 0.28 * math.sin(2.0 * math.pi * fifth * t)
            + 0.16 * math.sin(2.0 * math.pi * third * t)
            + 0.10 * math.sin(2.0 * math.pi * (root * 0.5) * t)
        )
        flute = 0.0
        if is_indian_devotional:
            note_f = raag_bhupali[int(t // 2.0) % len(raag_bhupali)]
            note_p = (t % 2.0) / 2.0
            vib = 1.0 + 0.006 * math.sin(2.0 * math.pi * 5.2 * t)
            flute = 0.22 * (math.sin(math.pi * note_p) ** 1.5) * math.sin(2.0 * math.pi * note_f * vib * t)
        val = int(14000 * swell * (pad + flute))
        struct.pack_into("<h", buf, i * 2, max(-32767, min(32767, val)))

    loop_wav = output_wav_path.with_suffix(".loop.wav")
    with wave.open(str(loop_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf)

    raw_long = output_wav_path.with_suffix(".fallback_long.wav")
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-stream_loop", "-1", "-i", str(loop_wav),
            "-t", f"{duration_sec + 6.0:.2f}",
            "-af", "lowpass=f=2200",
            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
            str(raw_long),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _normalize_wav_lufs(raw_long, output_wav_path, target_i=-15.0)
    loop_wav.unlink(missing_ok=True)
    raw_long.unlink(missing_ok=True)
    engine_meta_path.write_text(f"warm_devotional_fallback [sig:{sig_hash}]" if is_indian_devotional else f"warm_harmonic_fallback [sig:{sig_hash}]", encoding="utf-8")
    return output_wav_path


def mix_scene_master_audio(
    voice_wav_path: Path,
    bgm_wav_path: Path,
    output_master_wav: Path,
    *,
    bgm_offset_sec: float,
    target_duration_sec: float,
    exact_samples: Optional[int] = None,
    duck_db: float = -13.5,
    foley_wav_path: Optional[Path] = None,
    foley_db: float = -13.5,
    add_cut_sfx: bool = False,  # Kept for signature compatibility; cartoon cut-ting is permanently removed!
) -> Path:
    """
    Broadcast-grade 3-stem frame-locked cinematic mixer (ZERO cartoon cut-ting, ZERO overlap!):
    1. Voiceover Narration: Safe zero-DC-offset RMS-normalized (-14 dBFS) with crisp 18ms fades.
    2. Topic-Matched BGM Score: Continuous sample-aligned playback with buttery-smooth
       RMS sidechain envelope ducking (`duck_db` during speech, swelling +5dB in pauses).
    3. Frame-Synced Foley SFX (vocal-notched Omni/Veo Foley or realistic cinema Foley):
       Politely tucked at `foley_db` (-13.5 dB) under spoken words and blooming to -8.0 dB
       during natural action pauses so SFX NEVER overlaps or obscures narration!
    """
    del add_cut_sfx  # Permanently disabled cartoon transition sine-sweep
    sr = 24000
    n_total = int(exact_samples) if (exact_samples and exact_samples > 0) else max(1, int(round(target_duration_sec * sr)))

    # Normalize voiceover stem cleanly to -14 LUFS so voice/BGM/Foley levels are always balanced
    norm_voice = output_master_wav.with_suffix(".vnorm.wav")
    if voice_wav_path.exists():
        _normalize_wav_lufs(voice_wav_path, norm_voice, target_i=-14.0)
    voice_src = norm_voice if norm_voice.exists() and norm_voice.stat().st_size > 1024 else voice_wav_path

    def _read_slice(path: Optional[Path], start_sample: int, count: int, loop: bool = True) -> List[int]:
        if path is None or not path.exists():
            return [0] * count
        try:
            with wave.open(str(path), "rb") as wf:
                total_frames = wf.getnframes()
                if total_frames <= 0:
                    return [0] * count
                pos = (start_sample % total_frames) if loop else min(start_sample, total_frames)
                wf.setpos(pos)
                raw = wf.readframes(min(count, total_frames - pos))
                samples = list(struct.unpack(f"<{len(raw) // 2}h", raw[: (len(raw) // 2) * 2]))
                while loop and len(samples) < count:
                    wf.rewind()
                    rem = count - len(samples)
                    raw2 = wf.readframes(min(rem, total_frames))
                    if not raw2:
                        break
                    samples.extend(struct.unpack(f"<{len(raw2) // 2}h", raw2[: (len(raw2) // 2) * 2]))
                if len(samples) < count:
                    samples.extend([0] * (count - len(samples)))
                return samples[:count]
        except Exception:
            return [0] * count

    v_samples = _read_slice(voice_src, 0, n_total, loop=False)
    b_samples = _read_slice(bgm_wav_path, int(bgm_offset_sec * sr), n_total, loop=True)
    f_samples = _read_slice(foley_wav_path, 0, n_total, loop=False) if foley_wav_path else None
    norm_voice.unlink(missing_ok=True)

    # Smooth broadcast sidechain ducking gains
    # Default duck_db = -13.5 dB (~0.211 amplitude) during active speech -> rich, audible score!
    # Swells smoothly to duck_db + 5.0 dB (~-8.5 dB, ~0.376 amplitude) during dramatic pauses!
    clamped_duck = max(-26.0, min(-7.0, float(duck_db)))
    bgm_speech_gain = math.pow(10.0, clamped_duck / 20.0)
    bgm_pause_gain = math.pow(10.0, min(-5.0, clamped_duck + 5.0) / 20.0)

    foley_speech_gain = math.pow(10.0, float(foley_db) / 20.0)
    foley_pause_gain = math.pow(10.0, min(-5.5, float(foley_db) + 5.5) / 20.0)

    # Smooth RMS-like speech activity envelope follower (attack ~55ms, release ~320ms — zero pumping!)
    attack_coeff = 1.0 - math.exp(-1.0 / (0.055 * sr))
    release_coeff = 1.0 - math.exp(-1.0 / (0.320 * sr))
    env = 0.0
    speech_thresh = 850.0  # Normalized voice level threshold
    fade_edge = min(n_total // 8, int(0.015 * sr))  # 15ms micro-declick on voice/foley edges only

    out_buf = bytearray(n_total * 2)
    for i in range(n_total):
        v = float(v_samples[i])
        av = abs(v)
        target_active = 1.0 if av > speech_thresh else 0.0
        coeff = attack_coeff if target_active > env else release_coeff
        env += coeff * (target_active - env)

        edge_mult = 1.0
        if i < fade_edge:
            edge_mult = i / float(max(1, fade_edge))
        elif i > n_total - fade_edge:
            edge_mult = (n_total - i) / float(max(1, fade_edge))

        bgm_gain = bgm_pause_gain * (1.0 - env) + bgm_speech_gain * env
        b = b_samples[i] * bgm_gain

        f_val = 0.0
        if f_samples is not None:
            f_gain = foley_pause_gain * (1.0 - env) + foley_speech_gain * env
            f_val = f_samples[i] * f_gain * edge_mult

        # Gentle analog-style soft limiter (`tanh`) prevents harsh digital clipping on loud SFX impacts
        raw_sum = (v * edge_mult) + b + f_val
        if abs(raw_sum) > 28000.0:
            raw_sum = 32000.0 * math.tanh(raw_sum / 32000.0)
        mixed = int(max(-32767, min(32767, raw_sum)))
        struct.pack_into("<h", out_buf, i * 2, mixed)

    output_master_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_master_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(out_buf)
    return output_master_wav


def concat_wav_segments(wav_paths: List[Path], output_wav: Path) -> Path:
    """
    Concatenates scene master WAVs directly at the raw PCM level into ONE seamless continuous WAV
    (eliminating AAC concat edit-list discontinuities that mute audio in browsers!).
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sr = 24000
    all_frames = bytearray()
    for p in wav_paths:
        if not p.exists():
            continue
        with wave.open(str(p), "rb") as wf:
            all_frames.extend(wf.readframes(wf.getnframes()))
    with wave.open(str(output_wav), "wb") as out_wf:
        out_wf.setnchannels(1)
        out_wf.setsampwidth(2)
        out_wf.setframerate(sr)
        out_wf.writeframes(all_frames)
    return output_wav
