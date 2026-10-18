import json
import shutil
import subprocess
import threading
import queue
import time
import os
import stat
import uuid
import sys
from pathlib import Path
from dsp import Processor, Headphones, MicrophoneOutput
from noise import NoiseSuppressor

_audio_env = None
_audio_prefix = []


def in_container():
    return Path('/run/.containerenv').exists() or Path('/.dockerenv').exists()


def audio_environment():
    return dict(_audio_env if _audio_env is not None else os.environ)


def audio_command(program):
    return [*_audio_prefix, program]


def device_list(records, kind):
    result = []
    for device in records:
        name = device.get('name')
        if not isinstance(name, str) or not name or name.lower() in ('null', 'none'):
            continue
        if name.startswith('voz_clara') or name in ('auto_null', 'auto_null.monitor'):
            continue
        properties = device.get('properties') or {}
        if device.get('driver') == 'module-null-sink.c' or properties.get('factory.name') == 'support.null-audio-sink':
            continue
        if kind == 'sources' and (name.endswith('.monitor') or
                device.get('monitor_of_sink') not in (None, 4294967295, '4294967295')):
            continue
        label = device.get('description') or properties.get('device.description') or properties.get('node.description')
        if not isinstance(label, str) or label.strip().lower() in ('', 'null', '(null)', 'none'):
            label = name
        result.append((name, label))
    return result


def configure_audio():
    """Prefer the host socket in Distrobox; never silently accept a dummy server."""
    global _audio_env, _audio_prefix
    base = dict(os.environ)
    candidates = []
    if in_container() and hasattr(os, 'getuid'):
        uid = os.getuid()
        paths = [f'/run/host/run/user/{uid}/pulse/native',
                 f'/run/user/{uid}/pulse/native']
        runtime = base.get('XDG_RUNTIME_DIR')
        if runtime:
            paths.append(str(Path(runtime) / 'pulse/native'))
        for path in dict.fromkeys(paths):
            try:
                if stat.S_ISSOCK(Path(path).stat().st_mode):
                    candidates.append((dict(base, PULSE_SERVER='unix:'+path), []))
            except OSError:
                pass
    candidates.append((base, []))
    # If the host socket isn't mounted, use Distrobox's host bridge for ALL
    # audio commands, including capture/playback; do not mix two servers.
    if in_container() and shutil.which('distrobox-host-exec'):
        try:
            subprocess.check_output(['distrobox-host-exec', 'sh', '-c',
                'command -v pactl >/dev/null && command -v parec >/dev/null && command -v pacat >/dev/null'],
                stderr=subprocess.PIPE, timeout=5)
            candidates.append((base, ['distrobox-host-exec']))
        except (OSError, subprocess.SubprocessError):
            pass
    errors = []
    for env, prefix in candidates:
        try:
            sources = json.loads(subprocess.check_output([*prefix, 'pactl', '-f', 'json', 'list', 'sources'],
                text=True, stderr=subprocess.PIPE, timeout=5, env=env))
            sinks = json.loads(subprocess.check_output([*prefix, 'pactl', '-f', 'json', 'list', 'sinks'],
                text=True, stderr=subprocess.PIPE, timeout=5, env=env))
            if not device_list(sources, 'sources') and not device_list(sinks, 'sinks'):
                errors.append('El servidor solo ofrece dispositivos ficticios (null) o ningún dispositivo.')
                continue
            _audio_env = env
            _audio_prefix = prefix
            return
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            detail = getattr(exc, 'stderr', None) or str(exc)
            errors.append(str(detail).strip())
    _audio_env = None
    _audio_prefix = []
    raise RuntimeError('No se ven los dispositivos de audio del sistema. '
        'En Bazzite, cierra la app y repite el instalador actualizado. '
        + (errors[-1] if errors else 'No se encontró el servidor de audio.'))


def stream_args(rate, frames):
    # Float32 stereo. Request small server fragments as well as small app blocks.
    return ['--raw', '--format=float32le', f'--rate={rate}', '--channels=2',
            '--channel-map=front-left,front-right', f'--latency={frames*8}',
            f'--process-time={max(32, frames//2)*8}', '--client-name=Voz Clara']


def read_exact(stream, count):
    result = bytearray()
    while len(result) < count:
        part = stream.read(count-len(result))
        if not part:
            raise RuntimeError('Se interrumpió la captura del micrófono.')
        result.extend(part)
    return result


def write_all(stream, data):
    view = memoryview(data)
    while view:
        count = stream.write(view)
        if not count:
            raise RuntimeError('Se interrumpió la reproducción de audio.')
        view = view[count:]


def pactl(*args):
    return subprocess.check_output([*audio_command('pactl'), *map(str, args)], text=True, stderr=subprocess.PIPE,
        timeout=5, env=audio_environment()).strip()


def devices(kind):
    return device_list(json.loads(pactl('-f', 'json', 'list', kind)), kind)


MIC_BUS = 'voz_clara_mic_bus'
MIC_SOURCE = 'voz_clara_mic'
SPEAKER_SINK = 'voz_clara_altavoces'


def pinned_args(rate, frames, device, role, session):
    return [f'--device={device}', *stream_args(rate, frames),
            f'--stream-name=Voz Clara {role}',
            f'--property=target.object={device}',
            '--property=node.dont-move=true',
            '--property=node.dont-reconnect=true',
            '--property=node.dont-fallback=true',
            '--property=media.role=filter',
            f'--property=voz_clara.role={role}',
            f'--property=voz_clara.session={session}']


def validate_device(name, kind):
    if not name or name.startswith('voz_clara') or name.startswith('@') or name.lower() in ('null', 'none', 'auto_null'):
        raise RuntimeError('Escoge un dispositivo físico, no un dispositivo de Voz Clara ni el predeterminado.')
    if kind == 'sources' and name.endswith('.monitor'):
        raise RuntimeError('La entrada debe ser un micrófono, no un monitor de altavoz.')
    records = json.loads(pactl('-f', 'json', 'list', kind))
    if not any(d.get('name') == name for d in records):
        raise RuntimeError('El dispositivo elegido se desconectó. Actualiza los dispositivos.')


def routing_error(sources, sinks, captures, playbacks, expected, session):
    """Fail closed if a session manager moves one of our internal streams."""
    for streams, devices_, field in ((captures, sources, 'source'), (playbacks, sinks, 'sink')):
        names = {str(d['index']): d['name'] for d in devices_}
        for stream in streams:
            props = stream.get('properties') or {}
            if props.get('voz_clara.session') != session:
                continue
            role = props.get('voz_clara.role')
            if role in expected and names.get(str(stream.get(field))) != expected[role]:
                return f'La ruta {role} cambió de dispositivo. Audio detenido para evitar un bucle.'
    return ''


class Engine:
    def __init__(self):
        self.modules = []
        self.processes = []
        self.speaker_processes = []
        self.monitor_queue = None
        self.monitor_error = ''
        self.dropped = 0
        self.processing_ms = 0
        self.thread = self.speaker_thread = self.guard_thread = None
        self.stopping = False
        self.error = ''
        self.processor = Processor(48000)
        self.safety = MicrophoneOutput(48000)
        self.noise = NoiseSuppressor(48000)
        self.headphones = Headphones(48000)
        self.fault = threading.Event()
        self.guard_stop = threading.Event()
        self.speaker_stop = threading.Event()
        self.expected = {}
        self.previous_defaults = {}
        self.output_generation = 0
        self.output_switching = False
        self.session = uuid.uuid4().hex

    def open_audio(self, program, device, role):
        options = dict(stderr=subprocess.DEVNULL, bufsize=0, env=audio_environment())
        if program == 'parec':
            options['stdout'] = subprocess.PIPE
        else:
            options['stdin'] = subprocess.PIPE
        return subprocess.Popen(self.stream_command(program, device, role), **options)

    def stream_command(self, program, device, role):
        python = 'python3' if _audio_prefix else sys.executable
        return [*audio_command(python), str(Path(__file__).with_name('pulse_stream.py')),
            'record' if program == 'parec' else 'playback', device,
            str(self.rate), str(self.frames), role, self.session]

    def start(self, source, sink, rate, frames, noise_enabled=False, noise_strength=70):
        for command in ('pactl', 'parec', 'pacat'):
            if not shutil.which(command):
                raise RuntimeError(f'Falta {command}. Repite el instalador de Voz Clara.')
        self.stop()
        validate_device(source, 'sources')
        validate_device(sink, 'sinks')
        if any(d['name'].startswith('voz_clara') for d in json.loads(pactl('-f', 'json', 'list', 'sinks'))):
            raise RuntimeError('Hay otra instancia o módulos antiguos de Voz Clara. Cierra la app anterior antes de iniciar.')
        self.error = ''
        self.stopping = False
        self.fault.clear()
        self.guard_stop.clear()
        self.source, self.sink = source, sink
        self.rate, self.frames = rate, frames
        self.dropped = 0
        self.processor = Processor(rate)
        self.safety = MicrophoneOutput(rate)
        self.noise = NoiseSuppressor(rate)
        self.noise.strength = noise_strength
        self.noise.set_enabled(noise_enabled)
        self.headphones = Headphones(rate)
        self.expected = {'microphone-input': source, 'microphone-output': MIC_BUS,
                         'desktop-input': SPEAKER_SINK+'.monitor', 'hardware-output': sink}
        for kind in ('source', 'sink'):
            try:
                self.previous_defaults[kind] = pactl('get-default-'+kind)
            except Exception:
                pass
        try:
            self.modules.append(pactl('load-module', 'module-null-sink', f'sink_name={MIC_BUS}',
                f'rate={rate}', 'channels=2', 'channel_map=front-left,front-right',
                'sink_properties="device.description=Voz_Clara_Interno_NO_SELECCIONAR device.class=abstract node.hidden=true priority.session=0"'))
            self.modules.append(pactl('load-module', 'module-remap-source', f'master={MIC_BUS}.monitor',
                f'source_name={MIC_SOURCE}', 'channels=2', 'channel_map=front-left,front-right',
                'source_properties=device.description=Voz_Clara_Microfono'))
            self.modules.append(pactl('load-module', 'module-null-sink', f'sink_name={SPEAKER_SINK}',
                f'rate={rate}', 'channels=2', 'channel_map=front-left,front-right',
                'sink_properties=device.description=Voz_Clara_Altavoces'))
            reader = self.open_audio('parec', source, 'microphone-input')
            self.processes.append(reader)
            writer = self.open_audio('pacat', MIC_BUS, 'microphone-output')
            self.processes.append(writer)
            self.thread = threading.Thread(target=self.run, args=(reader, writer, frames), daemon=True)
            self.thread.start()
            self.set_output(sink)
            self.guard_thread = threading.Thread(target=self.guard_routes, daemon=True)
            self.guard_thread.start()
        except Exception:
            self.stop()
            raise

    def run(self, reader, writer, frames):
        import numpy as np
        try:
            while not self.stopping:
                data = read_exact(reader.stdout, frames*8)
                started = time.perf_counter()
                clean = self.noise.process(np.frombuffer(data, dtype='<f4').reshape(-1, 2))
                out = self.safety.process(self.processor.process(clean))
                if self.fault.is_set():
                    out.fill(0)
                self.processing_ms = (time.perf_counter()-started)*1000
                write_all(writer.stdin, out.tobytes())
                target = self.monitor_queue
                if target is not None:
                    try:
                        target.put_nowait(out)
                    except queue.Full:
                        try:
                            target.get_nowait()
                        except queue.Empty:
                            pass
                        self.dropped += 1
                        try:
                            target.put_nowait(out)
                        except queue.Full:
                            pass
        except Exception as exc:
            if not self.stopping:
                self.fault.set()
                self.error = str(exc)

    def set_output(self, sink):
        validate_device(sink, 'sinks')
        self.output_switching = True
        self.output_generation += 1
        self.stop_speakers()
        self.speaker_stop = threading.Event()
        try:
            reader = self.open_audio('parec', SPEAKER_SINK+'.monitor', 'desktop-input')
            self.speaker_processes.append(reader)
            writer = self.open_audio('pacat', sink, 'hardware-output')
            self.speaker_processes.append(writer)
            self.sink = sink
            self.expected['hardware-output'] = sink
            self.speaker_thread = threading.Thread(target=self.run_speakers,
                args=(reader, writer, self.frames, self.speaker_stop), daemon=True)
            self.speaker_thread.start()
        except Exception:
            self.stop_speakers()
            self.fault.set()
            self.error = 'No se pudo abrir el altavoz físico elegido.'
            raise
        finally:
            self.output_switching = False

    def mix_speakers(self, desktop):
        import numpy as np
        mixed = np.array(desktop, dtype=np.float32, copy=True)
        target = self.monitor_queue
        if target is not None:
            try:
                mixed += target.get_nowait()
            except queue.Empty:
                pass
        # One EQ state for the combined desktop + optional microphone signal.
        out = self.headphones.process(mixed)
        if self.fault.is_set():
            out.fill(0)
        return out

    def run_speakers(self, reader, writer, frames, stop):
        import numpy as np
        try:
            while not self.stopping and not stop.is_set():
                data = read_exact(reader.stdout, frames*8)
                desktop = np.frombuffer(data, dtype='<f4').reshape(-1, 2)
                write_all(writer.stdin, self.mix_speakers(desktop).tobytes())
        except Exception as exc:
            if not self.stopping and not stop.is_set():
                self.fault.set()
                self.error = f'Salida de altavoces interrumpida: {exc}'

    def monitor(self, enabled, sink):
        # Oírme controls only whether microphone samples enter the speaker mix.
        # Desktop playback remains active even with Oírme OFF.
        if enabled:
            if sink != self.sink:
                self.set_output(sink)
            self.monitor_queue = queue.Queue(maxsize=2)
        else:
            self.monitor_queue = None

    def use_as_defaults(self):
        if not self.modules or self.stopping:
            raise RuntimeError('Primero inicia el audio de Voz Clara.')
        pactl('set-default-source', MIC_SOURCE)
        try:
            pactl('set-default-sink', SPEAKER_SINK)
        except Exception:
            pactl('set-default-source', self.source)
            raise

    def guard_routes(self):
        while not self.guard_stop.wait(.3):
            if self.output_switching:
                continue
            generation = self.output_generation
            try:
                records = {kind: json.loads(pactl('-f', 'json', 'list', kind))
                    for kind in ('sources', 'sinks', 'source-outputs', 'sink-inputs')}
                if self.output_switching or generation != self.output_generation:
                    continue
                message = routing_error(records['sources'], records['sinks'],
                    records['source-outputs'], records['sink-inputs'], self.expected, self.session)
                if message:
                    self.fault.set()
                    self.error = message
                    return
            except Exception as exc:
                if not self.guard_stop.is_set():
                    self.fault.set()
                    self.error = f'No se pudo comprobar la ruta de audio: {exc}'
                return

    @staticmethod
    def terminate(process):
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()

    def stop_speakers(self):
        self.speaker_stop.set()
        for process in self.speaker_processes:
            self.terminate(process)
        if self.speaker_thread:
            self.speaker_thread.join(timeout=2)
        self.speaker_thread = None
        self.speaker_processes = []

    def stop(self):
        self.stopping = True
        self.guard_stop.set()
        self.fault.set()
        self.monitor_queue = None
        if self.modules:
            # Restore only if the user still has one of OUR endpoints selected.
            for kind, fallback in (('source', getattr(self, 'source', '')), ('sink', getattr(self, 'sink', ''))):
                try:
                    if pactl('get-default-'+kind).startswith('voz_clara'):
                        previous = self.previous_defaults.get(kind) or fallback
                        if previous.startswith('voz_clara'):
                            previous = fallback
                        if previous:
                            pactl('set-default-'+kind, previous)
                except Exception:
                    pass
        self.stop_speakers()
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
        for p in self.processes:
            self.terminate(p)
        if self.thread:
            self.thread.join(timeout=3)
        if self.guard_thread:
            self.guard_thread.join(timeout=1)
        self.thread = self.guard_thread = None
        self.noise.close()
        self.processes = []
        for module in self.modules[::-1]:
            try:
                pactl('unload-module', module)
            except Exception:
                pass
        self.modules = []
        self.previous_defaults = {}
