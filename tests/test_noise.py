import unittest
import numpy as np
from noise import NoiseSuppressor, RNNoiseBackend


class DelayedDenoiser:
    """Deterministic two-frame-delay model to test dry/wet time alignment."""
    def __init__(self):
        self.previous = np.zeros((960, 2), dtype=np.float32)

    def process(self, samples):
        out = self.previous[:480]*.25
        self.previous = np.concatenate((self.previous[480:], samples))
        return out

    def close(self):
        pass


class NoiseTests(unittest.TestCase):
    def test_disabled_preserves_samples_exactly(self):
        samples = np.random.default_rng(4).normal(0, .03, (128, 2)).astype('float32')
        for rate in (44100, 48000, 96000):
            effect = NoiseSuppressor(rate)
            np.testing.assert_array_equal(effect.process(samples), samples)
        with self.assertRaisesRegex(RuntimeError, '48000'):
            NoiseSuppressor(44100).set_enabled(True)

    def test_strength_has_aligned_dry_and_wet_signals(self):
        samples = np.random.default_rng(5).normal(0, .03, (128*200, 2)).astype('float32')
        for strength, ratio in ((0, 1), (50, .625), (100, .25)):
            effect = NoiseSuppressor(48000, DelayedDenoiser())
            effect.set_enabled(True)
            effect.strength = strength
            output = np.concatenate([effect.process(x) for x in np.split(samples, 200)])
            np.testing.assert_allclose(output[4800:], samples[4800-1440:-1440]*ratio, atol=1e-7)

    def test_blocks_do_not_drop_samples_or_accumulate_delay(self):
        effect = NoiseSuppressor(48000, DelayedDenoiser())
        effect.set_enabled(True)
        for size in (128, 256, 512, 1024, 128, 2048)*20:
            block = np.full((size, 2), .01, dtype='float32')
            out = effect.process(block)
            self.assertEqual(out.shape, block.shape)
            self.assertTrue(np.isfinite(out).all())
            self.assertLess(len(effect.pending), 480)
            self.assertLessEqual(len(effect.output), 480)

    def test_switching_off_returns_to_undelayed_audio(self):
        effect = NoiseSuppressor(48000, DelayedDenoiser())
        effect.set_enabled(True)
        for _ in range(20):
            effect.process(np.full((480, 2), .1, dtype='float32'))
        self.assertEqual(effect.enabled_mix, 1)
        effect.set_enabled(False)
        samples = np.random.default_rng(6).normal(0, .03, (4800, 2)).astype('float32')
        out = effect.process(samples)
        np.testing.assert_array_equal(out[1000:], samples[1000:])

    def test_native_rnnoise_reduces_stationary_noise(self):
        backend = RNNoiseBackend()
        effect = NoiseSuppressor(48000, backend)
        self.addCleanup(effect.close)
        effect.set_enabled(True)
        effect.strength = 100
        samples = np.random.default_rng(7).normal(0, .025, (48000*2, 2)).astype('float32')
        output = np.concatenate([effect.process(block) for block in np.split(samples, 200)])
        self.assertTrue(np.isfinite(output).all())
        self.assertLess(float(np.std(output[-24000:])), float(np.std(samples[-24000:]))*.8)

    def test_native_model_delay_matches_dry_alignment(self):
        from scipy.signal import correlate, correlation_lags
        backend = RNNoiseBackend()
        self.addCleanup(backend.close)
        samples = np.random.default_rng(3).normal(0, .03, (48000, 2)).astype('float32')
        out = np.concatenate([backend.process(block) for block in np.split(samples, 100)])
        correlation = correlate(out[:, 0], samples[:, 0], mode='full', method='fft')
        lags = correlation_lags(len(out), len(samples))
        valid = (lags >= 0) & (lags < 4800)
        measured = int(lags[valid][np.argmax(correlation[valid])])
        self.assertEqual(measured, backend.delay_frames)


if __name__ == '__main__':
    unittest.main()
