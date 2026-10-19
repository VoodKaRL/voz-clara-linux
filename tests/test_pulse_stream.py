import unittest
from unittest.mock import patch

from pulse_stream import playback_chunks, buffer_attributes


class PipeTests(unittest.TestCase):
    def test_bridge_fragments_preserve_complete_frames(self):
        data = bytes(range(80))
        fragments = [data[:3], data[3:9], data[9:22], data[22:23], data[23:], b'']
        with patch('pulse_stream.os.read', side_effect=fragments):
            chunks = list(playback_chunks(0, 128))
        self.assertEqual(b''.join(chunks), data)
        self.assertTrue(all(len(chunk) % 8 == 0 for chunk in chunks))

    def test_truncated_frame_is_reported(self):
        with patch('pulse_stream.os.read', side_effect=[b'123', b'']):
            with self.assertRaisesRegex(RuntimeError, 'incompleta'):
                list(playback_chunks(0, 128))

    def test_playback_has_reserve_for_scheduling_jitter(self):
        for rate in (44100, 48000, 96000):
            for frames in (128, 256, 512, 2048):
                attrs = buffer_attributes(rate, frames)
                self.assertGreaterEqual(attrs.fragsize/8/rate, .01)
                self.assertGreaterEqual(attrs.tlength, 3*frames*8)
                self.assertEqual(attrs.minreq*3, attrs.tlength)
                self.assertEqual(attrs.prebuf, 0xffffffff)
