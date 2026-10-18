# Voz Clara Linux

Un mezclador sencillo para transformar tu micrófono y escucharte en directo en Linux. Una entrada física, un micrófono virtual y controles fáciles de mover.

**Versión 0.2.0 · Experimental.** El procesamiento y la interfaz tienen pruebas automáticas. La captura, la compatibilidad con dispositivos y la latencia total todavía necesitan validación con hardware Linux.

## Qué puedes hacer

- Elegir tu micrófono físico y la salida para escucharte.
- Usar un único micrófono virtual: **Voz_Clara** en Discord, OBS y otras aplicaciones.
- Ajustar gate y compresor para controlar la voz.
- Cambiar graves y agudos moviendo un punto en un panel.
- Activar mono o conservar estéreo.
- Regular el volumen y silenciar el micrófono.
- Escuchar la voz procesada con volumen, silencio y EQ de cinco bandas independientes.
- Elegir frecuencia de procesamiento y tamaño de búfer solicitado.

El EQ y volumen de auriculares solo afectan a tu escucha de la voz; no al audio de otras aplicaciones ni a lo enviado por el micrófono virtual. No hay canales AUX ni mezclador de audio del escritorio.

## Instalar en Linux

### Bazzite GNOME o KDE: un solo comando

En la terminal de Bazzite, con tu usuario normal y sin `sudo`, pega esta única línea:

```bash
curl -fsSL https://raw.githubusercontent.com/VoodKaRL/voz-clara-linux/main/instalar-bazzite.sh | bash
```

El instalador descarga el proyecto, prepara las dependencias de sistema y Python en un contenedor Distrobox dedicado y crea **Voz Clara Linux** en el menú de aplicaciones. La primera vez necesita internet, espacio para el contenedor y varios minutos. Después lo abres desde el menú, sin terminal. Para actualizar, cierra la app y repite el mismo comando; conserva los ajustes.

Bazzite está basado en Fedora, pero utiliza un sistema base atómico: no sigas las instrucciones `sudo dnf install` de Fedora tradicional sobre el host. El instalador usa una imagen Ubuntu 24.04 *dentro de Distrobox* para sus dependencias; tu sistema sigue siendo Bazzite. Distrobox integra la interfaz gráfica y el audio del host. No se instala un servidor de audio adicional ni se requiere reiniciar. Requiere Distrobox y Podman disponibles en Bazzite.

Esta ruta de instalación está preparada, pero aún necesita una prueba completa en un equipo Bazzite real. Si la conexión al audio falla, el instalador muestra el error. No garantiza una latencia específica por usar el contenedor.

Referencias: [instalación de software en Bazzite](https://docs.bazzite.gg/Installing_and_Managing_Software/software-intro/), [integración de Distrobox](https://distrobox.it/).

### Otras distribuciones: instalación manual

Necesitas Python 3.10 o posterior, Git, y un escritorio con **PipeWire + pipewire-pulse** o **PulseAudio**. Conserva el servidor de audio que ya utiliza tu distribución.

Ubuntu / Debian / Linux Mint:

```bash
sudo apt install git python3-venv pulseaudio-utils libegl1 libxcb-cursor0
```

Fedora:

```bash
sudo dnf install git python3 python3-pip pulseaudio-utils
```

Arch Linux:

```bash
sudo pacman -S git python python-pip libpulse
```

Descarga el proyecto desde **Code → Download ZIP** y descomprímelo, o clónalo:

```bash
git clone https://github.com/VoodKaRL/voz-clara-linux.git
cd voz-clara-linux
bash iniciar.sh
```

La primera ejecución instala las dependencias Python en `.venv`, dentro del proyecto. Necesita internet. No ejecutes la app con `sudo`. En Windows puedes descargar y editar el proyecto, pero el motor de audio está destinado exclusivamente a Linux.

## Primer uso

1. Selecciona el micrófono y la salida de auriculares.
2. Empieza con **48000 Hz / 128 muestras**. Si hay cortes, aumenta a 256 o 512.
3. Pulsa **Iniciar micrófono**.
4. En la aplicación de llamadas o grabación, elige **Voz_Clara** como micrófono.
5. Activa **Escuchar mi voz** para monitorizar la señal procesada. Usa auriculares.
6. Ajusta gate, compresor, panel de tono y volumen. El EQ de auriculares es independiente.

Para cambiar dispositivos, Hz o búfer, detén y reinicia la captura. Al cerrar se guardan los controles y se retira el micrófono virtual; la app debe permanecer abierta mientras lo usas.

## Actualizar

**Bazzite:** repite el comando único de instalación anterior con la app cerrada. Las instrucciones siguientes son para la instalación manual de otras distribuciones.

Si lo instalaste con Git, cierra la app y ejecuta desde la carpeta del proyecto:

```bash
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
bash iniciar.sh
```

Si lo descargaste como ZIP, descarga la nueva versión y descomprímela en una carpeta nueva. Los ajustes se guardan con Qt fuera del código fuente.

## Sobre el tiempo real

La app procesa bloques continuamente, sin grabar para reproducir después. Envía cada bloque procesado al micrófono virtual y, si activas la escucha, a los auriculares por una ruta independiente. La escucha no pasa por un loopback adicional y su cola se limita a dos bloques para evitar que acumule retraso si se satura.

**128 muestras a 48000 Hz son 2,67 ms por bloque, no 2,67 ms de latencia total.** El dispositivo, el servidor de audio y la aplicación receptora añaden retraso. No se garantiza latencia cero ni funcionamiento de tiempo real estricto. Para medir la latencia completa hace falta una prueba de retorno físico en Linux. Usa auriculares por cable o USB para reducir el retraso de monitorización.

La interfaz muestra tiempo de DSP por bloque y descartes de la cola de escucha. Si el procesamiento supera el tiempo disponible por bloque o escuchas cortes, aumenta el búfer. Estos indicadores no son una medición de latencia de extremo a extremo.

## Desarrollo y pruebas

Después de instalar dependencias:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Las pruebas cubren DSP, mono/estéreo, compresión, separación del EQ de escucha, continuidad de bloques, transferencias parciales y una escucha atascada que no bloquea el micrófono virtual. GitHub Actions ejecuta estas pruebas en Linux. No sustituyen la validación con hardware.

Al informar un problema incluye distribución, PipeWire o PulseAudio, modelo de micrófono, salida de auriculares, frecuencia y búfer, y qué ocurre. Puedes proponer mejoras en Issues.

Detalles de controles, instalación y solución de problemas: [LEEME.md](LEEME.md). Cambios de cada versión: [CHANGELOG.md](CHANGELOG.md).

Inspirado en la sencillez de los controles de mezcladores de voz. Proyecto independiente, sin afiliación con VB-Audio; no utiliza su código, marca ni algoritmo Intellipan.

## Licencia

[MIT](LICENSE).
