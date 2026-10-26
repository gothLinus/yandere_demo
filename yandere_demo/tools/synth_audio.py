#!/usr/bin/env python3
"""Synthesizes every sound effect and the school BGM loop as 44.1 kHz 16-bit mono WAV files.

Usage: python3 yandere_demo/tools/synth_audio.py yandere_demo/assets/audio
"""
import math
import random
import struct
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 44100
TWO_PI = 2.0 * math.pi

NOTE_FREQUENCIES = {
    "Bb2": 116.54, "Eb3": 155.56, "F3": 174.61, "G3": 196.00, "Ab3": 207.65, "Bb3": 233.08, "C4": 261.63,
    "D4": 293.66, "Eb4": 311.13, "F4": 349.23, "G4": 392.00, "Ab4": 415.30, "Bb4": 466.16, "C5": 523.25,
    "D5": 587.33, "Eb5": 622.25, "F5": 698.46, "G5": 783.99, "Ab5": 830.61, "Bb5": 932.33, "C6": 1046.50,
    "E6": 1318.51, "B6": 1975.53,
}


def silence(seconds):
    return [0.0] * int(seconds * SAMPLE_RATE)


def add_into(buffer, samples, start_seconds, gain=1.0, wrap=False):
    start = int(start_seconds * SAMPLE_RATE)
    for offset, value in enumerate(samples):
        index = start + offset
        if wrap:
            index %= len(buffer)
        elif index >= len(buffer):
            break
        buffer[index] += value * gain


def tone(frequency, seconds, partials, decay_seconds, attack_seconds=0.004):
    """Sum of sine partials [(ratio, amplitude, decay_scale)] under an exponential decay."""
    count = int(seconds * SAMPLE_RATE)
    samples = []
    for index in range(count):
        time = index / SAMPLE_RATE
        envelope = min(1.0, time / attack_seconds) if attack_seconds > 0.0 else 1.0
        value = 0.0
        for ratio, amplitude, decay_scale in partials:
            value += amplitude * math.exp(-time / (decay_seconds * decay_scale)) * math.sin(TWO_PI * frequency * ratio * time)
        samples.append(value * envelope)
    return samples


def low_pass(samples, coefficient):
    filtered = []
    previous = 0.0
    for value in samples:
        previous += coefficient * (value - previous)
        filtered.append(previous)
    return filtered


def noise(generator, seconds):
    return [generator.uniform(-1.0, 1.0) for _ in range(int(seconds * SAMPLE_RATE))]


def decayed(samples, decay_seconds):
    return [value * math.exp(-(index / SAMPLE_RATE) / decay_seconds) for index, value in enumerate(samples)]


def thump(start_frequency, end_frequency, seconds, decay_seconds):
    samples = []
    phase = 0.0
    count = int(seconds * SAMPLE_RATE)
    for index in range(count):
        progress = index / count
        phase += TWO_PI * (start_frequency + (end_frequency - start_frequency) * progress) / SAMPLE_RATE
        samples.append(math.sin(phase) * math.exp(-(index / SAMPLE_RATE) / decay_seconds))
    return samples


def normalized(samples, peak=0.85):
    highest = max(max(abs(value) for value in samples), 1e-9)
    return [value * peak / highest for value in samples]


def write_wav(path, samples):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767)) for value in samples)
        output.writeframes(frames)


def footstep(generator, seconds, noise_coefficient, noise_decay, thump_frequency, thump_gain, peak):
    scuff = decayed(low_pass(noise(generator, seconds), noise_coefficient), noise_decay)
    body = thump(thump_frequency, thump_frequency * 0.55, seconds, noise_decay * 1.4)
    mixed = [scuff_value * 1.6 + body_value * thump_gain for scuff_value, body_value in zip(scuff, body)]
    return normalized(mixed, peak)


def footsteps(generator):
    sounds = {}
    for number in range(1, 4):
        sounds["footstep_walk_%02d" % number] = footstep(
            generator, 0.22, generator.uniform(0.16, 0.26), 0.045, generator.uniform(70.0, 95.0), 0.9, 0.7)
        sounds["footstep_run_%02d" % number] = footstep(
            generator, 0.16, generator.uniform(0.3, 0.42), 0.032, generator.uniform(85.0, 110.0), 1.1, 0.9)
    for number in range(1, 3):
        sounds["footstep_sneak_%02d" % number] = footstep(
            generator, 0.28, generator.uniform(0.07, 0.11), 0.07, generator.uniform(55.0, 70.0), 0.45, 0.3)
    return sounds


def heartbeat():
    buffer = silence(0.8)
    add_into(buffer, thump(62.0, 38.0, 0.25, 0.07), 0.0, 1.0)
    add_into(buffer, thump(55.0, 34.0, 0.22, 0.06), 0.3, 0.7)
    return normalized(buffer, 0.9)


def shutter(generator):
    buffer = silence(0.32)
    add_into(buffer, decayed(noise(generator, 0.02), 0.004), 0.0, 1.0)
    add_into(buffer, decayed(low_pass(noise(generator, 0.12), 0.35), 0.03), 0.015, 0.6)
    add_into(buffer, decayed(noise(generator, 0.02), 0.005), 0.09, 0.8)
    add_into(buffer, decayed(low_pass(noise(generator, 0.1), 0.2), 0.04), 0.12, 0.35)
    add_into(buffer, thump(900.0, 300.0, 0.04, 0.01), 0.0, 0.5)
    return normalized(buffer, 0.8)


def bell_chime():
    bell_partials = [(1.0, 1.0, 1.0), (2.0, 0.5, 0.7), (2.4, 0.25, 0.5), (3.0, 0.3, 0.45), (4.2, 0.12, 0.3), (0.5, 0.35, 1.4)]
    quarter_notes = ["Eb4", "G4", "F4", "Bb3"]
    spacing_seconds = 0.95
    buffer = silence(5.2)
    for index, note in enumerate(quarter_notes):
        ring = tone(NOTE_FREQUENCIES[note], 4.2, bell_partials, 1.1, 0.003)
        add_into(buffer, ring, index * spacing_seconds, 1.0)
    fade_samples = int(0.3 * SAMPLE_RATE)
    for index in range(fade_samples):
        buffer[-1 - index] *= index / fade_samples
    return normalized(buffer, 0.8)


def locker_door(generator):
    buffer = silence(0.7)
    creak = []
    phase = 0.0
    count = int(0.4 * SAMPLE_RATE)
    for index in range(count):
        progress = index / count
        frequency = 180.0 + 140.0 * progress + 18.0 * math.sin(TWO_PI * 23.0 * progress)
        phase += TWO_PI * frequency / SAMPLE_RATE
        envelope = math.sin(math.pi * progress) ** 0.6
        creak.append((math.sin(phase) + 0.5 * math.sin(2.0 * phase)) * envelope)
    add_into(buffer, creak, 0.0, 0.35)
    add_into(buffer, low_pass(noise(generator, 0.4), 0.05), 0.0, 0.25)
    add_into(buffer, decayed(low_pass(noise(generator, 0.2), 0.12), 0.05), 0.42, 1.0)
    add_into(buffer, thump(120.0, 55.0, 0.25, 0.07), 0.42, 1.1)
    return normalized(buffer, 0.8)


def pickup_chime():
    partials = [(1.0, 1.0, 1.0), (2.0, 0.3, 0.6), (3.0, 0.1, 0.4)]
    buffer = silence(0.9)
    add_into(buffer, tone(NOTE_FREQUENCIES["E6"], 0.6, partials, 0.18), 0.0, 0.8)
    add_into(buffer, tone(NOTE_FREQUENCIES["B6"], 0.7, partials, 0.22), 0.11, 0.7)
    return normalized(buffer, 0.7)


def suspicion_sting():
    seconds = 1.3
    count = int(seconds * SAMPLE_RATE)
    samples = []
    for index in range(count):
        time = index / SAMPLE_RATE
        envelope = min(1.0, time / 0.05) * math.exp(-time / 0.55)
        tremolo = 0.75 + 0.25 * math.sin(TWO_PI * 9.0 * time)
        rising = 1.0 + 0.04 * time
        value = (math.sin(TWO_PI * 311.13 * rising * time) + math.sin(TWO_PI * 440.0 * rising * time)
                 + 0.4 * math.sin(TWO_PI * 622.25 * time))
        samples.append(value * envelope * tremolo)
    return normalized(samples, 0.75)


def game_over_sting(generator):
    buffer = silence(3.0)
    partials = [(1.0, 1.0, 1.0), (2.0, 0.4, 0.6), (3.0, 0.2, 0.4)]
    add_into(buffer, tone(NOTE_FREQUENCIES["Bb2"], 2.8, partials, 1.0, 0.01), 0.0, 1.0)
    add_into(buffer, tone(NOTE_FREQUENCIES["Eb3"] * 0.9439, 2.6, partials, 0.9, 0.01), 0.25, 0.8)
    add_into(buffer, tone(NOTE_FREQUENCIES["Ab3"] * 0.9439, 2.3, partials, 0.8, 0.01), 0.5, 0.6)
    add_into(buffer, thump(70.0, 30.0, 0.6, 0.25), 0.0, 1.4)
    add_into(buffer, decayed(low_pass(noise(generator, 1.0), 0.03), 0.4), 0.0, 0.3)
    return normalized(buffer, 0.85)


def bgm_school_loop():
    """32 s music-box arpeggio over a pad. Every note's tail wraps into the start so the loop point is inaudible."""
    seconds = 32.0
    buffer = silence(seconds)
    chord_seconds = 4.0
    progression = [
        (["Eb4", "G4", "Bb4", "G4", "Eb5", "Bb4", "G4", "Bb4"], ["Eb3", "G3", "Bb3"]),
        (["C4", "Eb4", "G4", "Eb4", "C5", "G4", "Eb4", "G4"], ["C4", "Eb4", "G4"]),
        (["Ab4", "C5", "Eb5", "C5", "Ab4", "Eb5", "C5", "Eb5"], ["Ab3", "C4", "Eb4"]),
        (["Bb4", "D5", "F5", "D5", "Bb4", "F5", "D5", "F5"], ["Bb3", "D4", "F4"]),
    ] * 2
    music_box_partials = [(1.0, 1.0, 1.0), (2.0, 0.35, 0.5), (4.0, 0.15, 0.25), (5.4, 0.08, 0.12)]
    note_seconds = chord_seconds / 8.0
    for chord_index, (arpeggio, pad_notes) in enumerate(progression):
        chord_start = chord_index * chord_seconds
        for note_index, note in enumerate(arpeggio):
            accent = 1.0 if note_index % 4 == 0 else 0.75
            ring = tone(NOTE_FREQUENCIES[note], 1.8, music_box_partials, 0.35, 0.003)
            add_into(buffer, ring, chord_start + note_index * note_seconds, 0.22 * accent, wrap=True)
        for pad_note in pad_notes:
            for detune in (0.997, 1.003):
                add_into(buffer, pad_swell(NOTE_FREQUENCIES[pad_note] * detune, chord_seconds + 1.5), chord_start - 0.75, 0.05, wrap=True)
    return normalized(buffer, 0.7)


def pad_swell(frequency, seconds):
    count = int(seconds * SAMPLE_RATE)
    samples = []
    for index in range(count):
        time = index / SAMPLE_RATE
        envelope = math.sin(math.pi * time / seconds) ** 2
        samples.append(envelope * (math.sin(TWO_PI * frequency * time) + 0.3 * math.sin(TWO_PI * 2.0 * frequency * time)))
    return samples


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: synth_audio.py <output directory>")
    output_directory = Path(sys.argv[1])
    output_directory.mkdir(parents=True, exist_ok=True)
    generator = random.Random(21)
    sounds = footsteps(generator)
    sounds["heartbeat"] = heartbeat()
    sounds["shutter"] = shutter(generator)
    sounds["bell_chime"] = bell_chime()
    sounds["locker_door"] = locker_door(generator)
    sounds["pickup_chime"] = pickup_chime()
    sounds["suspicion_sting"] = suspicion_sting()
    sounds["game_over_sting"] = game_over_sting(generator)
    sounds["bgm_school_loop"] = bgm_school_loop()
    for name, samples in sounds.items():
        write_wav(output_directory / ("%s.wav" % name), samples)
        print("%s.wav  %.2f s" % (name, len(samples) / SAMPLE_RATE))


if __name__ == "__main__":
    main()
