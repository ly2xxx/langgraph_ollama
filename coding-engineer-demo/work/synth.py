"""Soundtrack for the brag video: 120 BPM, A minor (Am-F-C-G), effects on the same grid."""
import wave
import numpy as np

SR = 44100
BPM = 120
BEAT = 60 / BPM          # 0.5 s
DUR = 24.5
N = int(SR * DUR)
rng = np.random.default_rng(7)

def midi(n): return 440.0 * 2 ** ((n - 69) / 12)
def env_ad(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)
def add(buf, start_s, sig, gain=1.0):
    i = int(round(start_s * SR))
    if i >= len(buf): return
    j = min(len(buf), i + len(sig))
    buf[i:j] += gain * sig[: j - i]
def shaped_noise(n, lo, hi):
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec *= ((f >= lo) & (f <= hi))
    x = np.fft.irfft(spec, n)
    return x / (np.abs(x).max() + 1e-9)

# Am, F, C, G  (bar = 2 s = 4 beats)
CHORDS = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [48, 52, 55]), (55, [55, 59, 62])]
def chord_at(t): return CHORDS[int(t // (4 * BEAT)) % 4]

drums = np.zeros(N); bass = np.zeros(N); pad = np.zeros(N); arp = np.zeros(N); sfx = np.zeros(N)
END_GROOVE = 22.0   # outro: drums drop, final Am rings

# kick: enters with the FAIL slam at 1.5s
kn = int(0.32 * SR); kt = np.arange(kn) / SR
kick = np.sin(2 * np.pi * np.cumsum(45 + 75 * np.exp(-kt / 0.035)) / SR) * np.exp(-kt / 0.11)
for b in range(int(DUR / BEAT)):
    t = b * BEAT
    if 1.5 <= t < END_GROOVE: add(drums, t, kick, 0.55)
# hats on off-beat 8ths, and a soft clap on 2 & 4 after the reveal
hn = int(0.05 * SR); hat = shaped_noise(hn, 7000, 16000) * env_ad(hn, 0.001, 0.012)
cn = int(0.18 * SR); clap = shaped_noise(cn, 900, 5000) * env_ad(cn, 0.002, 0.045)
for e in range(int(DUR / (BEAT / 2))):
    t = e * BEAT / 2
    if 3.5 <= t < END_GROOVE and e % 2 == 1: add(drums, t, hat, 0.10)
    if 3.5 <= t < END_GROOVE and e % 4 == 2: add(drums, t, clap, 0.16)

# bass: root on 8ths (octave below), from 1.5s
for e in range(int(DUR / (BEAT / 2))):
    t = e * BEAT / 2
    if not (1.5 <= t < END_GROOVE): continue
    root, _ = chord_at(t)
    f = midi(root - 12); n = int(BEAT / 2 * SR * 0.9); tt = np.arange(n) / SR
    tone = np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt)
    add(bass, t, tone * env_ad(n, 0.005, 0.18), 0.30)

# pad: soft detuned triads per bar, whole track; final Am held through the outro
def pad_note(f, n):
    tt = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * d * tt) for d in (0.997, 1.0, 1.003)) / 3
    x += 0.15 * np.sin(2 * np.pi * 2 * f * tt)
    a = np.minimum(1, tt / 0.25); r = np.minimum(1, (n / SR - tt) / 0.4)
    return x * a * np.clip(r, 0, 1)
bar = 4 * BEAT
for k in range(int(END_GROOVE / bar)):
    _, notes = CHORDS[k % 4]
    for m in notes: add(pad, k * bar, pad_note(midi(m), int(bar * SR) + int(0.3 * SR)), 0.06)
for m in [57, 60, 64, 69]: add(pad, END_GROOVE, pad_note(midi(m), int((DUR - END_GROOVE) * SR)), 0.075)

# arp: plucked 8ths up an octave, enters at the reveal
pattern = [0, 1, 2, 1, 2, 0, 1, 2]
for e in range(int(DUR / (BEAT / 2))):
    t = e * BEAT / 2
    if not (3.5 <= t < END_GROOVE): continue
    _, notes = chord_at(t)
    f = midi(notes[pattern[e % 8]] + 12); n = int(0.35 * SR); tt = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * env_ad(n, 0.003, 0.09)
    add(arp, t, tone, 0.07)
# final arp flourish on the outro downbeat
for i, m in enumerate([69, 72, 76, 81]):
    n = int(1.2 * SR); tt = np.arange(n) / SR
    add(arp, END_GROOVE + i * BEAT / 2, np.sin(2 * np.pi * midi(m) * tt) * env_ad(n, 0.003, 0.35), 0.06)

# --- SFX, on the grid, in key ---
CUTS = [3.5, 7.0, 11.0, 15.0, 19.0, 22.0]
wn = int(0.4 * SR)
for c in CUTS:
    w = shaped_noise(wn, 400, 3500) * np.linspace(0, 1, wn) ** 2.2   # swell into the cut
    add(sfx, c - 0.4, w, 0.07)
    tn = int(0.4 * SR); tt = np.arange(tn) / SR                       # soft in-key sub thump (A1)
    add(sfx, c, np.sin(2 * np.pi * midi(45) * tt) * env_ad(tn, 0.003, 0.12), 0.22)
for s in [1.5, 16.5]:                                                  # the "stamp": FAIL / escalated
    tn = int(0.5 * SR); tt = np.arange(tn) / SR
    add(sfx, s, np.sin(2 * np.pi * midi(33) * tt) * env_ad(tn, 0.002, 0.16), 0.40)
    add(sfx, s, shaped_noise(int(0.12 * SR), 150, 1800) * env_ad(int(0.12 * SR), 0.001, 0.03), 0.16)
for s in [8.5, 9.5, 16.0]:                                             # lock snap / refusal / "==" : muted tick in key
    tn = int(0.15 * SR); tt = np.arange(tn) / SR
    add(sfx, s, np.sin(2 * np.pi * midi(81) * tt) * env_ad(tn, 0.001, 0.025), 0.10)
# typing ticks in the hook, kept under the pad
for i in range(14):
    t = 0.1 + i * 0.05
    add(sfx, t, shaped_noise(int(0.015 * SR), 2500, 7000) * env_ad(int(0.015 * SR), 0.0005, 0.004), 0.025)

mix = drums + bass + pad + arp + sfx
# gentle fade-in of 10 ms and fade-out over the last 0.6 s
mix[: int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))
fo = int(0.6 * SR); mix[-fo:] *= np.linspace(1, 0, fo) ** 1.5
mix /= np.abs(mix).max() / 0.7
stereo = np.stack([mix, mix], axis=1)
with wave.open("music_raw.wav", "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((stereo * 32767).astype("<i2").tobytes())
print("wrote music_raw.wav", DUR, "s")
