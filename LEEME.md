# Voz Clara Linux — manual

Versión 0.4.0. Una entrada física, un micrófono virtual y un altavoz virtual. El código es experimental: las pruebas automáticas no sustituyen la medición con tu hardware.

## Instalar y actualizar

En Bazzite GNOME/KDE ejecuta el comando único del [README](README.md). Instala las dependencias automáticamente en Distrobox y crea Voz Clara Linux en el menú. Cierra la app antes de repetir ese mismo comando para actualizar. No uses sudo ni las instrucciones de dnf de Fedora tradicional sobre el host Bazzite.

Las instrucciones manuales para Ubuntu/Debian, Fedora y Arch también están en el README. Conserva tu servidor PipeWire + pipewire-pulse o PulseAudio.

## Conectar los dispositivos

1. Dentro de Voz Clara elige el micrófono físico y el altavoz/auriculares físicos. Nunca selecciones un dispositivo de Voz Clara como su propia entrada o salida física.
2. Empieza con 48000 Hz / 512 muestras; si hay cortes, prueba 1024.
3. Pulsa Iniciar audio.
4. Pulsa Conectar a mis apps, o selecciona en GNOME entrada **Voz_Clara_Microfono** y salida **Voz_Clara_Altavoces**.
5. Enciende Oírme si deseas escuchar tu propia voz. OFF retira solo tu voz; el audio del escritorio sigue sonando.

El EQ de cinco bandas y el volumen de salida afectan al escritorio enviado al altavoz virtual y a la escucha de tu voz. No afectan al micrófono virtual. Si una aplicación tiene seleccionada directamente la salida física, su sonido evita el EQ.

La app debe permanecer abierta. Al detenerla se retiran los dispositivos virtuales y se intenta restaurar los predeterminados anteriores, siempre que aún estén seleccionados los de Voz Clara. No se cambia una elección posterior del usuario hacia otro dispositivo.

## Controles del micrófono

- **Panel de tono:** izquierda realza graves y reduce agudos; derecha hace lo contrario. Arriba aumenta ambas bandas y abajo las reduce. Doble clic centra el punto. Control propio, sin usar el algoritmo Intellipan.
- **Gate:** −80 desactiva el gate. Sube el umbral hasta ocultar el ruido entre frases. El gate no elimina ruido durante la voz.
- **Comp:** 0 desactiva el compresor. 1–10 aumenta su intensidad. Ataque 5 ms, liberación 80 ms y sin ganancia automática.
- **Mono:** promedia izquierdo y derecho y coloca la misma voz en ambos canales. Desactivado conserva estéreo.
- **Volumen y silencio del micrófono:** solo afectan al micrófono virtual y a su escucha.

El gate añade 150 ms de mantenimiento para preservar pausas breves de voz. El tono conserva su procesamiento y se añade un limitador de picos después de la ganancia. Se añade protección de componente continua y un arranque suave al final de la ruta del micrófono.

## Supresión de ruido de fondo

Control independiente con motor RNNoise local. No transmite audio a la nube. Puede reducir ruido mientras hablas; no elimina todos los sonidos.

Actívalo a 48000 Hz y empieza con potencia 70 %. El porcentaje controla la mezcla alineada original/filtrada: 0 % conserva el original y 100 % aplica el filtrado completo. No indica el porcentaje real de ruido eliminado. Si notas voz artificial, baja la potencia.

ON/OFF y potencia tienen transiciones suaves. El filtro acumula bloques nativos de 480 muestras y mantiene acotadas sus colas. Al activarse se calienta antes de entrar. La ruta ON añade aproximadamente 30 ms de filtrado y adaptación, aunque el porcentaje esté en 0. La mezcla original/filtrada compensa el retardo de 20 ms del modelo. OFF vuelve al audio sin ese retardo tras la transición.

Si el motor ya está funcionando a 44100 o 96000 Hz, detén el audio y cambia a 48000 antes de activar RNNoise. Si activas el control con el motor detenido, la frecuencia se ajusta automáticamente.

## Evitar bucles

La captura física siempre apunta al micrófono seleccionado. El audio del escritorio nunca se envía al micrófono virtual. Los destinos internos están fijados y se desactiva el movimiento/fallback de PipeWire. Una vigilancia adicional detiene y silencia si descubre una ruta movida hacia otro dispositivo.

El bus de micrófono se marca como interno/oculto. Algunas herramientas técnicas pueden mostrarlo como **Voz_Clara_Interno_NO_SELECCIONAR**: no lo elijas como salida. Usa **Voz_Clara_Altavoces**. Actualiza con la versión anterior cerrada; si hubo un cierre abrupto, sus módulos pueden seguir cargados. No descargues módulos ajenos. Un reinicio de la sesión retira los módulos temporales.

## Latencia y diagnóstico

128 muestras a 48000 Hz son 2,67 ms por bloque, no la latencia total. La frecuencia y el búfer se solicitan al servidor; no cambian el quantum global de PipeWire ni obligan al hardware a esa frecuencia. La supresión añade su retardo, y aplicaciones de llamadas/Bluetooth pueden añadir otros. Usa auriculares por cable o USB y mide un bucle físico si necesitas conocer la latencia completa.

La interfaz muestra tiempo de DSP del último bloque y descartes de la cola de escucha. Si hay cortes, aumenta el búfer. Una ganancia o EQ excesivos pueden producir recorte; baja los niveles. Para que los cambios de dispositivo de entrada/Hz/búfer surtan efecto, detén y reinicia el audio.

Si no aparecen dispositivos, comprueba Ajustes → Sonido de GNOME y pulsa Actualizar dispositivos con el audio detenido. La app no acepta salidas ficticias null. Si falla, copia el mensaje inferior de la ventana para diagnosticar la conexión.

## Pruebas

Con las dependencias instaladas:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

La prueba de servidores de audio está aislada y se activa expresamente en CI con VOZ_CLARA_AUDIO_TEST=1. Usa dispositivos sintéticos y no prueba hardware real. Consulta [THIRD_PARTY.md](THIRD_PARTY.md) para los componentes de terceros.

## Mezclador 0.4.0

En Rutas y protección puedes fijar el techo final del micrófono entre −12 y −1 dBFS; siempre permanece activo y añade 5 ms de anticipación. «Aplicar voz protegida» prepara compresión suave, techo −3 dBFS y escucha apagada. Frecuencia, búfer y restablecimiento están en Motor y ayuda. El techo actúa después del filtro de componente continua y no puede recuperar una captura que ya llegue distorsionada.
