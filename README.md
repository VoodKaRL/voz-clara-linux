# Voz Clara Linux

Un mezclador sencillo para transformar tu micrófono y controlar el sonido de Linux. Un micrófono virtual, un altavoz virtual y controles fáciles de mover.

**Versión 0.4.0 · Experimental.** Las pruebas cubren procesamiento, RNNoise y rutas de audio con servidores aislados en Linux. La compatibilidad y la latencia con hardware Bazzite todavía necesitan validación.

## Qué puedes hacer

- Elegir tu micrófono físico y la salida para escucharte.
- Usar **Voz_Clara_Microfono** como entrada predeterminada en Discord, OBS y Linux.
- Usar **Voz_Clara_Altavoces** como salida predeterminada y aplicar volumen y EQ al audio del sistema.
- Ajustar gate y compresor para controlar la voz.
- Cambiar graves y agudos moviendo un punto en un panel.
- Activar mono o conservar estéreo.
- Regular el volumen y silenciar el micrófono.
- Escuchar la voz procesada con volumen, silencio y EQ de cinco bandas independientes.
- Reducir ruido de fondo con **RNNoise**, ON/OFF y potencia de 0 a 100 %, separado del gate.
- Elegir frecuencia de procesamiento y tamaño de búfer solicitado.

El EQ y volumen de salida afectan al audio que las aplicaciones envían a **Voz_Clara_Altavoces** y a tu voz si activas **Oírme**. No modifican lo enviado por el micrófono virtual. **Oírme OFF no silencia el escritorio.** Las aplicaciones que envíen directamente a un altavoz físico evitan el EQ de Voz Clara.

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

1. Selecciona **Escoger micrófono** en el panel izquierdo y **Escoger altavoz / auriculares** en el panel central.
2. Empieza con **48000 Hz / 512 muestras**. Si hay cortes, aumenta a 1024.
3. Pulsa **Iniciar audio**.
4. Pulsa **Conectar a mis apps**, o elige en Ajustes → Sonido de GNOME: entrada **Voz_Clara_Microfono** y salida **Voz_Clara_Altavoces**. Dentro de Voz Clara conserva seleccionados los dispositivos físicos.
5. Pulsa **Oírme: OFF** para pasar a **Oírme: ON** y monitorizar la señal procesada. Es un botón, separado del selector de salida. Usa auriculares. Puedes cambiar de altavoz durante la escucha.
6. Ajusta gate, compresor, panel de tono y volumen. El EQ de auriculares es independiente.

Para cambiar el micrófono, Hz o búfer, detén y reinicia el audio. Puedes cambiar el altavoz físico durante el funcionamiento. Al cerrar se guardan los controles, se retiran los dispositivos virtuales y se intenta restaurar la entrada/salida anterior si aún estaban seleccionados los de Voz Clara. La app debe permanecer abierta mientras usas sus dispositivos.

Si antes aparecía «null», cierra la app y repite el instalador Bazzite para recibir la corrección. La app prueba la conexión al audio del host y, si hace falta y las utilidades están disponibles en el host, el puente de Distrobox. La misma ruta se usa para enumerar, capturar y reproducir. No presenta una salida ficticia como altavoz: si no ve hardware muestra «Sin micrófonos/altavoces disponibles» y el error correspondiente. Comprueba también que los dispositivos aparezcan en Ajustes → Sonido de GNOME.

## Mezclador y protección de voz

La interfaz separa **Micrófono**, **Escritorio y auriculares** y **Rutas y protección**. Los ajustes de frecuencia, búfer y recuperación están en **Motor y ayuda**. Los medidores de canal muestran nivel RMS; las barras de reducción indican cuándo actúan los limitadores.

El micrófono tiene una protección final siempre activa, con techo seleccionable de **−12 a −1 dBFS**. Se aplica después de eliminar la componente continua, usa 5 ms de anticipación y no aumenta automáticamente la ganancia del ruido. El techo limita las muestras digitales a la salida de la app; no reconstruye una captura ya distorsionada ni garantiza los picos entre muestras de un DAC o la ganancia que aplique otra app después.

**Aplicar voz protegida** prepara compresor 3/10, techo −3 dBFS, 48 kHz / 512 muestras, gate desactivado, EQ plano, voz a 0 dB, salida a −6 dB y escucha/supresión OFF. Detiene el motor para aplicar el conjunto; después pulsa **Iniciar audio**. El techo queda guardado para la próxima sesión.

Se restablecen a ganancia unitaria los endpoints internos del micrófono para evitar una amplificación restaurada por el servidor. El vigilante corrige posteriores subidas sobre el 100 % de esos endpoints; no controla el volumen que una aplicación receptora añada por su cuenta ni modifica el micrófono físico.

## Saturación, cortes y eco

Pulsa **Restablecer audio seguro · sin escucha** para detener el motor y preparar 48 kHz / 512 muestras, gate desactivado, tono y EQ planos, supresión OFF y ganancias de −6 dB. Después pulsa **Iniciar audio**. Este botón conserva tus dispositivos y sustituye los controles de procesamiento; se guardan al cerrar.

Mantén **Oírme OFF** para no reproducir una copia retardada de tu voz. Con auriculares evitas que el sonido del altavoz vuelva acústicamente al micrófono. Desactiva también la monitorización de micrófono de OBS/Discord si está activa. Esta versión no incorpora cancelación de eco acústico ni controla la escucha directa del hardware.

Los limitadores del micrófono y de la salida reducen los picos sin aumentar el ruido entre frases. El indicador de protección muestra la reducción aplicada. Si aparece la advertencia **Entrada cerca de saturar**, baja la ganancia del micrófono o el volumen de entrada de Linux: una señal que ya llega distorsionada no se puede reconstruir con el volumen de la app. Si sigue habiendo cortes, prueba 1024 muestras. Más reserva mejora la tolerancia a carga a costa de más latencia, especialmente audible si activas Oírme.

## Supresión de ruido

Es un filtro de voz local basado en [RNNoise de Xiph](https://github.com/xiph/rnnoise), independiente del gate. Puede reducir ruido de fondo mientras hablas. No envía audio a servicios externos. El instalador incluye el motor mediante la dependencia [pyrnnoise](https://github.com/pengzhendong/pyrnnoise).

- **OFF:** conserva la señal original. Al apagar el filtro, una transición de unos 20 ms devuelve el audio sin el retardo añadido del filtro.
- **ON:** requiere **48000 Hz**. Al activarlo con el motor detenido, la frecuencia se ajusta automáticamente. Si ya estás usando otra frecuencia, detén primero el audio.
- **Potencia 0–100 %:** mezcla alineada del audio original y filtrado; no es una promesa del porcentaje de ruido eliminado. 0 % conserva el original con el retardo de la ruta activada; 100 % aplica RNNoise completo. Empieza con 70 % y ajusta escuchando tu voz.
- **Cambios en directo:** potencia y ON/OFF usan transiciones suaves. El filtro se calienta antes de entrar y mantiene acotadas sus colas; no acumula segundos de audio.

RNNoise trabaja en bloques de 10 ms. El modelo incluido tiene 20 ms de retardo, verificados por correlación en las pruebas; con la adaptación de bloques, la ruta activada añade aproximadamente 30 ms al micrófono, además del resto de latencias del sistema. La señal original de la mezcla se retrasa lo mismo para evitar coloración por desalineación. Reduce la potencia si percibes voz artificial o pérdida de consonantes; la calidad depende del ruido y el micrófono. No elimina todo tipo de sonidos ni sustituye una buena colocación del micrófono.

Orden de micrófono: supresión opcional → controles de voz existentes (tono, gate, compresor, ganancia) → protección contra componente continua y arranque suave → limitador final con anticipación → micrófono virtual. El gate mantiene la apertura durante pausas breves de 150 ms para no cortar sílabas suaves. El tono conserva su algoritmo; un limitador de picos evita el recorte duro después de la ganancia.

## Rutas sin realimentación

El micrófono físico siempre alimenta el micrófono virtual. El escritorio entra por el altavoz virtual, pasa por el EQ y sale al altavoz físico. Oírme agrega tu voz únicamente a esa salida; nunca envía el escritorio al micrófono virtual.

Las conexiones internas fijan su destino y desactivan el movimiento/fallback en PipeWire. Un vigilante detecta movimientos inesperados y silencia el procesamiento para evitar un bucle. El bus técnico de micrófono está marcado como interno/oculto; si alguna herramienta lo muestra, **no lo elijas como altavoz del sistema**. Usa **Voz_Clara_Altavoces**.

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

La app procesa bloques continuamente, sin grabar para reproducir después. El audio del escritorio y la escucha opcional de voz se mezclan antes del EQ de salida, con estados de filtro únicos. La cola de escucha se limita a dos bloques para evitar acumular retraso. Cada flujo solicita al menos 10 ms de captura y tres bloques de reserva de reproducción; el servidor puede adaptar esos valores. La supresión de ruido añade el retardo indicado arriba cuando está activada. El limitador final del micrófono añade siempre otros 5 ms.

**128 muestras a 48000 Hz son 2,67 ms por bloque, no 2,67 ms de latencia total.** El dispositivo, el servidor de audio y la aplicación receptora añaden retraso. No se garantiza latencia cero ni funcionamiento de tiempo real estricto. Para medir la latencia completa hace falta una prueba de retorno físico en Linux. Usa auriculares por cable o USB para reducir el retraso de monitorización.

La interfaz muestra tiempo de DSP por bloque y descartes de la cola de escucha. Si el procesamiento supera el tiempo disponible por bloque o escuchas cortes, aumenta el búfer a 512 o 1024. Estos indicadores no son una medición de latencia de extremo a extremo.

## Desarrollo y pruebas

Después de instalar dependencias:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Las pruebas cubren DSP, supresión RNNoise nativa, mezclas por porcentaje y su alineación temporal, continuidad de bloques, prevención de rutas hacia sí mismo y restauración de predeterminados. GitHub Actions también prueba audio del escritorio, EQ, Oírme y cambio de predeterminados con servidores PulseAudio/PipeWire aislados y dispositivos sintéticos. No sustituyen la validación con hardware.

Al informar un problema incluye distribución, PipeWire o PulseAudio, modelo de micrófono, salida de auriculares, frecuencia y búfer, y qué ocurre. Puedes proponer mejoras en Issues.

Detalles de controles, instalación y solución de problemas: [LEEME.md](LEEME.md). Cambios de cada versión: [CHANGELOG.md](CHANGELOG.md).

Inspirado en la sencillez de los controles de mezcladores de voz. Proyecto independiente, sin afiliación con VB-Audio; no utiliza su código, marca ni algoritmo Intellipan.

## Licencia

[MIT](LICENSE).
