# Cambios

## 0.4.0 — Mezclador y protección final

- Interfaz oscura en tres canales, faders, medidores RMS segmentados y sección Motor y ayuda.
- Techo de micrófono de −12 a −1 dBFS siempre activo, después del filtro de componente continua, con 5 ms de anticipación y recuperación progresiva.
- Preset Voz protegida con compresión suave, techo −3 dBFS y escucha OFF.
- Medidor del micrófono tomado a la salida de la cadena completa y visualización de reducción de picos.
- Normalización de ganancias restauradas y vigilancia de amplificación de los endpoints internos del micrófono; no se cambia la ganancia física.
- Sanitización de muestras no finitas y extremas antes de RNNoise, DSP y medidores; bloques vacíos seguros.
- Eventos de parada propios de cada sesión para evitar que un vigilante antiguo detenga una sesión nueva.
- Ajustes persistentes inválidos recuperados con valores seguros; los dispositivos recordados se conservan si faltan al cerrar.
- Pruebas de interfaz sin pantalla, anticipación y techo final; aislamiento de configuración, estado y descubrimiento de hardware en pruebas PipeWire.

## 0.3.1 — Estabilidad de audio

- Lecturas de reproducción alineadas a muestras completas, incluso con fragmentación en Distrobox.
- Reserva de reproducción de tres bloques con mínimo de 10 ms por bloque y valor inicial de 512 muestras para DSP.
- Limitadores de picos enlazados en estéreo en micrófono y salida, sin ganancia automática del ruido.
- Gate con mantenimiento de 150 ms para evitar cierres durante sílabas suaves.
- Ganancia, mute y EQ aplicados antes de arrancar los hilos; volumen inicial de reproducción explícito al 100 % para evitar restauraciones amplificadas.
- Aviso de saturación de entrada y medición de reducción de picos.
- Restablecimiento seguro sin escucha y explicación del eco de monitorización. No incluye cancelación de eco acústico.
- Restauración correcta del micrófono anterior si falla el cambio de salida predeterminada.

## 0.3.0 — Salida del sistema y supresión de ruido

- Altavoz virtual público Voz_Clara_Altavoces: audio del sistema → EQ/volumen → salida física.
- Micrófono virtual separado y bus técnico marcado como interno/oculto.
- Oírme ON/OFF agrega o retira solo la voz de la salida; el escritorio sigue sonando.
- Destinos fijados, sin movimiento/fallback de PipeWire, y vigilancia contra realimentación.
- Eliminación de componente continua y arranque suave en la salida de micrófono, manteniendo el gate y tono existentes.
- Botón para usar ambos dispositivos virtuales por defecto y restauración al cerrar.
- RNNoise local: control independiente ON/OFF y potencia 0–100 %, mezcla alineada y cambios suaves.
- Supresión a 48 kHz, con unos 30 ms adicionales de ruta cuando está activada y mezcla original/filtrada alineada con el retardo real del modelo.
- Pruebas de audio con servidores PulseAudio y PipeWire aislados en CI.

## 0.2.1 — Corrección de dispositivos

- Selectores visibles de micrófono y altavoz/auriculares en sus paneles.
- Oírme: un único botón ON/OFF; cambio de salida durante la escucha.
- Los nombres vacíos o null se sustituyen por el identificador real.
- Se excluyen monitores, el bus interno y salidas ficticias auto_null.
- En contenedores se prueban los sockets de audio del host y se comparte la conexión entre captura, salida virtual y auriculares.
- Si no hay dispositivos reales, la app muestra un error y no permite iniciar con null.

## Instalador Bazzite

- Instalación y actualización con un solo comando en Bazzite GNOME/KDE.
- Dependencias en Distrobox y acceso desde el menú de aplicaciones.
- Comprobación de conexión al audio antes de crear el acceso.
- Ruta preparada; pendiente validar instalación y audio en Bazzite real.

## 0.2.0 — 2026-10-18

- Una entrada física y un micrófono virtual para Linux.
- Gate, compresor, panel de graves/agudos, volumen y mute de micrófono.
- Mono activable y procesamiento estéreo con detección enlazada.
- Escucha directa con volumen y mute independientes y EQ de cinco bandas.
- Búferes pequeños solicitados al servidor y pipes sin búfer de Python.
- Cola limitada para que la escucha no bloquee la salida virtual.
- Ajustes persistentes e indicadores del tiempo de DSP.
- Pruebas automáticas e instrucciones de instalación y actualización.

Estado: experimental; pendiente validar audio y latencia con hardware Linux.
