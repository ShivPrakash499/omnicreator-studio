"""
OMNI STUDIO — Frame-Synced Native Foley Extractor & Procedural Cinema Foley Engine
==================================================================================
Provides authentic Hollywood/documentary sound effects synced to on-screen action:
1. Priority 1 (Best): Extracts native frame-accurate Foley SFX directly from
   `gemini-omni-1.2-flash` and Vertex `veo-3.1-generate-001` MP4 audio streams
   (bowstring snaps, flaming arrows, spinning Sudarshan Chakra, rain, thunder, engines)
   with gentle speech-pocket EQ and clean 50ms edge fades (ZERO clicks or cartoon tings!).
2. Priority 2 (Fallback for Keyframes / Silent Clips): Synthesizes realistic,
   physically textured multi-band cinema Foley matched to `sfx_cue` & `visual_prompt`
   (arrow release & whistle, revolving metallic chakra/vortex hum, rolling thunder,
   warm low bronze temple resonance, crackling fire, rain/wind, deep sci-fi drive).
"""

from __future__ import annotations

import logging
import math
import random
import struct
import subprocess
import wave
from pathlib import Path
from typing import List, Optional

import imageio_ffmpeg

logger = logging.getLogger("omni_studio.foley_sfx")

SAMPLE_RATE = 24000


def _compute_wav_rms(wav_path: Path) -> float:
    if not wav_path.exists() or wav_path.stat().st_size < 1024:
        return 0.0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            n = len(raw) // 2
            if n <= 0:
                return 0.0
            samples = struct.unpack(f"<{n}h", raw[: n * 2])
            step = max(1, n // 4000)
            sq_sum = 0.0
            cnt = 0
            for i in range(0, n, step):
                s = samples[i]
                sq_sum += s * s
                cnt += 1
            return math.sqrt(sq_sum / max(1, cnt))
    except Exception:
        return 0.0


def extract_native_video_foley(
    raw_video_path: Path,
    output_foley_wav: Path,
    *,
    target_duration_sec: float,
) -> Optional[Path]:
    """
    Extracts frame-accurate native Foley SFX ONCE from an Omni 1.2 Flash or Veo 3.1 MP4 clip
    (NEVER loops audio mid-scene!). Applies vocal-formant notch EQ (suppressing any accidental
    model speech/singing so it never overlaps our narrator!), pads trailing silence to exact
    scene duration, and adds clean 60ms fade-in / 250ms fade-out.
    Returns `output_foley_wav` if real non-silent audio was present, else `None`.
    """
    if not raw_video_path.exists():
        return None
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    dur = max(1.0, float(target_duration_sec))
    exact_samples = int(round(dur * SAMPLE_RATE))
    output_foley_wav.parent.mkdir(parents=True, exist_ok=True)

    # Probe if raw video contains an audio stream & measure its actual source duration
    probe = subprocess.run(
        [ffmpeg_exe, "-i", str(raw_video_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stderr_txt = probe.stderr or ""
    if "Audio:" not in stderr_txt:
        return None

    import re as _re
    src_dur = dur
    m_dur = _re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr_txt)
    if m_dur:
        src_dur = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))
    play_dur = max(0.5, min(dur, src_dur))
    fade_out_d = min(0.28, play_dur * 0.25)
    fade_out_st = max(0.05, play_dur - fade_out_d)

    # Suppress speech/vocal formants (350Hz, 1.2kHz, 2.6kHz) so accidental Omni voices never overlap narrator,
    # while keeping crisp Foley transients (arrows, chakra shimmer, thunder sub-bass, fire, rain) vivid!
    af_chain = (
        f"highpass=f=55,"
        f"equalizer=f=350:width_type=q:w=0.9:g=-7,"
        f"equalizer=f=1200:width_type=q:w=0.8:g=-9,"
        f"equalizer=f=2600:width_type=q:w=1.0:g=-7,"
        f"afade=t=in:st=0:d=0.06,"
        f"afade=t=out:st={fade_out_st:.3f}:d={fade_out_d:.3f},"
        f"apad=whole_dur={dur:.4f}"
    )
    try:
        subprocess.run(
            [
                ffmpeg_exe, "-y",
                "-i", str(raw_video_path),
                "-vn",
                "-t", f"{dur:.4f}",
                "-af", af_chain,
                "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le",
                str(output_foley_wav),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        rms = _compute_wav_rms(output_foley_wav)
        if rms > 120.0:
            # Normalize native Foley gently to ~-18 dBFS RMS & lock to exact sample count
            with wave.open(str(output_foley_wav), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            n = len(raw) // 2
            samples = list(struct.unpack(f"<{n}h", raw[: n * 2]))
            if len(samples) < exact_samples:
                samples.extend([0] * (exact_samples - len(samples)))
            else:
                samples = samples[:exact_samples]
            peak = max((abs(s) for s in samples), default=1)
            target_rms = 32767.0 * math.pow(10.0, -18.0 / 20.0)
            gain = min(4.0, max(0.22, target_rms / rms), 24000.0 / float(max(1, peak)))
            out_b = bytearray(exact_samples * 2)
            for i, s in enumerate(samples):
                struct.pack_into("<h", out_b, i * 2, int(max(-32767, min(32767, s * gain))))
            with wave.open(str(output_foley_wav), "wb") as wf_o:
                wf_o.setnchannels(1)
                wf_o.setsampwidth(2)
                wf_o.setframerate(SAMPLE_RATE)
                wf_o.writeframes(out_b)
            return output_foley_wav
        output_foley_wav.unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("Native video Foley extraction skipped (%s)", exc)
        output_foley_wav.unlink(missing_ok=True)
    return None


def _one_pole_bandpass(noise: List[float], low_hz: float, high_hz: float, sr: int = SAMPLE_RATE) -> List[float]:
    """Simple, zero-dependency, warm analog-style bandpass filter for physical air/whoosh/thunder SFX."""
    # High-pass stage
    rc_hp = 1.0 / (2.0 * math.pi * max(20.0, low_hz))
    dt = 1.0 / float(sr)
    alpha_hp = rc_hp / (rc_hp + dt)
    hp_out = [0.0] * len(noise)
    prev_x = 0.0
    prev_y = 0.0
    for i, x in enumerate(noise):
        y = alpha_hp * (prev_y + x - prev_x)
        hp_out[i] = y
        prev_x = x
        prev_y = y

    # Low-pass stage
    rc_lp = 1.0 / (2.0 * math.pi * max(low_hz + 40.0, high_hz))
    alpha_lp = dt / (rc_lp + dt)
    out = [0.0] * len(noise)
    prev = 0.0
    for i, x in enumerate(hp_out):
        prev = prev + alpha_lp * (x - prev)
        out[i] = prev
    return out


def _add_arrow_release_whoosh(buf: List[float], start_sec: float, *, flaming: bool = False, rng: random.Random) -> None:
    """Physically modeled bowstring snap + air-cutting arrow whistle (optional flame trail)."""
    sr = SAMPLE_RATE
    s0 = int(start_sec * sr)
    # 1. Taut bowstring release twang (0.28s decaying low plucked harmonic)
    twang_len = int(0.28 * sr)
    for k in range(twang_len):
        idx = s0 + k
        if idx >= len(buf):
            break
        t = k / float(sr)
        env = math.exp(-t * 14.0) * min(1.0, t / 0.004)
        # Pitch drops slightly right after release like a real bowstring
        f0 = 115.0 + 45.0 * math.exp(-t * 28.0)
        sig = 0.65 * math.sin(2.0 * math.pi * f0 * t) + 0.35 * math.sin(2.0 * math.pi * f0 * 2.02 * t)
        buf[idx] += 0.55 * env * sig

    # 2. High-velocity arrow air-whistle whoosh (0.55s filtered turbulence with Doppler pitch sweep)
    whoosh_start = s0 + int(0.05 * sr)
    whoosh_len = int(0.60 * sr)
    raw_n = [rng.uniform(-1.0, 1.0) for _ in range(whoosh_len)]
    air = _one_pole_bandpass(raw_n, 420.0, 2600.0, sr)
    for k in range(whoosh_len):
        idx = whoosh_start + k
        if idx >= len(buf):
            break
        p = k / float(max(1, whoosh_len))
        # Fast sharp attack peaking at 25%, graceful aerodynamic tail
        env = (p / 0.22) if p < 0.22 else math.exp(-(p - 0.22) * 5.2)
        whistle = 0.14 * math.sin(2.0 * math.pi * (920.0 - 460.0 * p) * (k / float(sr)))
        buf[idx] += env * (1.35 * air[k] + whistle)

    # 3. Optional flaming arrow trail (warm crackle & roar)
    if flaming:
        fire_len = int(1.10 * sr)
        raw_f = [rng.uniform(-1.0, 1.0) for _ in range(fire_len)]
        roar = _one_pole_bandpass(raw_f, 160.0, 850.0, sr)
        for k in range(fire_len):
            idx = whoosh_start + k
            if idx >= len(buf):
                break
            p = k / float(max(1, fire_len))
            env = math.sin(math.pi * min(1.0, p)) * math.exp(-p * 1.4)
            pop = (rng.uniform(-0.7, 0.7) if rng.random() < 0.008 else 0.0)
            buf[idx] += env * (0.70 * roar[k] + 0.35 * pop)


def _add_revolving_chakra_vortex(buf: List[float], duration_sec: float, *, rng: random.Random) -> None:
    """Revolving metallic cosmic disc / Sudarshan Chakra resonant Doppler hum + wind vortex."""
    sr = SAMPLE_RATE
    n = len(buf)
    raw_n = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    wind = _one_pole_bandpass(raw_n, 280.0, 1650.0, sr)
    for i in range(n):
        t = i / float(sr)
        p = t / max(0.5, duration_sec)
        # Smooth swell in, sustained majestic spin, gentle fade out
        macro_env = min(1.0, t / 0.6) * min(1.0, max(0.0, (duration_sec - t) / 0.7))
        # Rotational Doppler LFO accelerating subtly (4.5 Hz -> 7.5 Hz spin rate)
        spin_hz = 4.5 + 2.8 * math.sin(math.pi * p)
        doppler = 0.62 + 0.38 * math.sin(2.0 * math.pi * spin_hz * t)
        # Warm metallic bronze/gold resonant harmonics (in-harmonic cosmic sheen)
        f_base = 148.0 + 18.0 * math.sin(2.0 * math.pi * 0.35 * t)
        hum = (
            0.46 * math.sin(2.0 * math.pi * f_base * t)
            + 0.28 * math.sin(2.0 * math.pi * (f_base * 1.502) * t)
            + 0.16 * math.sin(2.0 * math.pi * (f_base * 2.74) * t)
            + 0.10 * math.sin(2.0 * math.pi * (f_base * 4.08) * t)
        )
        vortex = 0.85 * wind[i] * (0.55 + 0.45 * doppler)
        buf[i] += 0.48 * macro_env * (hum * doppler + vortex)


def _add_thunder_or_war_impact(buf: List[float], start_sec: float, *, rng: random.Random) -> None:
    """Deep rolling cinematic thunder / epic battle-drum sub-bass rumble."""
    sr = SAMPLE_RATE
    s0 = int(start_sec * sr)
    length = min(len(buf) - s0, int(3.2 * sr))
    if length <= 0:
        return
    raw_n = [rng.uniform(-1.0, 1.0) for _ in range(length)]
    rumble = _one_pole_bandpass(raw_n, 38.0, 195.0, sr)
    for k in range(length):
        idx = s0 + k
        t = k / float(sr)
        env = min(1.0, t / 0.04) * math.exp(-t * 1.15)
        sub = 0.45 * math.sin(2.0 * math.pi * (56.0 - 18.0 * min(1.0, t)) * t) * math.exp(-t * 3.8)
        buf[idx] += env * (1.85 * rumble[k] + sub)


def _add_sacred_temple_resonance(buf: List[float], duration_sec: float, *, rng: random.Random) -> None:
    """Warm deep resonant temple bronze bell + soft distant conch/shankh breath (zero cartoon ting)."""
    sr = SAMPLE_RATE
    n = len(buf)
    # Deep warm bronze bell struck softly at 0.35s (low fundamental 196Hz + warm fifth)
    s0 = int(0.35 * sr)
    bell_len = min(n - s0, int(4.5 * sr))
    for k in range(max(0, bell_len)):
        idx = s0 + k
        t = k / float(sr)
        env = min(1.0, t / 0.015) * math.exp(-t * 0.95)
        bell = (
            0.55 * math.sin(2.0 * math.pi * 196.0 * t)
            + 0.25 * math.sin(2.0 * math.pi * 293.66 * t) * math.exp(-t * 0.5)
            + 0.12 * math.sin(2.0 * math.pi * 392.0 * t) * math.exp(-t * 1.2)
        )
        buf[idx] += 0.32 * env * bell

    # Soft airy sacred breath / distant shankh swell in the middle
    raw_n = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    air = _one_pole_bandpass(raw_n, 260.0, 700.0, sr)
    for i in range(n):
        t = i / float(sr)
        env = math.sin(math.pi * min(1.0, t / max(0.5, duration_sec))) ** 2
        drone = 0.30 * math.sin(2.0 * math.pi * 261.63 * t) + 0.15 * math.sin(2.0 * math.pi * 523.25 * t)
        buf[i] += 0.22 * env * (drone + 0.45 * air[i])


def _add_fire_crackle_bed(buf: List[float], duration_sec: float, *, rng: random.Random) -> None:
    """Warm organic flames & crackling embers."""
    sr = SAMPLE_RATE
    n = len(buf)
    raw_n = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    roar = _one_pole_bandpass(raw_n, 85.0, 460.0, sr)
    for i in range(n):
        t = i / float(sr)
        env = min(1.0, t / 0.3) * min(1.0, max(0.0, (duration_sec - t) / 0.35))
        crackle = (rng.uniform(-0.85, 0.85) if rng.random() < 0.004 else 0.0)
        buf[i] += 0.45 * env * (roar[i] + 0.50 * crackle)


def _add_rain_wind_ambience(buf: List[float], duration_sec: float, *, rng: random.Random) -> None:
    """Smooth natural rainfall & atmospheric wind texture."""
    sr = SAMPLE_RATE
    n = len(buf)
    raw_n = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    rain = _one_pole_bandpass(raw_n, 380.0, 3400.0, sr)
    for i in range(n):
        t = i / float(sr)
        env = min(1.0, t / 0.4) * min(1.0, max(0.0, (duration_sec - t) / 0.4))
        gust = 0.72 + 0.28 * math.sin(2.0 * math.pi * 0.22 * t)
        buf[i] += 0.32 * env * gust * rain[i]


def _add_tech_drive_pulse(buf: List[float], duration_sec: float, *, rng: random.Random) -> None:
    """Sleek modern low-end electric drive / sci-fi ambient turbine hum."""
    sr = SAMPLE_RATE
    n = len(buf)
    raw_n = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    air = _one_pole_bandpass(raw_n, 120.0, 900.0, sr)
    for i in range(n):
        t = i / float(sr)
        env = min(1.0, t / 0.4) * min(1.0, max(0.0, (duration_sec - t) / 0.4))
        sweep = 72.0 + 18.0 * math.sin(2.0 * math.pi * 0.3 * t)
        hum = 0.50 * math.sin(2.0 * math.pi * sweep * t) + 0.22 * math.sin(2.0 * math.pi * (sweep * 2.0) * t)
        buf[i] += 0.34 * env * (hum + 0.55 * air[i])


def synthesize_scene_foley_fallback(
    output_foley_wav: Path,
    *,
    sfx_cue: str,
    visual_prompt: str,
    duration_sec: float,
    scene_index: int = 1,
) -> Optional[Path]:
    """
    Synthesizes realistic, scene-matched procedural Foley SFX ONLY when native Omni/Veo Foley
    is unavailable. Matches physical cues (arrow release, revolving chakra, thunder, fire,
    rain, temple resonance, sci-fi/engine pulse). Returns `None` for calm scenes so no artificial
    or cartoon noises ever clutter the soundtrack.
    """
    text = f"{sfx_cue or ''} {visual_prompt or ''}".lower()
    dur = max(2.0, float(duration_sec))
    n_samples = int(round(dur * SAMPLE_RATE))
    buf = [0.0] * n_samples
    rng = random.Random(1009 + scene_index * 97)
    triggered = False

    if any(k in text for k in ("arrow", "bowstring", "bow ", "baana", "teer", "barbarik", "archery", "spear", "sword", "blade")):
        flaming = any(k in text for k in ("flam", "fire", "glow", "burn", "spark", "agni"))
        _add_arrow_release_whoosh(buf, min(1.1, dur * 0.18), flaming=flaming, rng=rng)
        if dur >= 6.5 and any(k in text for k in ("three", "3 ", "arrows", "volley", "barrage", "pierc")):
            _add_arrow_release_whoosh(buf, min(3.4, dur * 0.48), flaming=flaming, rng=rng)
            _add_arrow_release_whoosh(buf, min(5.4, dur * 0.72), flaming=flaming, rng=rng)
        triggered = True

    if any(k in text for k in ("chakra", "sudarshan", "revolving", "spinning disc", "vortex", "cosmic spin", "whirling", "portal", "halo")):
        _add_revolving_chakra_vortex(buf, dur, rng=rng)
        triggered = True

    if any(k in text for k in ("thunder", "lightning", "storm", "war drum", "battle", "explosion", "impact", "crash", "earthquake", "blast")):
        _add_thunder_or_war_impact(buf, min(0.8, dur * 0.12), rng=rng)
        triggered = True

    if any(k in text for k in ("shankh", "conch", "temple", "mandir", "aarti", "divine", "krishna", "shyam", "sacred", "bell")):
        _add_sacred_temple_resonance(buf, dur, rng=rng)
        triggered = True

    if any(k in text for k in ("fire", "flame", "torch", "embers", "sparks", "lava", "burning")):
        _add_fire_crackle_bed(buf, dur, rng=rng)
        triggered = True

    if any(k in text for k in ("rain", "wet asphalt", "monsoon", "ocean", "river", "waterfall", "wind", "mist")):
        _add_rain_wind_ambience(buf, dur, rng=rng)
        triggered = True

    if not triggered and any(k in text for k in ("lidar", "autonomous", "highway", "engine", "rocket", "spacecraft", "server", "quantum", "laser")):
        _add_tech_drive_pulse(buf, dur, rng=rng)
        triggered = True

    if not triggered:
        return None

    # Normalize gently to peak ~0.58 (-4.7 dBFS) with smooth 60ms fade-in/out (zero clicks!)
    peak = max((abs(x) for x in buf), default=0.0)
    if peak < 1e-4:
        return None
    scale = (0.58 * 32767.0) / peak
    fade_n = min(n_samples // 4, int(0.06 * SAMPLE_RATE))

    out_bytes = bytearray(n_samples * 2)
    for i, s in enumerate(buf):
        env = 1.0
        if i < fade_n:
            env = i / float(max(1, fade_n))
        elif i > n_samples - fade_n:
            env = (n_samples - i) / float(max(1, fade_n))
        val = int(max(-32767, min(32767, s * scale * env)))
        struct.pack_into("<h", out_bytes, i * 2, val)

    output_foley_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_foley_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(out_bytes)
    return output_foley_wav
