import io
import unittest
import queue
from types import SimpleNamespace
import numpy as np
from audio import read_exact, write_all, stream_args, Engine


class Fragments(io.BytesIO):
    def read(self, count):
        return super().read(min(count, 3))


class PartialWriter(io.BytesIO):
    def write(self, data):
        return super().write(data[:3])


class RoutingTests(unittest.TestCase):
    def test_partial_pipe_reads_and_writes(self):
        data = b'0123456789abcdef'
        self.assertEqual(read_exact(Fragments(data), len(data)), data)
        writer = PartialWriter()
        write_all(writer, data)
        self.assertEqual(writer.getvalue(), data)
        with self.assertRaises(RuntimeError):
            read_exact(Fragments(b'abc'), 8)

    def test_small_server_buffers(self):
        args = stream_args(48000, 128)
        self.assertIn('--latency=1024', args)
        self.assertIn('--process-time=512', args)
        self.assertIn('--channels=2', args)

    def test_stop_before_start_is_safe(self):
        engine = Engine()
        engine.stop()
        engine.stop()

    def test_slow_headphones_do_not_block_virtual_microphone(self):
        engine = Engine()
        engine.stopping = False
        engine.processor.gate_db = -80
        engine.monitor_queue = queue.Queue(maxsize=2)
        source = SimpleNamespace(stdout=io.BytesIO(np.full((128*8, 2), .1, dtype='<f4').tobytes()))
        output = io.BytesIO()
        engine.run(source, SimpleNamespace(stdin=output), 128)
        self.assertEqual(len(output.getvalue()), 128*8*8)
        self.assertEqual(engine.monitor_queue.qsize(), 2)
        self.assertEqual(engine.dropped, 6)


if __name__ == '__main__':
    unittest.main()
