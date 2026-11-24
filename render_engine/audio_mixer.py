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
import logging
import math
import re
import struct
import subprocess
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import imageio_ffmpeg

from backend.config import (
    MUSIC_LYRIA_MODEL,
    TTS_EXPRESSIVE_MODEL,
    OmniStudioConfig,
    call_interaction_with_fallback,
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
    if output_wav_path.exists() and output_wav_path.stat().st_size > 2048:
        return output_wav_path, max(1.5, get_wav_duration_sec(output_wav_path)), "cached"

    cfg = config or OmniStudioConfig()
    vprof = get_language_voice_profile(language_tone)
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    plain_text = _strip_ssml_for_plain_tts(ssml_voice_cues or voiceover_text) or voiceover_text

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
                return output_wav_path, dur, "cloud_tts_chirp3_hd"
        except Exception as exc:
            logger.debug("Cloud TTS Chirp 3 HD skipped (%s); trying Gemini 3.8 TTS.", exc)

    # 2. Gemini 3.8 Flash TTS (Vertex AI native `generate_content` OR Developer API `interactions.create`)
    if cfg.has_valid_gemini_key and not prefer_fast_local_tts:
        try:
            tts_model = resolve_current_model(TTS_EXPRESSIVE_MODEL, "gemini-3.8-flash-tts")
            client = get_genai_client(cfg.gemini_api_key)
            v_creds, v_proj = get_vertex_adc_credentials()
            if v_creds is not None and v_proj:
                resp = client.models.generate_content(
                    model=tts_model,
                    contents=f"Speak with this style ({vprof['style_prompt']}): {plain_text}",
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
                if raw_pcm:
                    if "pcm" in mime_a.lower() or "l16" in mime_a.lower() or not raw_pcm.startswith(b"RIFF"):
                        with wave.open(str(output_wav_path), "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(24000)
                            wf.writeframes(raw_pcm)
                    else:
                        tmp_raw = output_wav_path.with_suffix(".vertex.raw")
                        tmp_raw.write_bytes(raw_pcm)
                        _convert_any_audio_to_wav24k(tmp_raw, output_wav_path)
                        tmp_raw.unlink(missing_ok=True)
                    dur = get_wav_duration_sec(output_wav_path)
                    if dur > 0.5:
                        return output_wav_path, dur, f"vertex_tts({tts_model})"
            else:
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
                    tmp_raw = output_wav_path.with_suffix(".gemini.raw")
                    tmp_raw.write_bytes(raw_bytes)
                    _convert_any_audio_to_wav24k(tmp_raw, output_wav_path)
                    tmp_raw.unlink(missing_ok=True)
                    dur = get_wav_duration_sec(output_wav_path)
                    if dur > 0.5:
                        return output_wav_path, dur, f"gemini_tts({tts_model})"
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
                        return output_wav_path, dur, f"edge_tts({v_name})"
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


def generate_niche_bgm_stem(
    output_wav_path: Path,
    *,
    niche: str,
    bgm_style_reference: str,
    duration_sec: float,
    config: Optional[OmniStudioConfig] = None,
    use_lyria_api: bool = True,
) -> Path:
    """
    Generates high-spirited instrumental background music tailored to the niche & top-performing
    search video via `lyria-3.5` (with clean procedural harmonic synth fallback).
    """
    if output_wav_path.exists() and output_wav_path.stat().st_size > 4096:
        if get_wav_duration_sec(output_wav_path) >= duration_sec - 1.0:
            return output_wav_path

    cfg = config or OmniStudioConfig()
    prof = get_niche_profile(niche)
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    music_prompt = (
        f"{prof['music_vibe']}. Reference vibe: {bgm_style_reference}. "
        f"High-spirited, engaging YouTube documentary pace, clean midrange space so voiceover sits cleanly on top."
    )

    if use_lyria_api and cfg.has_valid_gemini_key:
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
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run(
                    [
                        ffmpeg_exe, "-y",
                        "-stream_loop", "-1", "-i", str(tmp_stem),
                        "-t", f"{duration_sec + 4.0:.2f}",
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                        str(output_wav_path),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                tmp_stem.unlink(missing_ok=True)
                if output_wav_path.exists() and output_wav_path.stat().st_size > 4096:
                    return output_wav_path
        except Exception as exc:
            logger.info("Lyria 3.5 BGM stem fell back to procedural modern synth bed: %s", exc)

    # Procedural upbeat cinematic electronic documentary bed (zero childish tones)
    sr = 24000
    loop_dur = min(30.0, max(12.0, duration_sec))
    n_loop = int(loop_dur * sr)
    chord_roots = [110.0, 130.81, 146.83, 98.0]  # A2 -> C3 -> D3 -> G2 modern documentary progression
    buf = bytearray(n_loop * 2)
    for i in range(n_loop):
        t = i / float(sr)
        bar_idx = int(t // 2.0) % len(chord_roots)
        root = chord_roots[bar_idx]
        fifth = root * 1.498
        octave = root * 2.0
        beat_pulse = 0.65 + 0.35 * (max(0.0, math.sin(2.0 * math.pi * 2.0 * t)) ** 2)
        arp = 0.20 * (max(0.0, math.sin(2.0 * math.pi * 4.0 * t)) ** 4) * math.sin(2.0 * math.pi * octave * t)
        pad = 0.50 * math.sin(2.0 * math.pi * root * t) + 0.30 * math.sin(2.0 * math.pi * fifth * t)
        val = int(9000 * beat_pulse * (pad + arp))
        struct.pack_into("<h", buf, i * 2, max(-32767, min(32767, val)))

    loop_wav = output_wav_path.with_suffix(".loop.wav")
    with wave.open(str(loop_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-stream_loop", "-1", "-i", str(loop_wav),
            "-t", f"{duration_sec + 4.0:.2f}",
            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
            str(output_wav_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    loop_wav.unlink(missing_ok=True)
    return output_wav_path


def mix_scene_master_audio(
    voice_wav_path: Path,
    bgm_wav_path: Path,
    output_master_wav: Path,
    *,
    bgm_offset_sec: float,
    target_duration_sec: float,
    duck_db: float = -24.0,
    add_cut_sfx: bool = True,
) -> Path:
    """
    Mixes one scene's narration with the continuous BGM stem ducked strictly to **-24dB**
    during active narration + subtle tactile riser/whoosh SFX at scene transition.
    """
    sr = 24000
    n_total = max(1, int(round(target_duration_sec * sr)))

    def _read_slice(path: Path, start_sample: int, count: int) -> List[int]:
        if not path.exists():
            return [0] * count
        with wave.open(str(path), "rb") as wf:
            total_frames = wf.getnframes()
            if total_frames <= 0:
                return [0] * count
            pos = start_sample % total_frames
            wf.setpos(pos)
            raw = wf.readframes(min(count, total_frames - pos))
            samples = list(struct.unpack(f"<{len(raw) // 2}h", raw[: (len(raw) // 2) * 2]))
            if len(samples) < count:
                wf.rewind()
                rem = count - len(samples)
                raw2 = wf.readframes(min(rem, total_frames))
                samples.extend(struct.unpack(f"<{len(raw2) // 2}h", raw2[: (len(raw2) // 2) * 2]))
            if len(samples) < count:
                samples.extend([0] * (count - len(samples)))
            return samples[:count]

    v_samples = _read_slice(voice_wav_path, 0, n_total)
    b_samples = _read_slice(bgm_wav_path, int(bgm_offset_sec * sr), n_total)

    # -24dB amplitude ratio = 10^(-24/20) = 0.0631
    duck_gain = math.pow(10.0, float(duck_db) / 20.0)
    pause_gain = min(0.16, duck_gain * 1.9)
    sfx_len = min(n_total, int(0.32 * sr))

    out_buf = bytearray(n_total * 2)
    for i in range(n_total):
        v = v_samples[i]
        gain = duck_gain if abs(v) > 380 else pause_gain
        b = int(b_samples[i] * gain)

        sfx = 0
        if add_cut_sfx and i < sfx_len:
            prog = i / float(sfx_len)
            env = math.sin(math.pi * prog)
            freq = 140.0 + 480.0 * (prog ** 1.6)
            sfx = int(2200 * env * math.sin(2.0 * math.pi * freq * (i / float(sr))))

        mixed = max(-32767, min(32767, v + b + sfx))
        struct.pack_into("<h", out_buf, i * 2, mixed)

    output_master_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_master_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(out_buf)
    return output_master_wav
