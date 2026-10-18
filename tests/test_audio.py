import io
import unittest
import queue
from types import SimpleNamespace
import numpy as np
import json
import stat
from unittest.mock import patch
import audio
from audio import read_exact, write_all, stream_args, Engine


class Fragments(io.BytesIO):
    def read(self, count):
        return super().read(min(count, 3))


class PartialWriter(io.BytesIO):
    def write(self, data):
        return super().write(data[:3])


class RoutingTests(unittest.TestCase):
    def test_null_labels_and_fake_devices(self):
        records = [{'name': 'alsa_input.usb', 'description': None},
            {'name': 'auto_null', 'description': 'Dummy Output'},
            {'name': 'voz_clara_mic', 'description': 'Voz Clara'},
            {'name': None, 'description': None},
            {'name': 'alsa_output.card.monitor', 'description': 'Monitor'}]
        self.assertEqual(audio.device_list(records, 'sources'), [('alsa_input.usb', 'alsa_input.usb')])
        records = [{'name': 'alsa_output.usb', 'description': 'null'},
                   {'name': 'alsa_output.card', 'description': 'Auriculares USB'}]
        self.assertEqual(audio.device_list(records, 'sinks'),
            [('alsa_output.usb', 'alsa_output.usb'), ('alsa_output.card', 'Auriculares USB')])

    def test_container_retries_host_socket_and_reuses_connection(self):
        dummy = json.dumps([{'name': 'auto_null'}])
        source = json.dumps([{'name': 'alsa_input.usb', 'description': 'Micrófono USB'}])
        sink = json.dumps([{'name': 'alsa_output.usb', 'description': 'Auriculares'}])
        with patch.object(audio, '_audio_env', None), patch.object(audio, 'in_container', return_value=True), \
                patch.object(audio.os, 'getuid', return_value=1000, create=True), \
                patch.object(audio.Path, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFSOCK)), \
                patch.object(audio.subprocess, 'check_output', side_effect=[dummy, dummy, source, sink, 'OK']) as command:
            audio.configure_audio()
            self.assertEqual(audio.audio_environment()['PULSE_SERVER'], 'unix:/run/user/1000/pulse/native')
            audio.pactl('info')
            self.assertEqual(command.call_args.kwargs['env']['PULSE_SERVER'], 'unix:/run/user/1000/pulse/native')

    def test_dummy_server_is_an_error_not_a_device(self):
        with patch.object(audio, '_audio_env', None), patch.object(audio, 'in_container', return_value=False), \
                patch.object(audio.subprocess, 'check_output', return_value=json.dumps([{'name': 'auto_null'}])):
            with self.assertRaisesRegex(RuntimeError, 'ficticios'):
                audio.configure_audio()

    def test_host_bridge_is_used_for_capture_and_playback(self):
        dummy = json.dumps([{'name': 'auto_null'}])
        mic = json.dumps([{'name': 'alsa_input.usb'}])
        speaker = json.dumps([{'name': 'alsa_output.usb'}])
        with patch.object(audio, '_audio_env', None), patch.object(audio, '_audio_prefix', []), \
                patch.object(audio, 'in_container', return_value=True), \
                patch.object(audio.os, 'getuid', return_value=1000, create=True), \
                patch.object(audio.Path, 'stat', side_effect=FileNotFoundError), \
                patch.object(audio.shutil, 'which', return_value='/usr/bin/distrobox-host-exec'), \
                patch.object(audio.subprocess, 'check_output', side_effect=[b'', dummy, dummy, mic, speaker]):
            audio.configure_audio()
            self.assertEqual(audio.audio_command('pactl'), ['distrobox-host-exec', 'pactl'])
            self.assertEqual(audio.audio_command('parec'), ['distrobox-host-exec', 'parec'])
            self.assertEqual(audio.audio_command('pacat'), ['distrobox-host-exec', 'pacat'])

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
