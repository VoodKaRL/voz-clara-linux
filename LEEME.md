# Voz Clara — Linux

Versión 0.2 en código fuente. Una sola entrada física mono/estéreo, gate con ataque y cierre suave, compresor, panel de tono, volumen y mute de micrófono. Escucha directa con volumen independiente y ecualizador de cinco bandas. Publica un solo micrófono virtual llamado `Voz_Clara`. No incluye entradas AUX ni mezclador de audio del escritorio.

## Instalación

Requiere Linux de escritorio, Python 3.10 o posterior y PipeWire con pipewire-pulse o PulseAudio. No reemplaces tu servidor de audio.

Ubuntu / Debian / Mint:

```sh
sudo apt install python3-venv pulseaudio-utils libegl1 libxcb-cursor0
```

Fedora:

```sh
sudo dnf install python3 python3-pip pulseaudio-utils
```

Arch:

```sh
sudo pacman -S python python-pip libpulse
```

Descomprime la carpeta, abre un terminal en ella y ejecuta:

```sh
bash iniciar.sh
```

La primera ejecución crea un entorno Python local e instala las dependencias; necesita internet. No ejecutes la app con sudo.

## Uso

1. Selecciona tu micrófono en STEREO INPUT. MONO promedia los canales izquierdo y derecho y envía la misma voz a ambos lados. Desactívalo para conservar estéreo. Si el dispositivo físico es mono, el servidor lo adapta a los dos canales del flujo.
2. Elige frecuencia, búfer y salida de auriculares antes de iniciar.
3. Pulsa Iniciar micrófono y selecciona `Voz_Clara` en Discord, OBS o tu aplicación de llamadas.
4. Sube el gate desde −80 hasta que el ruido deje de pasar cuando no hablas. Un gate silencia entre frases; no elimina ruido mientras hablas.
5. Mueve el punto: izquierda realza graves y reduce agudos; derecha hace lo contrario. Arriba aumenta ambas bandas y abajo las reduce. Doble clic devuelve el tono neutro. Es un control propio, no una reproducción del algoritmo Intellipan.
6. COMP, junto al gate, controla la compresión de la voz: 0 la desactiva; 1–10 aumenta la intensidad (umbral de −13,8 a −30 dBFS, relación 1,5:1 a 6:1). Ataque 5 ms, liberación 80 ms y sin lookahead ni ganancia automática. El gate detecta la entrada antes de comprimir; ajusta el volumen del micrófono después.
7. Activa Escuchar mi voz para oír la señal procesada en la salida escogida. Usa auriculares. Su fader de volumen, mute y EQ (80, 250, 1000, 4000 y 12000 Hz; ±12 dB) solo modifican tu escucha. No cambian lo enviado por el micrófono virtual ni el audio de otras aplicaciones. EQ plano restablece las cinco bandas.

Para cambiar dispositivos, Hz o búfer, detén y reinicia la captura. La selección y los controles se guardan al cerrar; no se activa el micrófono automáticamente.

## Alcance y limitaciones

La frecuencia controla el flujo de procesamiento. El búfer controla el bloque de la app y solicita una latencia al servidor, pero no cambia globalmente el quantum de PipeWire ni obliga al hardware a esa frecuencia. La latencia real incluye captura, servidor, procesamiento y reproducción. El medidor muestra salida procesada en un rango de −90 a 0 dBFS. La salida se recorta a ±1 para evitar desbordamiento; demasiada ganancia produce distorsión.

## Escucha en directo y latencia

La versión 0.2 elimina el loopback adicional de 20 ms de la primera versión. Bifurca el bloque procesado: una ruta va al micrófono virtual y otra directamente a los auriculares, sin volver a capturar el monitor virtual. Captura y reproducción usan pipes sin búfer Python y solicitan tanto el tamaño de búfer como el intervalo de procesamiento al servidor. La escucha corre en un hilo separado con un máximo de dos bloques en su cola; ante sobrecarga descarta el más antiguo para no acumular retraso en esa cola. El servidor y los pipes tienen sus propios búferes adicionales.

Punto de partida: 48000 Hz / 128 muestras (2,67 ms por bloque solicitado). Si aparecen cortes, prueba 256 y después 512. El bloque de 2,67 ms no significa 2,67 ms de latencia total. La interfaz muestra el tiempo real empleado por el DSP del último bloque y el número de bloques de escucha descartados; no mide el recorrido completo de audio. Un valor de DSP menor que el bloque es necesario, pero no garantiza ausencia de cortes del sistema.

No existe latencia cero por software. Para comprobar la latencia real, hay que medir en Linux un impulso y su retorno con conexión de bucle físico o una herramienta de medición, con el mismo dispositivo, frecuencia y búfer usados en la app. Para escucharte, favorece auriculares por cable o USB; Bluetooth añade su propia latencia. Discord/OBS pueden añadir otros búferes, procesamiento y retrasos de red. La app procesa continuamente y no graba para reproducir después.

Se crea un bus interno de salida y su monitor técnico para construir el único micrófono virtual público. Herramientas avanzadas de Linux también pueden mostrar ese monitor; no son canales AUX adicionales. La app no cambia los dispositivos predeterminados del sistema.

La implementación usa Qt, NumPy/SciPy y las utilidades de PulseAudio. No es un binario empaquetado ni está validada todavía con hardware Linux. El procesamiento Python puede necesitar bloques mayores en equipos lentos. Si falta un dispositivo, detén, reconecta y pulsa Actualizar dispositivos. Si una aplicación no muestra el micrófono virtual, vuelve a abrir su selector de audio. Si falla la escucha, se desactiva y se mantiene la captura virtual; si falla la captura o la salida virtual, se detiene el motor.

Al detener o cerrar normalmente se eliminan los módulos creados por la app. Si termina abruptamente, consulta `pactl list short modules` y descarga con `pactl unload-module ID` solamente los módulos con `voz_clara` en sus argumentos, primero remap-source y después null-sink. No descargues módulos de otras aplicaciones.

## Verificación

Pruebas: `python -m unittest discover -s tests -v` con las dependencias instaladas. Comprueban gate, tono, compresión, continuidad entre bloques, mono/estéreo, EQ y mute independientes, transferencias parciales de pipes y tamaños de búfer solicitados. Hace falta una prueba adicional en Linux con micrófono real: iniciar, comprobar captura en otra app, escuchar, medir latencia, probar 128/256/512 muestras, verificar que EQ/volumen de auriculares no cambian la grabación virtual y confirmar que al cerrar desaparece el micrófono virtual.

Referencias técnicas: [módulos PulseAudio](https://www.freedesktop.org/wiki/Software/PulseAudio/Documentation/User/Modules/), [opciones de búfer de pacat](https://github.com/pulseaudio/pulseaudio/blob/master/src/utils/pacat.c).
