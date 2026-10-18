import json
import shutil
import subprocess
import threading
import queue
import time
import os
import stat
from pathlib import Path
from dsp import Processor, Headphones

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


class Engine:
    def __init__(self):
        self.modules = []
        self.processes = []
        self.monitor_process = None
        self.monitor_thread = None
        self.monitor_queue = None
        self.monitor_error = ''
        self.dropped = 0
        self.processing_ms = 0
        self.thread = None
        self.stopping = False
        self.error = ''
        self.processor = Processor(48000)
        self.headphones = Headphones(48000)

    def start(self, source, rate, frames):
        for command in ('pactl', 'parec', 'pacat'):
            if not shutil.which(command):
                raise RuntimeError(f'Falta {command}. Instala pulseaudio-utils (o libpulse en Arch).')
        self.stop()
        self.error = ''
        self.stopping = False
        try:
            if any(d['name'] == 'voz_clara_bus' for d in json.loads(pactl('-f', 'json', 'list', 'sinks'))):
                raise RuntimeError('Ya existe otra instancia de Voz Clara. Ciérrala antes de iniciar.')
            self.modules.append(pactl('load-module', 'module-null-sink', 'sink_name=voz_clara_bus',
                                      f'rate={rate}', 'channels=2', 'channel_map=front-left,front-right',
                                      'sink_properties=device.description=Voz_Clara_Bus'))
            self.modules.append(pactl('load-module', 'module-remap-source', 'master=voz_clara_bus.monitor',
                                      'source_name=voz_clara_mic', 'channels=2', 'channel_map=front-left,front-right',
                                      'source_properties=device.description=Voz_Clara'))
            self.rate, self.frames = rate, frames
            self.dropped = 0
            common = stream_args(rate, frames)
            reader = subprocess.Popen([*audio_command('parec'), f'--device={source}', *common], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, env=audio_environment())
            self.processes.append(reader)
            writer = subprocess.Popen([*audio_command('pacat'), '--playback', '--device=voz_clara_bus', *common], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, env=audio_environment())
            self.processes.append(writer)
            self.processor = Processor(rate)
            self.headphones = Headphones(rate)
            self.thread = threading.Thread(target=self.run, args=(reader, writer, frames), daemon=True)
            self.thread.start()
        except Exception:
            self.stop()
            raise

    def run(self, reader, writer, frames):
        import numpy as np
        try:
            while not self.stopping:
                data = read_exact(reader.stdout, frames*8)
                started = time.perf_counter()
                out = self.processor.process(np.frombuffer(data, dtype='<f4').reshape(-1, 2))
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
                self.error = str(exc)

    def monitor(self, enabled, sink):
        self.monitor_queue = None
        if self.monitor_process:
            self.terminate(self.monitor_process)
        if self.monitor_thread:
            self.monitor_thread.join(timeout=3)
        self.monitor_process = self.monitor_thread = None
        if enabled:
            if not sink or sink.lower() in ('null', 'none', 'auto_null'):
                raise RuntimeError('Selecciona un altavoz o unos auriculares disponibles.')
            self.monitor_error = ''
            target = queue.Queue(maxsize=2)
            process = subprocess.Popen([*audio_command('pacat'), '--playback', f'--device={sink}',
                *stream_args(self.rate, self.frames)], stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0, env=audio_environment())
            self.monitor_process = process
            self.monitor_queue = target
            self.monitor_thread = threading.Thread(target=self.run_monitor, args=(process, target), daemon=True)
            self.monitor_thread.start()

    def run_monitor(self, process, target):
        try:
            while self.monitor_queue is target and not self.stopping:
                try:
                    out = target.get(timeout=.05)
                except queue.Empty:
                    continue
                write_all(process.stdin, self.headphones.process(out).tobytes())
        except Exception as exc:
            if self.monitor_queue is target and not self.stopping:
                self.monitor_error = f'Escucha interrumpida: {exc}'

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

    def stop(self):
        self.stopping = True
        self.monitor(False, None)
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
        for p in self.processes:
            self.terminate(p)
        if self.thread:
            self.thread.join(timeout=3)
        self.thread = None
        self.processes = []
        for module in self.modules[::-1]:
            try:
                pactl('unload-module', module)
            except Exception:
                pass
        self.modules = []
