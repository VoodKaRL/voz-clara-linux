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
            XDG_CONFIG_HOME=str(cls.runtime / 'config'),
            XDG_STATE_HOME=str(cls.runtime / 'state'),
            XDG_CACHE_HOME=str(cls.runtime / 'cache'),
            PULSE_SERVER='unix:'+str(cls.runtime / 'pulse/native'))
        cls.log = (cls.runtime / 'server.log').open('wb')
        cls.server = None
        cls.addClassCleanup(cls.shutdown)
        backend = os.environ.get('VOZ_CLARA_TEST_BACKEND', 'pulseaudio')
        if backend == 'pipewire':
            # A separate socket alone doesn't isolate hardware or saved policy.
            # Disable discovery for both WirePlumber 0.5 and the older 0.4 CI.
            wp = cls.runtime / 'config/wireplumber'
            fragment = wp / 'wireplumber.conf.d/90-no-hardware.conf'
            fragment.parent.mkdir(parents=True)
            fragment.write_text('wireplumber.profiles = { main = {\n'
                'monitor.alsa = disabled\nmonitor.alsa-midi = disabled\n'
                'monitor.bluez = disabled\nmonitor.bluez-midi = disabled\n'
                'monitor.v4l2 = disabled\nmonitor.libcamera = disabled\n} }\n')
            for directory, names in (('main.lua.d', ('alsa_monitor', 'v4l2_monitor', 'libcamera_monitor')),
                                     ('bluetooth.lua.d', ('bluez_monitor',))):
                legacy = wp / directory / '90-no-hardware.lua'
                legacy.parent.mkdir(parents=True)
                legacy.write_text('\n'.join(f'if {name} then {name}.enabled = false end' for name in names))
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
        def logged_open(program, device, role):
            log = (self.runtime / (role+'.log')).open('wb')
            self.addCleanup(log.close)
            options = dict(stderr=log, bufsize=0, env=self.env)
            options['stdout' if program == 'parec' else 'stdin'] = subprocess.PIPE
            return subprocess.Popen(self.engine.stream_command(program, device, role), **options)
        self.engine.open_audio = logged_open
        self.engine.start('test_mic', 'test_speaker', 48000, 256)
        self.engine.processor.gate_db = -80
        self.engine.headphones.volume_db = 0

    def tearDown(self):
        print('Engine error:', self.engine.error, flush=True)
        for path in self.runtime.glob('*.log'):
            print(path.name, path.read_text(errors='replace'), flush=True)
        for kind in ('sources', 'sinks', 'source-outputs', 'sink-inputs'):
            print(kind, audio.pactl('-f', 'json', 'list', kind), flush=True)

    def tone(self, sink, frequency):
        log = (self.runtime / ('tone-'+sink+'.log')).open('wb')
        self.addCleanup(log.close)
        process = subprocess.Popen(['pacat', '--playback', f'--device={sink}',
            *audio.stream_args(48000, 256)], stdin=subprocess.PIPE, stderr=log,
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

    def record(self, source, duration=3, full=False):
        path = self.runtime / ('record-'+str(time.monotonic_ns())+'.raw')
        with path.open('wb') as output:
            process = subprocess.Popen(['parec', f'--device={source}', *audio.stream_args(48000, 256)],
                stdout=output, stderr=subprocess.PIPE, env=self.env)
            # PulseAudio may negotiate/start a new monitor capture late. Test
            # an actual duration of samples, not wall time since Popen().
            required_frames = int(duration*48000)
            deadline = time.monotonic()+duration+5
            while path.stat().st_size < required_frames*8 and time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                time.sleep(.05)
            audio.Engine.terminate(process)
            detail = process.stderr.read().decode(errors='replace')
            process.stderr.close()
        raw = path.read_bytes()
        samples = np.frombuffer(raw[:len(raw)//8*8], dtype='<f4').reshape(-1, 2)
        self.assertGreaterEqual(len(samples), required_frames,
            'La ruta no entregó audio a tiempo: '+detail+'; motor: '+self.engine.error+
            '; servidor: '+(self.runtime / 'server.log').read_text(errors='replace'))
        self.assertTrue(np.isfinite(samples).all())
        return samples if full else samples[-4800:]

    def test_jitter_and_peak_protection_without_voice_monitoring(self):
        process = self.engine.processor.process
        calls = 0
        def jittered(samples):
            nonlocal calls
            calls += 1
            if calls % 7 == 0:
                time.sleep(.012)
            return process(samples)
        self.engine.processor.process = jittered
        self.engine.processor.gain_db = 12
        self.engine.headphones.gains = (12, 12, 12, 12, 12)
        self.engine.headphones.volume_db = 12
        self.tone('test_feed', 220)
        self.tone(audio.SPEAKER_SINK, 1000)
        time.sleep(.5)
        for source in (audio.MIC_SOURCE, 'test_speaker.monitor'):
            samples = self.record(source, duration=3, full=True)
            # Ignore startup; sustained 100 ms holes must not be hidden by
            # looking only at the last block of an otherwise broken stream.
            stable = samples[48000:]
            windows = len(stable)//4800
            self.assertGreater(windows, 5)
            rms = [float(np.std(w)) for w in np.split(stable[:windows*4800], windows)]
            self.assertGreater(min(rms), .002, 'Corte sostenido durante la prueba de jitter')
            self.assertLessEqual(float(np.max(np.abs(stable))), .951)
        self.assertFalse(self.engine.error, self.engine.error)

    def test_desktop_eq_monitor_and_default_switch_have_separate_routes(self):
        self.engine.use_as_defaults()
        stop_desktop = self.tone(audio.SPEAKER_SINK, 1000)
        time.sleep(.4)
        neutral = float(np.std(self.record('test_speaker.monitor')))
        self.assertGreater(neutral, .005, 'Oírme OFF no debe silenciar el escritorio')
        # Repeat after all streams are fully connected, not just during startup.
        audio.pactl('set-default-source', 'test_mic')
        audio.pactl('set-default-sink', 'test_speaker')
        self.engine.use_as_defaults()
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
