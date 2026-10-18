import math
import numpy as np
from scipy.signal import lfilter


class Processor:
    def __init__(self, rate):
        self.rate = rate
        self.gate_db = -45
        self.gain_db = 0
        self.x = self.y = 0.0
        self.muted = False
        self.mono = True
        self.comp = 0
        self.comp_gain = 1.0
        self.env = 0.0
        self.gate_gain = 0.0
        self.open = False
        self.low_state = None
        self.high_state = None
        self.input_db = self.output_db = -90.0

    def process(self, samples):
        a = np.asarray(samples, dtype=np.float32)
        flat = a.ndim == 1
        if flat:
            a = a[:, None]
        if self.mono and a.shape[1] > 1:
            a = np.repeat(np.mean(a, axis=1, keepdims=True), a.shape[1], axis=1)
        if self.low_state is None or self.low_state.shape[1] != a.shape[1]:
            self.low_state = np.zeros((1, a.shape[1]))
            self.high_state = np.zeros((1, a.shape[1]))
        self.input_db = 20 * math.log10(max(float(np.sqrt(np.mean(a*a))), 1e-9))
        # Two complementary one-pole bands: neutral at the centre of the pad.
        pole = math.exp(-2 * math.pi * 250 / self.rate)
        low, self.low_state = lfilter([1-pole], [1, -pole], a, axis=0, zi=self.low_state)
        pole = math.exp(-2 * math.pi * 3500 / self.rate)
        smooth, self.high_state = lfilter([1-pole], [1, -pole], a, axis=0, zi=self.high_state)
        bass = 10 ** ((-self.x * 12 + self.y * 6) / 20)
        treble = 10 ** ((self.x * 12 + self.y * 6) / 20)
        out = a + (bass-1)*low + (treble-1)*(a-smooth)
        attack = math.exp(-1 / (.003*self.rate))
        release = math.exp(-1 / (.12*self.rate))
        threshold = 10 ** (self.gate_db/20)
        detector = np.max(np.abs(a), axis=1)
        comp_threshold = -12 - self.comp * 1.8
        ratio = 1 + self.comp * .5
        comp_attack = math.exp(-1 / (.005*self.rate))
        comp_release = math.exp(-1 / (.08*self.rate))
        envelope = np.empty(len(a))
        for i in range(len(a)):
            value = float(detector[i])
            c = attack if value > self.env else release
            self.env = c*self.env + (1-c)*value
            if self.gate_db <= -80:
                self.open = True
            elif self.env > threshold:
                self.open = True
            elif self.env < threshold * .65:
                self.open = False
            c = attack if self.open else release
            self.gate_gain = c*self.gate_gain + (1-c)*float(self.open)
            level = 20 * math.log10(max(self.env, 1e-9))
            reduction = max(0, level-comp_threshold) * (1-1/ratio)
            target = 10 ** (-reduction/20) if self.comp else 1.0
            c = comp_attack if target < self.comp_gain else comp_release
            self.comp_gain = c*self.comp_gain + (1-c)*target
            envelope[i] = self.gate_gain*self.comp_gain
        out *= envelope[:, None]
        out *= 0 if self.muted else 10 ** (self.gain_db/20)
        out = np.clip(out, -1, 1).astype('<f4')
        self.output_db = 20 * math.log10(max(float(np.sqrt(np.mean(out*out))), 1e-9))
        return out[:, 0] if flat else out


class Headphones:
    frequencies = (80, 250, 1000, 4000, 12000)

    def __init__(self, rate):
        self.rate = rate
        self.gains = (0, 0, 0, 0, 0)
        self.volume_db = -6
        self.muted = False
        self.states = [np.zeros((2, 2)) for _ in self.frequencies]
        self.cached = None
        self.coefficients = []
        self.output_db = -90.0

    def process(self, samples):
        gains = tuple(self.gains)
        if gains != self.cached:
            self.coefficients = []
            for freq, gain in zip(self.frequencies, gains):
                w = 2*math.pi*min(freq, self.rate*.45)/self.rate
                alpha = math.sin(w)/(2*.8)
                amplitude = 10**(gain/40)
                b = np.array([1+alpha*amplitude, -2*math.cos(w), 1-alpha*amplitude])
                a = np.array([1+alpha/amplitude, -2*math.cos(w), 1-alpha/amplitude])
                self.coefficients.append((b/a[0], a/a[0]))
            self.cached = gains
        out = np.asarray(samples, dtype=np.float64)
        if out.ndim == 1:
            out = np.repeat(out[:, None], 2, axis=1)
        for i, (b, a) in enumerate(self.coefficients):
            out, self.states[i] = lfilter(b, a, out, axis=0, zi=self.states[i])
        out = np.clip(out*(0 if self.muted else 10**(self.volume_db/20)), -1, 1).astype('<f4')
        self.output_db = 20*math.log10(max(float(np.sqrt(np.mean(out*out))), 1e-9))
        return out
