"""Opt-in integration tests against an isolated audio server; never the desktop session."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
import audio


@unittest.skipUnless(os.name == 'posix' and os.environ.get('VOZ_CLARA_AUDIO_TEST') == '1',
                     'Requiere servidor de audio aislado en CI Linux')
class LinuxAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='voz-clara-audio-')
        cls.runtime = Path(cls.temp.name)
        cls.runtime.chmod(0o700)
        cls.env = dict(os.environ, XDG_RUNTIME_DIR=str(cls.runtime),
            PULSE_SERVER='unix:'+str(cls.runtime / 'pulse/native'))
        cls.log = (cls.runtime / 'server.log').open('wb')
        cls.server = None
        cls.addClassCleanup(cls.shutdown)
        backend = os.environ.get('VOZ_CLARA_TEST_BACKEND', 'pulseaudio')
        if backend == 'pipewire':
            command = ['dbus-run-session', '--', 'sh', '-c', 'pipewire & pipewire-pulse & wireplumber & wait']
        else:
            (cls.runtime / 'pulse').mkdir()
            command = ['pulseaudio', '-n', '--daemonize=no', '--use-pid-file=no', '--exit-idle-time=-1',
                '--load=module-native-protocol-unix socket='+str(cls.runtime / 'pulse/native')+' auth-anonymous=1']
        cls.server = subprocess.Popen(command, env=cls.env, stdout=cls.log, stderr=cls.log,
                                      start_new_session=True)
        until = time.monotonic()+20
        while time.monotonic() < until:
            try:
                subprocess.check_output(['pactl', 'info'], env=cls.env, stderr=subprocess.DEVNULL, timeout=1)
                break
            except (subprocess.SubprocessError, OSError):
                time.sleep(.1)
        else:
            cls.log.flush()
            raise RuntimeError((cls.runtime / 'server.log').read_text(errors='replace'))
        cls.patch_env = patch.object(audio, '_audio_env', cls.env)
        cls.patch_prefix = patch.object(audio, '_audio_prefix', [])
        cls.patch_env.start()
        cls.patch_prefix.start()
        cls.addClassCleanup(cls.patch_env.stop)
        cls.addClassCleanup(cls.patch_prefix.stop)
        # Hardware substitutes: no access to any actual microphone or speaker.
        audio.pactl('load-module', 'module-null-sink', 'sink_name=test_feed', 'rate=48000', 'channels=2')
        audio.pactl('load-module', 'module-remap-source', 'master=test_feed.monitor',
                    'source_name=test_mic', 'channels=2')
        audio.pactl('load-module', 'module-null-sink', 'sink_name=test_speaker', 'rate=48000', 'channels=2')
        audio.pactl('set-default-source', 'test_mic')
        audio.pactl('set-default-sink', 'test_speaker')

    @classmethod
    def shutdown(cls):
        if cls.server is not None and cls.server.poll() is None:
            os.killpg(cls.server.pid, signal.SIGTERM)
            try:
                cls.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(cls.server.pid, signal.SIGKILL)
                cls.server.wait()
        cls.log.close()
        cls.temp.cleanup()

    def setUp(self):
        self.engine = audio.Engine()
        self.addCleanup(self.engine.stop)
        self.engine.start('test_mic', 'test_speaker', 48000, 256)
        self.engine.processor.gate_db = -80
        self.engine.headphones.volume_db = 0

    def tone(self, sink, frequency):
        process = subprocess.Popen(['pacat', '--playback', f'--device={sink}',
            *audio.stream_args(48000, 256)], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=self.env, bufsize=0)
        def feed():
            wave = np.repeat((.02*np.sin(2*np.pi*frequency*np.arange(4800)/48000))[:, None], 2, axis=1).astype('<f4')
            try:
                while process.poll() is None:
                    audio.write_all(process.stdin, wave.tobytes())
            except (OSError, ValueError):
                pass
        thread = threading.Thread(target=feed, daemon=True)
        thread.start()
        def stop():
            audio.Engine.terminate(process)
            thread.join(timeout=2)
        self.addCleanup(stop)
        return stop

    def record(self, source, duration=.8):
        path = self.runtime / ('record-'+str(time.monotonic_ns())+'.raw')
        with path.open('wb') as output:
            process = subprocess.Popen(['parec', f'--device={source}', *audio.stream_args(48000, 256)],
                stdout=output, stderr=subprocess.DEVNULL, env=self.env)
            time.sleep(duration)
            audio.Engine.terminate(process)
        raw = path.read_bytes()
        samples = np.frombuffer(raw[:len(raw)//8*8], dtype='<f4').reshape(-1, 2)
        self.assertGreater(len(samples), 4800, 'La ruta no entregó audio a tiempo')
        self.assertTrue(np.isfinite(samples).all())
        return samples[-4800:]

    def test_desktop_eq_monitor_and_default_switch_have_separate_routes(self):
        self.engine.use_as_defaults()
        stop_desktop = self.tone(audio.SPEAKER_SINK, 1000)
        time.sleep(.4)
        neutral = float(np.std(self.record('test_speaker.monitor')))
        self.assertGreater(neutral, .005, 'Oírme OFF no debe silenciar el escritorio')
        self.engine.headphones.gains = (0, 0, 12, 0, 0)
        boosted = float(np.std(self.record('test_speaker.monitor')))
        self.assertGreater(boosted, neutral*2, 'El EQ debe afectar el audio del sistema')
        virtual_mic = self.record(audio.MIC_SOURCE)
        self.assertLess(float(np.max(np.abs(virtual_mic))), .0001,
                        'El audio del sistema no debe entrar al micrófono virtual')
        stop_desktop()
        self.engine.headphones.gains = (0, 0, 0, 0, 0)
        self.tone('test_feed', 220)
        virtual_mic = self.record(audio.MIC_SOURCE)
        self.assertGreater(float(np.std(virtual_mic)), .005)
        self.assertLess(float(np.max(np.abs(virtual_mic))), .1,
                        'Cambiar el predeterminado no debe crear realimentación')
        time.sleep(.3)
        off = self.record('test_speaker.monitor')
        self.assertLess(float(np.std(off)), .0001, 'Oírme OFF debe excluir solo la voz')
        self.engine.monitor(True, 'test_speaker')
        on = self.record('test_speaker.monitor')
        self.assertGreater(float(np.std(on)), .004, 'Oírme ON debe funcionar aunque el escritorio esté en silencio')
        self.engine.monitor(False, None)
        self.assertFalse(self.engine.error, self.engine.error)
        self.engine.stop()
        self.assertEqual(audio.pactl('get-default-source'), 'test_mic')
        self.assertEqual(audio.pactl('get-default-sink'), 'test_speaker')


if __name__ == '__main__':
    unittest.main()
