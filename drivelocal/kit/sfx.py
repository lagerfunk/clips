"""Synthesised sound for Drive Like a Local (no voice, no samples): a quiet suburb bed (birds, distant traffic),
car pass-bys and idles, brake squeaks, indicator clicks, quiz ticks, the reveal chime, whooshes, fine hits and a
light pluck music bed. Mix(T).place(...) then .write(path). 48 kHz stereo, peak -1 dBFS before loudnorm."""
import wave

import numpy as np

SR = 48000


def lowpass(x, k):
    k = max(1, int(k))
    return np.convolve(x, np.ones(k) / k, mode="same")


def env(n, a=0.01, r=0.1):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


class Mix:
    def __init__(self, T, seed=5):
        self.T = T
        self.N = int(SR * T)
        self.L = np.zeros(self.N)
        self.R = np.zeros(self.N)
        self.rng = np.random.default_rng(seed)
        self.t = np.arange(self.N) / SR

    def place(self, sig, at, gain=1.0, pan=0.0):
        i = int(at * SR)
        if i >= self.N or i + len(sig) <= 0:
            return
        if i < 0:
            sig, i = sig[-i:], 0
        j = min(self.N, i + len(sig))
        s = sig[: j - i] * gain
        self.L[i:j] += s * (1 - max(0.0, pan))
        self.R[i:j] += s * (1 + min(0.0, pan))

    def curve(self, points):
        ts = np.array([p[0] for p in points])
        gs = np.array([p[1] for p in points])
        return np.interp(self.t, ts, gs)

    # ---------------------------------------------------------- beds
    def suburb(self, gain=0.25):
        rng = self.rng
        far = lowpass(rng.standard_normal(self.N), 60) - lowpass(rng.standard_normal(self.N), 600)
        self.place(far, 0, gain * 0.5)
        # birds: short chirps with falling or rising pitch, sparse
        t = 0.3
        while t < self.T - 0.5:
            n = int(rng.uniform(0.05, 0.12) * SR)
            tt = np.arange(n) / SR
            f0 = rng.uniform(2800, 4800)
            f = f0 * (1 + rng.choice((-1, 1)) * 0.35 * tt / tt[-1])
            ch = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / tt[-1]) ** 2
            for r_ in range(rng.integers(1, 4)):
                self.place(ch, t + r_ * 0.11, gain * 0.16, rng.uniform(-0.8, 0.8))
            t += rng.uniform(0.6, 1.8)

    def engine(self, t0, t1, speed_fn, pan_fn=lambda t: 0.0, gain=0.3, base=34.0):
        """A small petrol car: pitch follows speed (m/s), level follows speed too; idles at 0."""
        n = int((t1 - t0) * SR)
        tt = t0 + np.arange(n) / SR
        v = np.array([speed_fn(x) for x in tt[:: SR // 100]])
        v = np.interp(np.arange(n), np.arange(len(v)) * (SR // 100), v)
        f = base + v * 7.5
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sign(np.sin(3 * ph))
        s = lowpass(s, 18) + 0.2 * lowpass(self.rng.standard_normal(n), 40) * (v / 9.0)
        lvl = 0.35 + 0.65 * np.clip(v / 9.0, 0, 1)
        s *= lvl * env(n, 0.2, 0.3)
        p = np.array([pan_fn(x) for x in tt[:: SR // 50]])
        p = np.interp(np.arange(n), np.arange(len(p)) * (SR // 50), p)
        i = int(t0 * SR)
        j = min(self.N, i + n)
        self.L[i:j] += (s * gain * (1 - np.clip(p, 0, 1)))[: j - i]
        self.R[i:j] += (s * gain * (1 + np.clip(p, -1, 0)))[: j - i]

    def squeak(self, at, gain=0.03, pan=0.0):
        n = int(0.45 * SR)
        tt = np.arange(n) / SR
        f = self.rng.uniform(1900, 2600) * (1 - 0.06 * tt)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (1 + 0.3 * np.sin(2 * np.pi * 23 * tt)) * env(n, 0.05, 0.25)
        self.place(s, at, gain, pan)

    def indicator(self, t0, t1, period=0.66, gain=0.12):
        """Relay click-clack of the indicator."""
        t = t0
        while t < t1:
            for k, at in enumerate((0.0, period / 2)):
                n = int(0.012 * SR)
                c = self.rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 400)
                c = c - lowpass(c, 3)
                self.place(c, t + at, gain * (1.0 if k == 0 else 0.7))
            t += period

    def horn(self, at, dur=0.6, gain=0.25, pan=0.0):
        n = int(dur * SR)
        tt = np.arange(n) / SR
        s = sum(np.sign(np.sin(2 * np.pi * f * tt)) * a for f, a in ((392, 0.6), (494, 0.5)))
        self.place(lowpass(s, 6) * env(n, 0.02, 0.08), at, gain, pan)

    def tick(self, at, gain=0.35, high=False):
        n = int(0.09 * SR)
        tt = np.arange(n) / SR
        f = 1760 if high else 1320
        s = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 45)
        self.place(s, at, gain)

    def chime(self, at, gain=0.25, notes=(1046.5, 1318.5, 1568.0)):
        for k, f in enumerate(notes):
            n = int(0.9 * SR)
            tt = np.arange(n) / SR
            s = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 4.5)
            self.place(s, at + 0.06 * k, gain)

    def buzz(self, at, gain=0.22):
        n = int(0.42 * SR)
        tt = np.arange(n) / SR
        s = np.sign(np.sin(2 * np.pi * 140 * tt)) + np.sign(np.sin(2 * np.pi * 147 * tt))
        self.place(lowpass(s, 12) * env(n, 0.01, 0.12), at, gain)

    def whoosh(self, at, gain=0.3, pan=0.0, dur=0.45):
        n = int(dur * SR)
        w = self.rng.standard_normal(n)
        e = np.sin(np.linspace(0, np.pi, n)) ** 2
        w = lowpass(w, 6) - lowpass(w, 60)
        self.place(w * e, at - dur / 3, gain, pan)

    def hit(self, at, gain=0.8, chime=True):
        n = int(0.9 * SR)
        tt = np.arange(n) / SR
        h = np.sin(2 * np.pi * (70 - 30 * tt) * tt) * np.exp(-tt * 5) + \
            0.5 * lowpass(self.rng.standard_normal(n), 8) * np.exp(-tt * 25)
        self.place(h, at, gain)
        if chime:
            self.chime(at + 0.12, 0.1, (1568.0, 2093.0))

    def pop(self, at, gain=0.25):
        n = int(0.12 * SR)
        tt = np.arange(n) / SR
        s = np.sin(2 * np.pi * (900 - 2500 * tt) * tt) * np.exp(-tt * 40)
        self.place(s, at, gain)

    # ---------------------------------------------------------- music
    def music(self, gain_points, bpm=112, key=0, seed_bar=0):
        """Soft pluck arpeggio and bass (A minor shifted by `key` semitones)."""
        def pluck(f, dur=0.32):
            n = int(dur * SR)
            tt = np.arange(n) / SR
            return (np.sin(2 * np.pi * f * tt) * np.exp(-tt * 14) + 0.35 * np.sin(4 * np.pi * f * tt) *
                    np.exp(-tt * 22) + 0.15 * np.sin(6 * np.pi * f * tt) * np.exp(-tt * 30))
        k = 2 ** (key / 12)
        chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66), (164.81, 207.65, 246.94)]
        bass = [110.0, 87.31, 98.0, 82.41]
        beat = 60 / bpm
        mus = np.zeros(self.N)
        b, tb = seed_bar, 0.0
        while tb < self.T:
            ch = chords[(b // 8) % 4]
            f = ch[[0, 1, 2, 1][b % 4]] * (2 if (b // 4) % 2 else 1) * k
            i = int(tb * SR)
            p = pluck(f)
            j = min(self.N, i + len(p))
            mus[i:j] += p[: j - i] * 0.22
            if b % 2 == 0:
                n = int(beat * 2 * SR)
                tt = np.arange(n) / SR
                bs = np.sin(2 * np.pi * bass[(b // 8) % 4] * k * tt) * np.exp(-tt * 2.5)
                j = min(self.N, i + n)
                mus[i:j] += bs[: j - i] * 0.3
            if b % 2 == 1:
                n = int(0.05 * SR)
                h = self.rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 90)
                h = h - lowpass(h, 4)
                j = min(self.N, i + n)
                mus[i:j] += h[: j - i] * 0.06
            b += 1
            tb += beat / 2
        self.place(mus * self.curve(gain_points), 0, 0.55)

    def write(self, path):
        out = np.stack([self.L, self.R], axis=1)
        out = out / max(1e-9, np.abs(out).max()) * 0.89
        pcm = (out * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        return path
