# Cambios

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
