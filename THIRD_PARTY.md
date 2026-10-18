# Componentes de terceros

El código de Voz Clara Linux tiene licencia MIT. Las dependencias conservan sus propias licencias:

- [RNNoise](https://github.com/xiph/rnnoise): motor de supresión de ruido de Xiph, licencia BSD de tres cláusulas, según su archivo COPYING.
- [pyrnnoise](https://github.com/pengzhendong/pyrnnoise): distribución de los binarios RNNoise utilizados por el adaptador, licencia Apache 2.0 de sus bindings. Se instala como dependencia, no se copia su implementación al proyecto.
- PySide6 / Qt: licencias indicadas por el proyecto Qt para sus paquetes.
- NumPy y SciPy: licencias BSD de sus respectivos proyectos.

La instalación mediante pip conserva los metadatos y archivos de licencia de las distribuciones instaladas. El repositorio no incluye binarios de estas dependencias.
