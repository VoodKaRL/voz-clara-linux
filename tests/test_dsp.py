import unittest
import numpy as np
from dsp import Processor, Headphones, MicrophoneOutput, PeakLimiter


class DSPTests(unittest.TestCase):
    def test_final_ceiling_survives_dc_overshoot_and_extreme_input(self):
        # A bipolar DC step can overshoot after the DC-blocking filter. The
        # final ceiling must hold there, not just before that filter.
        for ceiling_db in (-12, -3, -1):
            safety = MicrophoneOutput(48000)
            safety.limiter.ceiling = 10**(ceiling_db/20)
            samples = np.repeat(np.repeat([1e6, -1e6, .95, -.95, 0], 2400)[:, None], 2, axis=1)
            output = np.concatenate([safety.process(w) for w in np.array_split(samples, 125)])
            self.assertTrue(np.isfinite(output).all())
            self.assertLessEqual(float(np.max(np.abs(output))), safety.limiter.ceiling+1e-7)

    def test_lookahead_has_fixed_delay_and_preserves_quiet_wave(self):
        limiter = PeakLimiter(48000, ceiling=.89, lookahead_ms=5)
        rng = np.random.default_rng(15)
        samples = rng.normal(0, .01, (3000, 2))
        actual = np.concatenate([limiter.process(w) for w in np.array_split(samples, 30)])
        np.testing.assert_array_equal(actual[:240], 0)
        np.testing.assert_allclose(actual[240:], samples[:-240], atol=1e-8)

    def test_lookahead_limiter_block_boundaries_and_lowering_ceiling(self):
        rng = np.random.default_rng(3)
        samples = rng.normal(0, 4, (4800, 2))
        a = PeakLimiter(48000, ceiling=.89, lookahead_ms=5)
        b = PeakLimiter(48000, ceiling=.89, lookahead_ms=5)
        expected = a.process(samples)
        actual = np.concatenate([b.process(w) for w in np.array_split(samples, 71)])
        np.testing.assert_array_equal(actual, expected)
        b.ceiling = .25
        self.assertLessEqual(float(np.max(np.abs(b.process(samples)))), .250001)

    def test_extreme_and_nonfinite_values_cannot_poison_any_stage(self):
        bad = np.array([[1e300, -1e300], [np.nan, np.inf], [-np.inf, 0.]])
        for stage in (Processor(48000), MicrophoneOutput(48000), Headphones(48000)):
            output = stage.process(bad)
            self.assertTrue(np.isfinite(output).all())
            self.assertLessEqual(float(np.max(np.abs(output))), .950001)
            self.assertTrue(np.isfinite(stage.process(np.zeros((512, 2)))).all())

    def test_empty_blocks_are_safe(self):
        for stage in (Processor(48000), MicrophoneOutput(48000), Headphones(48000), PeakLimiter(48000)):
            self.assertEqual(stage.process(np.empty((0, 2))).shape, (0, 2))

    def test_peak_protection_recovers_without_amplifying_silence(self):
        limiter = PeakLimiter(48000)
        wave = np.column_stack((np.full(512, 4.), np.full(512, .4)))
        out = limiter.process(wave)
        self.assertLessEqual(float(np.max(np.abs(out))), .950001)
        np.testing.assert_allclose(out[:, 0], out[:, 1]*10, atol=1e-7)
        self.assertGreater(limiter.reduction_db, 10)
        np.testing.assert_array_equal(limiter.process(np.zeros((48000, 2))), 0)
        quiet = np.full((512, 2), .01)
        np.testing.assert_allclose(limiter.process(quiet), quiet, atol=1e-6)

    def test_limiter_is_independent_of_block_size(self):
        rng = np.random.default_rng(9)
        wave = rng.normal(0, .9, (5120, 2))
        a, b = PeakLimiter(48000), PeakLimiter(48000)
        expected = a.process(wave)
        actual = np.concatenate([b.process(chunk) for chunk in np.split(wave, 40)])
        np.testing.assert_array_equal(actual, expected)

    def test_overloaded_tone_and_eq_stay_bounded_and_recover(self):
        wave = np.repeat((.9*np.sin(2*np.pi*1000*np.arange(48000)/48000))[:, None], 2, axis=1)
        p = Processor(48000)
        p.gate_db, p.gain_db, p.x, p.y = -80, 12, 1, 1
        hp = Headphones(48000)
        hp.gains, hp.volume_db = (12, 12, 12, 12, 12), 12
        for processor in (p, hp):
            out = processor.process(wave)
            self.assertTrue(np.isfinite(out).all())
            self.assertLessEqual(float(np.max(np.abs(out))), .950001)
            quiet = processor.process(np.zeros((48000, 2)))
            self.assertLess(float(np.max(np.abs(quiet[-1000:]))), 1e-5)

    def test_gate_holds_through_short_quiet_consonants(self):
        p = Processor(48000)
        p.gate_db = -30
        p.process(np.full((2400, 2), .1))
        p.process(np.zeros((4800, 2)))
        self.assertTrue(p.open)
        p.process(np.zeros((48000, 2)))
        self.assertFalse(p.open)

    def test_nonfinite_samples_do_not_poison_filters(self):
        for processor in (Processor(48000), Headphones(48000)):
            bad = np.zeros((128, 2))
            bad[0] = [np.nan, np.inf]
            self.assertTrue(np.isfinite(processor.process(bad)).all())
            self.assertTrue(np.isfinite(processor.process(np.zeros((128, 2)))).all())

    def test_microphone_output_removes_dc_and_fades_startup(self):
        safety = MicrophoneOutput(48000)
        dc = safety.process(np.full((48000, 2), .8, dtype='float32'))
        self.assertEqual(float(dc[0, 0]), 0)
        self.assertLess(float(np.max(np.abs(dc[-1000:]))), 1e-6)
        samples = np.arange(48000)/48000
        voice = np.repeat((.1*np.sin(2*np.pi*1000*samples))[:, None], 2, axis=1)
        out = safety.process(voice)
        self.assertAlmostEqual(float(np.std(out[-24000:])), float(np.std(voice[-24000:])), places=3)

    def test_neutral_and_mute(self):
        p = Processor(48000)
        p.gate_db = -80
        wave = (.1*np.sin(2*np.pi*440*np.arange(48000)/48000)).astype('float32')
        output = p.process(wave)
        np.testing.assert_allclose(output[-10000:], wave[-10000:], atol=1e-6)
        p.muted = True
        self.assertEqual(float(np.max(np.abs(p.process(wave)))), 0)

    def test_gate(self):
        p = Processor(48000)
        noise = np.full(48000, .0001, dtype='float32')
        self.assertEqual(float(np.max(np.abs(p.process(noise)))), 0)
        voice = np.full(48000, .1, dtype='float32')
        self.assertGreater(float(p.process(voice)[-1]), .09)
        for _ in range(3):
            out = p.process(noise)
        self.assertLess(float(np.max(np.abs(out[-1000:]))), 1e-8)

    def test_tone(self):
        def rms(freq, x):
            p = Processor(48000)
            p.gate_db = -80
            p.x = x
            wave = .05*np.sin(2*np.pi*freq*np.arange(48000)/48000)
            return float(np.sqrt(np.mean(p.process(wave)[24000:]**2)))
        self.assertGreater(rms(80, -1), rms(80, 1)*2)
        self.assertGreater(rms(10000, 1), rms(10000, -1)*2)

    def test_stereo_and_mono(self):
        p = Processor(48000)
        p.gate_db = -80
        wave = np.column_stack((np.full(48000, .2), np.zeros(48000)))
        p.mono = False
        out = p.process(wave)
        self.assertAlmostEqual(float(out[-1, 0]), .2, places=5)
        self.assertEqual(float(out[-1, 1]), 0)
        p.mono = True
        out = p.process(wave)
        np.testing.assert_allclose(out[-1], [.1, .1], atol=1e-6)

    def test_compressor_reduces_loud_voice(self):
        p = Processor(48000)
        p.gate_db = -80
        p.comp = 8
        loud = p.process(np.full(48000, .7))
        self.assertLess(float(loud[-1]), .15)
        p.comp = 0
        bypass = p.process(np.full(48000, .7))
        self.assertAlmostEqual(float(bypass[-1]), .7, places=4)

    def test_headphones_independent_and_eq(self):
        wave = .02*np.sin(2*np.pi*1000*np.arange(48000)/48000)
        stereo = np.repeat(wave[:, None], 2, axis=1)
        original = stereo.copy()
        hp = Headphones(48000)
        hp.volume_db = 0
        neutral = hp.process(stereo)
        np.testing.assert_allclose(neutral, stereo, atol=1e-7)
        hp.gains = (0, 0, 12, 0, 0)
        boosted = hp.process(stereo)
        self.assertGreater(float(np.std(boosted[-24000:])), float(np.std(neutral[-24000:]))*3.8)
        np.testing.assert_array_equal(stereo, original)
        hp.muted = True
        self.assertEqual(float(np.max(np.abs(hp.process(stereo)))), 0)

    def test_split_blocks_match_continuous(self):
        rng = np.random.default_rng(123)
        wave = rng.normal(0, .05, (128*40, 2)).astype('float32')
        a, b = Processor(48000), Processor(48000)
        a.comp = b.comp = 5
        expected = a.process(wave)
        actual = np.concatenate([b.process(chunk) for chunk in np.split(wave, 40)])
        np.testing.assert_allclose(actual, expected, atol=1e-7)


if __name__ == '__main__':
    unittest.main()
