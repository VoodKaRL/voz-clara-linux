import unittest
import numpy as np
from dsp import Processor, Headphones, MicrophoneOutput


class DSPTests(unittest.TestCase):
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
