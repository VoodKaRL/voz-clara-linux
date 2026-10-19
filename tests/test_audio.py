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
    def test_virtual_microphone_amplification_is_capped_without_touching_hardware(self):
        engine = Engine()
        records = {
            'sources': [{'name': name, 'volume': {'left': {'value': 99000}}}
                        for name in (audio.MIC_SOURCE, audio.MIC_BUS+'.monitor', 'physical-mic')],
            'sinks': [{'name': audio.MIC_BUS, 'volume': {'left': {'value': 99000}}}],
            'source-outputs': [], 'sink-inputs': []}
        calls = []
        def server(*args):
            calls.append(args)
            return json.dumps(records[args[-1]]) if args[0] == '-f' else ''
        with patch.object(engine.guard_stop, 'wait', side_effect=[False, True]), \
                patch.object(audio, 'pactl', side_effect=server):
            engine.guard_routes()
        self.assertIn(('set-source-volume', audio.MIC_SOURCE, '100%'), calls)
        self.assertIn(('set-source-volume', audio.MIC_BUS+'.monitor', '100%'), calls)
        self.assertIn(('set-sink-volume', audio.MIC_BUS, '100%'), calls)
        self.assertFalse(any('physical-mic' in call for call in calls))

    def test_stopped_guard_cannot_fail_a_new_session(self):
        engine = Engine()
        old_stop = engine.guard_stop
        def server(*args):
            old_stop.set()
            engine.guard_stop = __import__('threading').Event()
            return '[]'
        with patch.object(old_stop, 'wait', return_value=False), \
                patch.object(audio, 'pactl', side_effect=server):
            engine.guard_routes(old_stop)
        self.assertFalse(engine.fault.is_set())
        self.assertEqual(engine.error, '')

    def test_bad_capture_is_cleaned_before_noise_processing(self):
        engine = Engine()
        samples = np.full((128, 2), .1, dtype='<f4')
        samples[0] = [np.nan, np.inf]
        reader = SimpleNamespace(stdout=io.BytesIO(samples.tobytes()))
        output = io.BytesIO()
        def clean_noise(a):
            self.assertTrue(np.isfinite(a).all())
            return a
        with patch.object(engine.noise, 'process', side_effect=clean_noise) as noise:
            engine.run(reader, SimpleNamespace(stdin=output), 128)
        self.assertEqual(noise.call_count, 1)
        self.assertTrue(np.isfinite(engine.input_peak))
        self.assertTrue(np.isfinite(np.frombuffer(output.getvalue(), dtype='<f4')).all())

    def test_failed_default_sink_restores_actual_previous_source(self):
        engine = Engine()
        engine.modules = ['test']
        engine.source = 'selected-physical-mic'
        calls = []
        def server(*args):
            calls.append(args)
            if args[0] == 'get-default-source':
                return 'users-other-mic'
            if args[0] == 'set-default-sink':
                raise RuntimeError('sink unavailable')
            return ''
        with patch.object(audio, 'pactl', side_effect=server):
            with self.assertRaisesRegex(RuntimeError, 'sink unavailable'):
                engine.use_as_defaults()
        self.assertEqual(calls[-1], ('set-default-source', 'users-other-mic'))

    def test_system_audio_passes_with_monitor_off(self):
        engine = Engine()
        engine.headphones.volume_db = 0
        desktop = np.full((128, 2), .03, dtype='float32')
        original = desktop.copy()
        engine.monitor(False, None)
        np.testing.assert_allclose(engine.mix_speakers(desktop), original, atol=1e-7)
        np.testing.assert_array_equal(desktop, original)
        engine.headphones.muted = True
        self.assertEqual(float(np.max(np.abs(engine.mix_speakers(desktop)))), 0)

    def test_monitor_adds_voice_only_to_speaker_mix(self):
        engine = Engine()
        engine.sink = 'physical-speaker'
        engine.headphones.volume_db = 0
        engine.monitor(True, 'physical-speaker')
        desktop = np.full((128, 2), .01, dtype='float32')
        engine.monitor_queue.put(np.full((128, 2), .02, dtype='float32'))
        np.testing.assert_allclose(engine.mix_speakers(desktop), .03, atol=1e-7)
        engine.monitor(False, None)
        np.testing.assert_allclose(engine.mix_speakers(desktop), .01, atol=1e-7)

    def test_stream_targets_reject_virtual_devices(self):
        for name in ('voz_clara_mic', 'voz_clara_altavoces', 'voz_clara_bus', '@DEFAULT_SOURCE@', 'alsa_output.card.monitor'):
            with self.assertRaises(RuntimeError):
                audio.validate_device(name, 'sources')

    def test_guard_detects_capture_rerouted_into_its_own_microphone(self):
        sources = [{'index': 1, 'name': 'physical-mic'}, {'index': 2, 'name': audio.MIC_SOURCE}]
        stream = {'source': 1, 'properties': {'voz_clara.session': 'test', 'voz_clara.role': 'microphone-input'}}
        expected = {'microphone-input': 'physical-mic'}
        self.assertEqual(audio.routing_error(sources, [], [stream], [], expected, 'test'), '')
        stream['source'] = 2
        self.assertIn('bucle', audio.routing_error(sources, [], [stream], [], expected, 'test'))
        self.assertEqual(audio.routing_error(sources, [], [stream], [], expected, 'other-session'), '')

    def test_stop_restores_defaults_only_when_ours_are_selected(self):
        engine = Engine()
        engine.modules = ['test-module']
        engine.source, engine.sink = 'physical-mic', 'physical-speaker'
        engine.previous_defaults = {'source': 'previous-mic', 'sink': 'previous-speaker'}
        calls = []
        def server(*args):
            calls.append(args)
            if args[0] == 'get-default-source':
                return audio.MIC_SOURCE
            if args[0] == 'get-default-sink':
                return 'user-chose-another-speaker'
            return ''
        with patch.object(audio, 'pactl', side_effect=server):
            engine.stop()
        self.assertIn(('set-default-source', 'previous-mic'), calls)
        self.assertFalse(any(call[0] == 'set-default-sink' for call in calls))

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
