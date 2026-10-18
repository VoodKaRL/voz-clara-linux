import sys
from PySide6.QtCore import Qt, QTimer, QSettings, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSlider, QGroupBox, QProgressBar, QMessageBox, QScrollArea)
from audio import Engine, devices, configure_audio


class TonePad(QWidget):
    def __init__(self, changed):
        super().__init__()
        self.x = self.y = 0.0
        self.changed = changed
        self.setMinimumSize(240, 210)
        self.setToolTip('Izquierda: graves · Derecha: agudos\nArriba: más color · Doble clic: neutro')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#14232c'))
        p.setPen(QPen(QColor('#304650'), 1))
        for t in (.25, .5, .75):
            p.drawLine(int(t*self.width()), 0, int(t*self.width()), self.height())
            p.drawLine(0, int(t*self.height()), self.width(), int(t*self.height()))
        p.setPen(QColor('#9fb6c1'))
        p.drawText(12, self.height()-12, 'GRAVES')
        p.drawText(self.width()-68, self.height()-12, 'AGUDOS')
        p.drawText(12, 22, 'COLOR')
        pos = QPointF((self.x+1)/2*(self.width()-28)+14, (1-self.y)/2*(self.height()-28)+14)
        p.setBrush(QColor('#77e0ba'))
        p.setPen(QPen(QColor('#ccffeb'), 2))
        p.drawEllipse(pos, 9, 9)

    def mousePressEvent(self, event):
        self.move_point(event)

    def mouseMoveEvent(self, event):
        self.move_point(event)

    def move_point(self, event):
        self.x = max(-1, min(1, 2*(event.position().x()-14)/(self.width()-28)-1))
        self.y = max(-1, min(1, 1-2*(event.position().y()-14)/(self.height()-28)))
        self.changed()
        self.update()

    def mouseDoubleClickEvent(self, event):
        self.x = self.y = 0
        self.changed()
        self.update()


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = Engine()
        self.settings = QSettings('VozClara', 'VozClara')
        self.setWindowTitle('Voz Clara 0.3.0 · Micrófono y altavoces')
        self.resize(1000, 840)
        root = QVBoxLayout(self)
        title = QLabel('VOZ CLARA  /  LINUX')
        title.setStyleSheet('font-size:23px; font-weight:700; color:#77e0ba')
        root.addWidget(title)
        root.addWidget(QLabel('Un micrófono. Tu voz, a tu manera.'))
        row = QHBoxLayout()
        root.addLayout(row)
        strip = QGroupBox('MICRÓFONO · Entrada')
        left = QVBoxLayout(strip)
        left.addWidget(QLabel('Escoger micrófono'))
        self.source = QComboBox()
        self.source.setMinimumContentsLength(16)
        self.source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        left.addWidget(self.source)
        left.addWidget(QLabel('PANEL DE VOZ'))
        self.pad = TonePad(self.sync)
        left.addWidget(self.pad)
        dynamics = QHBoxLayout()
        comp_box = QVBoxLayout()
        self.comp_label = QLabel()
        comp_box.addWidget(self.comp_label)
        self.comp = QSlider(Qt.Orientation.Horizontal)
        self.comp.setRange(0, 10)
        self.comp.setValue(int(self.settings.value('comp', 0)))
        self.comp.valueChanged.connect(self.sync)
        comp_box.addWidget(self.comp)
        dynamics.addLayout(comp_box)
        gate_box = QVBoxLayout()
        self.gate_label = QLabel()
        gate_box.addWidget(self.gate_label)
        self.gate = QSlider(Qt.Orientation.Horizontal)
        self.gate.setRange(-80, -10)
        self.gate.setValue(int(self.settings.value('gate', -45)))
        self.gate.valueChanged.connect(self.sync)
        gate_box.addWidget(self.gate)
        dynamics.addLayout(gate_box)
        left.addLayout(dynamics)
        left.addWidget(QLabel('−80 = desactivado · Sube hasta ocultar el ruido'))
        faders = QHBoxLayout()
        self.meter = QProgressBar()
        self.meter.setOrientation(Qt.Orientation.Vertical)
        self.meter.setRange(0, 90)
        self.meter.setTextVisible(False)
        self.meter.setFixedWidth(24)
        self.gain = QSlider(Qt.Orientation.Vertical)
        self.gain.setRange(-60, 12)
        self.gain.setValue(int(self.settings.value('gain', 0)))
        self.gain.valueChanged.connect(self.sync)
        self.gain_label = QLabel()
        faders.addWidget(self.meter)
        faders.addWidget(self.gain)
        faders.addWidget(self.gain_label)
        left.addLayout(faders)
        self.mute = QPushButton('Silenciar')
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self.sync)
        left.addWidget(self.mute)
        self.mono = QPushButton('MONO · Centrar la voz')
        self.mono.setCheckable(True)
        self.mono.setChecked(str(self.settings.value('mono', 'true')).lower() == 'true')
        self.mono.toggled.connect(self.sync)
        left.addWidget(self.mono)
        row.addWidget(strip, 3)
        headphones_box = QGroupBox('ALTAVOCES / AURICULARES · Salida')
        hp = QVBoxLayout(headphones_box)
        hp.addWidget(QLabel('Escoger altavoz / auriculares'))
        self.sink = QComboBox()
        self.sink.setMinimumContentsLength(16)
        self.sink.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.sink.currentIndexChanged.connect(self.output_changed)
        hp.addWidget(self.sink)
        self.listen = QPushButton('Oírme: OFF')
        self.listen.setCheckable(True)
        self.listen.setEnabled(False)
        self.listen.toggled.connect(self.monitor)
        hp.addWidget(self.listen)
        hp.addWidget(QLabel('ECUALIZADOR · ±12 dB'))
        eq_row = QHBoxLayout()
        self.eq = []
        self.eq_labels = []
        for i, frequency in enumerate(('80', '250', '1k', '4k', '12k')):
            band = QVBoxLayout()
            label = QLabel('0 dB')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            band.addWidget(label)
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setRange(-12, 12)
            slider.setValue(int(self.settings.value(f'eq{i}', 0)))
            slider.valueChanged.connect(self.sync)
            band.addWidget(slider, 1, Qt.AlignmentFlag.AlignHCenter)
            band.addWidget(QLabel(frequency + ' Hz'))
            self.eq.append(slider)
            self.eq_labels.append(label)
            eq_row.addLayout(band)
        hp.addLayout(eq_row, 1)
        reset = QPushButton('EQ plano')
        reset.clicked.connect(self.reset_eq)
        hp.addWidget(reset)
        self.hp_label = QLabel()
        hp.addWidget(self.hp_label)
        hp_row = QHBoxLayout()
        self.hp_meter = QProgressBar()
        self.hp_meter.setOrientation(Qt.Orientation.Vertical)
        self.hp_meter.setRange(0, 90)
        self.hp_meter.setTextVisible(False)
        self.hp_meter.setFixedWidth(24)
        hp_row.addWidget(self.hp_meter)
        self.hp_gain = QSlider(Qt.Orientation.Vertical)
        self.hp_gain.setRange(-60, 12)
        self.hp_gain.setValue(int(self.settings.value('hp_gain', -6)))
        self.hp_gain.valueChanged.connect(self.sync)
        hp_row.addWidget(self.hp_gain)
        hp.addLayout(hp_row, 1)
        self.hp_mute = QPushButton('Silenciar auriculares')
        self.hp_mute.setCheckable(True)
        self.hp_mute.toggled.connect(self.sync)
        hp.addWidget(self.hp_mute)
        note = QLabel('Volumen y EQ para el audio enviado a Voz Clara Altavoces y tu voz si activas Oírme. El micrófono virtual conserva sus propios ajustes.')
        note.setWordWrap(True)
        hp.addWidget(note)
        row.addWidget(headphones_box, 2)
        side_widget = QWidget()
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(0, 0, 0, 0)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setMinimumWidth(260)
        side_scroll.setStyleSheet('QScrollArea { border: 0; }')
        side_scroll.setWidget(side_widget)
        row.addWidget(side_scroll, 2)
        box = QGroupBox('AJUSTES DE AUDIO')
        form = QVBoxLayout(box)
        form.addWidget(QLabel('Frecuencia de procesamiento'))
        self.rate = QComboBox()
        self.rate.addItems(['44100', '48000', '96000'])
        self.rate.setCurrentText(str(self.settings.value('rate', '48000')))
        form.addWidget(self.rate)
        form.addWidget(QLabel('Búfer solicitado · muestras'))
        self.buffer = QComboBox()
        self.buffer.addItems(['128', '256', '512', '1024', '2048'])
        self.buffer.setCurrentText(str(self.settings.value('buffer', '128')))
        form.addWidget(self.buffer)
        hint = QLabel('El servidor de audio puede adaptar la frecuencia y latencia del dispositivo.')
        hint.setWordWrap(True)
        form.addWidget(hint)
        self.latency_label = QLabel()
        self.latency_label.setWordWrap(True)
        form.addWidget(self.latency_label)
        self.rate.currentTextChanged.connect(self.update_latency)
        self.buffer.currentTextChanged.connect(self.update_latency)
        self.update_latency()
        self.runtime_label = QLabel('Procesamiento: detenido')
        self.runtime_label.setWordWrap(True)
        form.addWidget(self.runtime_label)
        tip = QLabel('Usa auriculares para evitar acoples. La escucha incluye gate, tono y ganancia.')
        tip.setWordWrap(True)
        form.addWidget(tip)
        side.addWidget(box)
        noise_box = QGroupBox('SUPRESIÓN DE RUIDO · Micrófono')
        noise_form = QVBoxLayout(noise_box)
        self.noise_button = QPushButton('Supresión de ruido: OFF')
        self.noise_button.setCheckable(True)
        self.noise_button.setChecked(str(self.settings.value('noise_enabled', 'false')).lower() == 'true')
        self.noise_button.toggled.connect(self.toggle_noise)
        noise_form.addWidget(self.noise_button)
        self.noise_strength_label = QLabel()
        noise_form.addWidget(self.noise_strength_label)
        self.noise_strength = QSlider(Qt.Orientation.Horizontal)
        self.noise_strength.setRange(0, 100)
        self.noise_strength.setValue(int(self.settings.value('noise_strength', 70)))
        self.noise_strength.valueChanged.connect(self.sync)
        noise_form.addWidget(self.noise_strength)
        noise_hint = QLabel('RNNoise reduce ruido mientras hablas. 0 % conserva el audio; 100 % aplica todo el filtro. Usa 48.000 Hz; añade latencia de filtrado.')
        noise_hint.setWordWrap(True)
        noise_form.addWidget(noise_hint)
        side.addWidget(noise_box)
        self.refresh = QPushButton('Actualizar dispositivos')
        self.refresh.clicked.connect(self.load_devices)
        side.addWidget(self.refresh)
        self.start = QPushButton('Iniciar audio')
        self.start.setCheckable(True)
        self.start.toggled.connect(self.toggle)
        side.addWidget(self.start)
        self.defaults = QPushButton('Usar Voz Clara por defecto')
        self.defaults.setEnabled(False)
        self.defaults.clicked.connect(self.use_defaults)
        side.addWidget(self.defaults)
        info = QLabel('Dispositivos del sistema:\n\nEntrada: Voz_Clara_Microfono\nSalida: Voz_Clara_Altavoces\n\nDentro de esta app elige siempre el micrófono y altavoz físicos. Mantén la app abierta.')
        info.setWordWrap(True)
        side.addWidget(info)
        side.addStretch()
        self.status = QLabel('Listo para iniciar')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.pad.x = float(self.settings.value('x', 0))
        self.pad.y = float(self.settings.value('y', 0))
        self.toggle_noise(self.noise_button.isChecked())
        self.sync()
        self.load_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(60)

    def load_devices(self):
        previous = {key: combo.currentData() or self.settings.value(key, '')
            for combo, key in ((self.source, 'source'), (self.sink, 'sink'))}
        for combo in (self.source, self.sink):
            combo.blockSignals(True)
            combo.clear()
        try:
            configure_audio()
            for combo, kind, key in ((self.source, 'sources', 'source'), (self.sink, 'sinks', 'sink')):
                for name, description in devices(kind):
                    combo.addItem(description, name)
                idx = combo.findData(previous[key])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self.status.setText('Escoge micrófono y altavoz físicos. Inicia el audio y selecciona Voz Clara por defecto.'
                if self.source.count() and self.sink.count() else
                'Faltan dispositivos: revisa el micrófono y la salida en los ajustes de sonido de GNOME y pulsa Actualizar dispositivos.')
        except Exception as exc:
            self.status.setText(f'No se pudo consultar el audio: {exc}')
        finally:
            for combo, label in ((self.source, 'Sin micrófonos disponibles'), (self.sink, 'Sin altavoces disponibles')):
                if not combo.count():
                    combo.addItem(label, None)
                    combo.model().item(0).setEnabled(False)
                combo.blockSignals(False)
            self.start.setEnabled(bool(self.source.currentData()) and bool(self.sink.currentData()))
            self.listen.setEnabled(self.start.isChecked() and bool(self.sink.currentData()))

    def sync(self):
        p = self.engine.processor
        p.gate_db = self.gate.value()
        p.gain_db = self.gain.value()
        p.x, p.y = self.pad.x, self.pad.y
        p.muted = self.mute.isChecked()
        p.mono = self.mono.isChecked()
        p.comp = self.comp.value()
        self.comp_label.setText(f'COMP · {p.comp}/10' if p.comp else 'COMP · Apagado')
        self.engine.headphones.gains = tuple(slider.value() for slider in self.eq)
        self.engine.headphones.volume_db = self.hp_gain.value()
        self.engine.headphones.muted = self.hp_mute.isChecked()
        self.engine.noise.strength = self.noise_strength.value()
        self.noise_strength_label.setText(f'Potencia · {self.noise_strength.value()} %')
        self.hp_label.setText(f'Volumen auriculares · {self.hp_gain.value():+d} dB')
        for slider, label in zip(self.eq, self.eq_labels):
            label.setText(f'{slider.value():+d} dB')
        self.gate_label.setText(f'GATE · {p.gate_db} dBFS' if p.gate_db > -80 else 'GATE · Desactivado')
        self.gain_label.setText(f'{p.gain_db:+d} dB\nVolumen micrófono')

    def reset_eq(self):
        for slider in self.eq:
            slider.setValue(0)

    def toggle_noise(self, enabled):
        running = hasattr(self, 'start') and self.start.isChecked()
        try:
            if enabled and self.rate.currentText() != '48000':
                if running:
                    raise RuntimeError('Detén el audio y selecciona 48000 Hz para activar la supresión de ruido.')
                self.rate.setCurrentText('48000')
            if running:
                self.engine.noise.set_enabled(enabled)
        except Exception as exc:
            self.noise_button.blockSignals(True)
            self.noise_button.setChecked(False)
            self.noise_button.blockSignals(False)
            enabled = False
            QMessageBox.warning(self, 'Supresión de ruido', str(exc))
        self.noise_button.setText('Supresión de ruido: ON' if enabled else 'Supresión de ruido: OFF')
        self.noise_strength.setEnabled(enabled)
        self.rate.setEnabled(not running and not enabled)
        self.update_latency()

    def update_latency(self):
        duration = int(self.buffer.currentText())/int(self.rate.currentText())*1000
        self.latency_label.setText(f'Bloque: {duration:.2f} ms. Búfer solicitado por flujo: {duration:.2f} ms. '
            'No es la latencia total medida. Si hay cortes, prueba 256 o 512 muestras.' +
            (' Supresión ON: aproximadamente 30 ms adicionales de filtrado y adaptación.'
                if hasattr(self, 'noise_button') and self.noise_button.isChecked() else ''))

    def toggle(self, enabled):
        if enabled:
            try:
                if not self.source.currentData():
                    raise RuntimeError('Selecciona un micrófono disponible.')
                if not self.sink.currentData():
                    raise RuntimeError('Selecciona un altavoz o unos auriculares físicos.')
                self.engine.start(self.source.currentData(), self.sink.currentData(), int(self.rate.currentText()), int(self.buffer.currentText()),
                    self.noise_button.isChecked(), self.noise_strength.value())
                self.sync()
                self.status.setText('Activo · Voz_Clara_Microfono para entrada y Voz_Clara_Altavoces para salida del sistema.')
            except Exception as exc:
                self.start.setChecked(False)
                QMessageBox.warning(self, 'No se pudo iniciar', str(exc))
                return
        else:
            self.listen.setChecked(False)
            self.engine.stop()
            self.status.setText('Audio detenido · Se retiraron los dispositivos virtuales.')
        self.start.setText('Detener audio' if enabled else 'Iniciar audio')
        self.defaults.setEnabled(enabled)
        self.listen.setEnabled(enabled and bool(self.sink.currentData()))
        for widget in (self.source, self.rate, self.buffer, self.refresh):
            widget.setEnabled(not enabled)
        self.rate.setEnabled(not enabled and not self.noise_button.isChecked())

    def monitor(self, enabled):
        try:
            self.engine.monitor(enabled, self.sink.currentData())
            self.listen.setText('Oírme: ON' if enabled else 'Oírme: OFF')
        except Exception as exc:
            self.listen.blockSignals(True)
            self.listen.setChecked(False)
            self.listen.setText('Oírme: OFF')
            self.listen.blockSignals(False)
            QMessageBox.warning(self, 'Escucha', str(exc))

    def output_changed(self):
        if hasattr(self, 'start') and self.start.isChecked() and self.sink.currentData():
            try:
                self.engine.set_output(self.sink.currentData())
            except Exception as exc:
                self.sink.blockSignals(True)
                index = self.sink.findData(self.engine.sink)
                if index >= 0:
                    self.sink.setCurrentIndex(index)
                self.sink.blockSignals(False)
                QMessageBox.warning(self, 'Salida de audio', str(exc))

    def use_defaults(self):
        try:
            self.engine.use_as_defaults()
            self.status.setText('Voz Clara es la entrada y salida predeterminada. Oírme solo activa tu voz; la salida del sistema sigue funcionando con OFF.')
        except Exception as exc:
            QMessageBox.warning(self, 'Dispositivos predeterminados', str(exc))

    def tick(self):
        self.meter.setValue(int(max(0, self.engine.processor.output_db+90)) if self.start.isChecked() else 0)
        self.hp_meter.setValue(int(max(0, self.engine.headphones.output_db+90)) if self.start.isChecked() else 0)
        if self.start.isChecked():
            deadline = self.engine.frames/self.engine.rate*1000
            self.runtime_label.setText(f'DSP del último bloque: {self.engine.processing_ms:.2f} ms / {deadline:.2f} ms disponibles. '
                f'Bloques de escucha descartados: {self.engine.dropped}.')
        else:
            self.runtime_label.setText('Procesamiento: detenido')
        if self.engine.monitor_error:
            message = self.engine.monitor_error
            self.engine.monitor_error = ''
            self.listen.setChecked(False)
            self.status.setText(message + ' · El micrófono virtual sigue activo.')
        if self.engine.error:
            error = self.engine.error
            self.engine.error = ''
            self.start.setChecked(False)
            self.status.setText(f'Audio detenido: {error}')

    def closeEvent(self, event):
        self.engine.stop()
        for key, value in dict(gate=self.gate.value(), gain=self.gain.value(), x=self.pad.x, y=self.pad.y,
                comp=self.comp.value(), mono=self.mono.isChecked(), hp_gain=self.hp_gain.value(),
                noise_enabled=self.noise_button.isChecked(), noise_strength=self.noise_strength.value(),
                rate=self.rate.currentText(), buffer=self.buffer.currentText(), source=self.source.currentData(), sink=self.sink.currentData()).items():
            self.settings.setValue(key, value)
        for i, slider in enumerate(self.eq):
            self.settings.setValue(f'eq{i}', slider.value())
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet('''QWidget { background:#202f39; color:#d9e7ed; font-size:13px; }
        QGroupBox { border:1px solid #46606e; border-radius:10px; margin-top:14px; padding:14px 8px 8px; }
        QGroupBox::title { color:#9fb6c1; subcontrol-origin:margin; left:12px; }
        QPushButton,QComboBox { padding:9px; border:1px solid #527080; border-radius:6px; background:#2c4350; }
        QPushButton:checked { background:#367e68; border-color:#77e0ba; }
        QWidget:disabled { color:#71828b; }
        QSlider::groove:vertical { background:#14232c; width:12px; border-radius:6px; }
        QSlider::handle:vertical { background:#77e0ba; height:22px; margin:0 -9px; border-radius:6px; }
        QSlider::groove:horizontal { background:#14232c; height:8px; }
        QSlider::handle:horizontal { background:#77e0ba; width:16px; margin:-5px 0; border-radius:6px; }
        QProgressBar { background:#14232c; border:0; } QProgressBar::chunk { background:#77e0ba; }''')
    window = Window()
    window.show()
    sys.exit(app.exec())
