"""Streaming RNNoise adapter. Its state and controls are separate from the gate."""
import ctypes
from importlib.util import find_spec
from pathlib import Path
import sys

import numpy as np


class RNNoiseBackend:
    frame_size = 480
    delay_frames = 960  # Bundled RNNoise model in pyrnnoise 0.4.5; verified in tests.

    def __init__(self):
        package = find_spec('pyrnnoise')
        if package is None or not package.origin:
            raise RuntimeError('Falta RNNoise. Cierra Voz Clara y repite el instalador actualizado.')
        filename = 'rnnoise.dll' if sys.platform == 'win32' else 'librnnoise.so'
        self.lib = ctypes.CDLL(str(Path(package.origin).parent / filename))
        self.lib.rnnoise_create.argtypes = [ctypes.c_void_p]
        self.lib.rnnoise_create.restype = ctypes.c_void_p
        self.lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        self.lib.rnnoise_destroy.restype = None
        pointer = ctypes.POINTER(ctypes.c_float)
        self.lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, pointer, pointer]
        self.lib.rnnoise_process_frame.restype = ctypes.c_float
        self.lib.rnnoise_get_frame_size.argtypes = []
        self.lib.rnnoise_get_frame_size.restype = ctypes.c_int
        self.states = []
        if self.lib.rnnoise_get_frame_size() != self.frame_size:
            raise RuntimeError('La versión de RNNoise no usa bloques compatibles de 480 muestras.')
        for _ in range(2):
            state = self.lib.rnnoise_create(None)
            if not state:
                self.close()
                raise RuntimeError('No se pudo reservar memoria para la supresión de ruido.')
            self.states.append(state)

    def process(self, frame):
        out = np.empty((self.frame_size, 2), dtype=np.float32)
        for channel, state in enumerate(self.states):
            # The C API uses float buffers in 16-bit PCM amplitude units.
            samples = np.ascontiguousarray(np.clip(frame[:, channel], -1, 1)*32768, dtype=np.float32)
            pointer = samples.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self.lib.rnnoise_process_frame(state, pointer, pointer)
            out[:, channel] = samples/32768
        return out

    def close(self):
        for state in getattr(self, 'states', []):
            self.lib.rnnoise_destroy(state)
        self.states = []

    def __del__(self):
        self.close()


class NoiseSuppressor:
    """Fixed-size output for arbitrary audio blocks; no growing backlog.

    RNNoise consumes 480 frames at 48 kHz with two frames of model delay.
    A 480-frame FIFO supplies fixed-size output; dry/wet are aligned at 30 ms.
    OFF returns the undelayed input once the 20 ms switching fade completes.
    """
    def __init__(self, rate, backend=None):
        self.rate = rate
        self.backend = backend
        self.enabled = False
        self.strength = 70
        self.enabled_mix = 0.0
        self.strength_mix = .7
        self.pending = np.empty((0, 2), dtype=np.float32)
        self.output = np.zeros((480, 2), dtype=np.float32)
        self.previous_dry = np.zeros((960, 2), dtype=np.float32)
        self.dry_output = np.zeros((480, 2), dtype=np.float32)
        self.warm_remaining = 1440

    def set_enabled(self, enabled):
        if enabled:
            if self.rate != 48000:
                raise RuntimeError('La supresión de ruido requiere 48000 Hz. Detén el audio y selecciona esa frecuencia.')
            if self.backend is None:
                try:
                    self.backend = RNNoiseBackend()
                except (OSError, ImportError) as exc:
                    raise RuntimeError('No se pudo cargar RNNoise. Repite el instalador actualizado. '+str(exc)) from exc
        self.enabled = bool(enabled)

    def ramp(self, current, target, count):
        step = 1/max(1, int(self.rate*.02))
        values = current + np.sign(target-current)*step*np.arange(1, count+1)
        return np.clip(values, min(current, target), max(current, target))

    def process(self, samples):
        samples = np.asarray(samples, dtype=np.float32)
        if self.backend is None:
            return samples.copy()
        self.pending = np.concatenate((self.pending, samples))
        while len(self.pending) >= 480:
            frame = self.pending[:480]
            self.pending = self.pending[480:].copy()
            wet = self.backend.process(frame)
            self.output = np.concatenate((self.output, wet))
            self.dry_output = np.concatenate((self.dry_output, self.previous_dry[:480]))
            self.previous_dry = np.concatenate((self.previous_dry[480:], frame))
        count = len(samples)
        if len(self.output) < count:
            raise RuntimeError('El filtro de ruido no entregó un bloque completo.')
        wet, dry = self.output[:count], self.dry_output[:count]
        self.output = self.output[count:].copy()
        self.dry_output = self.dry_output[count:].copy()
        ready = self.warm_remaining == 0
        self.warm_remaining = max(0, self.warm_remaining-count)
        enabled = self.ramp(self.enabled_mix, float(self.enabled and ready), count)
        strength = self.ramp(self.strength_mix, max(0, min(100, self.strength))/100, count)
        self.enabled_mix, self.strength_mix = float(enabled[-1]), float(strength[-1])
        filtered = dry*(1-strength[:, None]) + wet*strength[:, None]
        return (samples*(1-enabled[:, None]) + filtered*enabled[:, None]).astype(np.float32)

    def close(self):
        if self.backend is not None:
            self.backend.close()
            self.backend = None
