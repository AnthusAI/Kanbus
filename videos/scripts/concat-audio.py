#!/usr/bin/env python3
"""Place TTS segments onto a silent timeline using Python wave module."""

import json
import struct
import wave

with open("src/videos/intro/intro.timeline.json") as f:
    data = json.load(f)

SAMPLE_RATE = 24000
TOTAL_DUR = 178.9
total_samples = int(TOTAL_DUR * SAMPLE_RATE)

# Collect TTS segments with timing
segments = []
for item in data["items"]:
    if item.get("type") == "tts":
        for seg in item.get("segments", []):
            if seg["type"] == "tts":
                segments.append({
                    "start": seg["startSec"],
                    "path": seg["segmentPath"],
                })
segments.sort(key=lambda s: s["start"])
print(f"Placing {len(segments)} segments onto {TOTAL_DUR}s silent track")

# Create silent buffer (16-bit PCM mono)
audio = bytearray(total_samples * 2)  # 2 bytes per sample

for seg in segments:
    offset_samples = int(seg["start"] * SAMPLE_RATE)
    with wave.open(seg["path"], "rb") as wf:
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()

    # Convert to mono 16-bit if needed
    if n_channels == 2 and sampwidth == 2:
        # Average stereo to mono
        samples = struct.unpack(f"<{n_frames * 2}h", raw)
        mono = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)]
        raw = struct.pack(f"<{len(mono)}h", *mono)
    elif n_channels == 1 and sampwidth == 2:
        pass  # already mono 16-bit
    else:
        print(f"  Warning: unexpected format ch={n_channels} sw={sampwidth} for {seg['path']}")
        continue

    # Resample if needed (simple skip/repeat)
    if rate != SAMPLE_RATE:
        samples = struct.unpack(f"<{len(raw) // 2}h", raw)
        ratio = rate / SAMPLE_RATE
        resampled = [samples[min(int(i * ratio), len(samples) - 1)] for i in range(int(len(samples) / ratio))]
        raw = struct.pack(f"<{len(resampled)}h", *resampled)

    # Write into buffer at the right offset
    byte_offset = offset_samples * 2
    end = min(byte_offset + len(raw), len(audio))
    audio[byte_offset:end] = raw[:end - byte_offset]
    dur = len(raw) / 2 / SAMPLE_RATE
    print(f"  {seg['start']:6.2f}s  {dur:.2f}s  {seg['path'].split('/')[-1]}")

# Write output
out_path = "out/intro-voice.wav"
with wave.open(out_path, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(SAMPLE_RATE)
    wf.writeframes(bytes(audio))

import os
size_mb = os.path.getsize(out_path) / (1024 * 1024)
print(f"\nWrote {out_path} ({size_mb:.1f} MB, {TOTAL_DUR}s)")
