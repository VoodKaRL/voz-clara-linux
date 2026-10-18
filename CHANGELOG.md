# Cambios

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
