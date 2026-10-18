"""Small stdlib-only libpulse pipe client with server-enforced immovable streams."""
import ctypes as c
import os
import sys

PA_STREAM_DONT_MOVE = 0x200
PA_STREAM_ADJUST_LATENCY = 0x2000
STREAM_FLAGS = PA_STREAM_DONT_MOVE | PA_STREAM_ADJUST_LATENCY


class SampleSpec(c.Structure):
    _fields_ = [('format', c.c_int), ('rate', c.c_uint32), ('channels', c.c_uint8)]


class BufferAttr(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in ('maxlength', 'tlength', 'prebuf', 'minreq', 'fragsize')]


def main(mode, device, rate, frames, role, session):
    lib = c.CDLL('libpulse.so.0')
    ptr, size = c.c_void_p, c.c_size_t
    state_cb = c.CFUNCTYPE(None, ptr, ptr)
    data_cb = c.CFUNCTYPE(None, ptr, size, ptr)
    def api(name, result, *args):
        fn = getattr(lib, 'pa_'+name)
        fn.restype, fn.argtypes = result, list(args)
        return fn
    new_loop = api('threaded_mainloop_new', ptr)
    get_api = api('threaded_mainloop_get_api', ptr, ptr)
    start = api('threaded_mainloop_start', c.c_int, ptr)
    lock = api('threaded_mainloop_lock', None, ptr)
    unlock = api('threaded_mainloop_unlock', None, ptr)
    wait = api('threaded_mainloop_wait', None, ptr)
    signal = api('threaded_mainloop_signal', None, ptr, c.c_int)
    context_new = api('context_new', ptr, ptr, c.c_char_p)
    context_cb = api('context_set_state_callback', None, ptr, state_cb, ptr)
    connect = api('context_connect', c.c_int, ptr, c.c_char_p, c.c_int, ptr)
    context_state = api('context_get_state', c.c_int, ptr)
    props_new = api('proplist_new', ptr)
    props_set = api('proplist_sets', c.c_int, ptr, c.c_char_p, c.c_char_p)
    props_free = api('proplist_free', None, ptr)
    stream_new = api('stream_new_with_proplist', ptr, ptr, c.c_char_p, c.POINTER(SampleSpec), ptr, ptr)
    stream_cb = api('stream_set_state_callback', None, ptr, state_cb, ptr)
    stream_data_cb = api('stream_set_read_callback' if mode == 'record' else 'stream_set_write_callback',
                         None, ptr, data_cb, ptr)
    stream_state = api('stream_get_state', c.c_int, ptr)
    record = api('stream_connect_record', c.c_int, ptr, c.c_char_p, c.POINTER(BufferAttr), c.c_int)
    playback = api('stream_connect_playback', c.c_int, ptr, c.c_char_p, c.POINTER(BufferAttr), c.c_int, ptr, ptr)
    available = api('stream_readable_size' if mode == 'record' else 'stream_writable_size', size, ptr)
    peek = api('stream_peek', c.c_int, ptr, c.POINTER(ptr), c.POINTER(size))
    drop = api('stream_drop', c.c_int, ptr)
    write = api('stream_write', c.c_int, ptr, ptr, size, ptr, c.c_int64, c.c_int)
    loop = new_loop()
    if not loop:
        raise RuntimeError('No se pudo crear el cliente de audio.')
    context = context_new(get_api(loop), b'Voz Clara')
    @state_cb
    def changed(_object, _userdata):
        signal(loop, 0)
    @data_cb
    def ready(_stream, _bytes, _userdata):
        signal(loop, 0)
    def check(result):
        if result < 0:
            raise RuntimeError('Falló la conexión fija con el dispositivo '+device)
    def ensure_live():
        if context_state(context) != 4 or stream_state(stream) != 2:
            raise RuntimeError('El dispositivo de audio se desconectó: '+device)
    def pipe_write(data):
        view = memoryview(data)
        while view:
            view = view[os.write(1, view):]
    check(start(loop))
    lock(loop)
    try:
        context_cb(context, changed, None)
        check(connect(context, None, 0, None))
        while context_state(context) != 4:
            if context_state(context) in (5, 6):
                raise RuntimeError('No se pudo conectar al servidor de audio.')
            wait(loop)
        props = props_new()
        for key, value in {'target.object': device, 'node.dont-move': 'true',
                'node.dont-reconnect': 'true', 'node.dont-fallback': 'true',
                'media.role': 'filter', 'voz_clara.role': role, 'voz_clara.session': session}.items():
            props_set(props, key.encode(), value.encode())
        spec = SampleSpec(5, rate, 2)  # PA_SAMPLE_FLOAT32LE
        stream = stream_new(context, ('Voz Clara '+role).encode(), c.byref(spec), None, props)
        props_free(props)
        if not stream:
            raise RuntimeError('No se pudo crear el flujo de audio.')
        stream_cb(stream, changed, None)
        stream_data_cb(stream, ready, None)
        attrs = BufferAttr(0xffffffff, frames*8, 0, max(32, frames//2)*8, frames*8)
        if mode == 'record':
            check(record(stream, device.encode(), c.byref(attrs), STREAM_FLAGS))
        else:
            check(playback(stream, device.encode(), c.byref(attrs), STREAM_FLAGS, None, None))
        while stream_state(stream) != 2:
            if stream_state(stream) in (3, 4):
                raise RuntimeError('No se pudo abrir el dispositivo: '+device)
            wait(loop)
    finally:
        unlock(loop)
    while True:
        if mode == 'record':
            lock(loop)
            try:
                ensure_live()
                while available(stream) == 0:
                    wait(loop)
                    ensure_live()
                data, count = ptr(), size()
                check(peek(stream, c.byref(data), c.byref(count)))
                chunk = c.string_at(data, count.value) if data.value else bytes(count.value)
                check(drop(stream))
            finally:
                unlock(loop)
            pipe_write(chunk)
        else:
            chunk = os.read(0, frames*8)
            if not chunk:
                return
            lock(loop)
            try:
                ensure_live()
                position = 0
                while position < len(chunk):
                    count = min(available(stream), len(chunk)-position)
                    if not count:
                        wait(loop)
                        ensure_live()
                        continue
                    data = c.create_string_buffer(chunk[position:position+count])
                    check(write(stream, data, count, None, 0, 0))
                    position += count
            finally:
                unlock(loop)


if __name__ == '__main__':
    try:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6])
        os._exit(0)  # The OS tears down libpulse's worker thread with the pipe client.
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        os._exit(1)
