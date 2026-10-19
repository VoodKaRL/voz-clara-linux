import sys
import math
from PySide6.QtCore import Qt, QTimer, QSettings, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSlider, QGroupBox, QProgressBar, QMessageBox, QScrollArea, QFrame, QTabWidget)
from audio import Engine, devices, configure_audio
from ui import STYLE, LevelMeter


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
        self.setObjectName('window')
        self.setStyleSheet(STYLE)
        self.setWindowTitle('Voz Clara 0.4.0 · Mezclador')
        self.resize(1220, 900)
        self.setMinimumSize(880, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 14)
        root.setSpacing(14)
        header = QHBoxLayout()
        branding = QVBoxLayout()
        branding.setSpacing(1)
        brand = QLabel('VOZ CLARA')
        brand.setObjectName('brand')
        branding.addWidget(brand)
        subtitle = QLabel('MEZCLADOR DE VOZ  /  LINUX')
        subtitle.setObjectName('section')
        branding.addWidget(subtitle)
        header.addLayout(branding)
        header.addStretch()
        self.engine_badge = QLabel('●  MOTOR DETENIDO')
        self.engine_badge.setObjectName('engineBadge')
        header.addWidget(self.engine_badge)
        self.defaults = QPushButton('Conectar a mis apps')
        self.defaults.setToolTip('Usar Voz Clara como entrada y salida predeterminada de Linux')
        self.defaults.setEnabled(False)
        self.defaults.clicked.connect(self.use_defaults)
        header.addWidget(self.defaults)
        self.start = QPushButton('Iniciar audio')
        self.start.setObjectName('primary')
        self.start.setCheckable(True)
        self.start.toggled.connect(self.toggle)
        header.addWidget(self.start)
        root.addLayout(header)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        mixer_scroll = QScrollArea()
        mixer_scroll.setWidgetResizable(True)
        mixer = QWidget()
        mixer.setObjectName('page')
        mixer.setMinimumWidth(1030)
        channels = QHBoxLayout(mixer)
        channels.setContentsMargins(0, 14, 0, 0)
        channels.setSpacing(14)
        mixer_scroll.setWidget(mixer)
        tabs.addTab(mixer_scroll, 'Mezclador')

        def card(parent, number, title, subtitle):
            frame = QFrame()
            frame.setObjectName('card')
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(8)
            label = QLabel(number)
            label.setObjectName('section')
            layout.addWidget(label)
            label = QLabel(title)
            label.setObjectName('channel')
            layout.addWidget(label)
            label = QLabel(subtitle)
            label.setObjectName('muted')
            label.setWordWrap(True)
            layout.addWidget(label)
            parent.addWidget(frame)
            return layout

        def section(layout, text):
            label = QLabel(text)
            label.setObjectName('section')
            layout.addWidget(label)

        def slider(vertical, lo, hi, value):
            result = QSlider(Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal)
            result.setRange(lo, hi)
            result.setValue(value)
            result.valueChanged.connect(self.sync)
            return result

        def combo():
            result = QComboBox()
            result.setMinimumContentsLength(14)
            result.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            return result

        left = card(channels, '01 / ENTRADA', 'Micrófono', 'Tu voz → micrófono virtual')
        self.source = combo()
        left.addWidget(self.source)
        section(left, 'COLOR DE VOZ')
        self.pad = TonePad(self.sync)
        self.pad.setMinimumSize(190, 105)
        self.pad.setMaximumHeight(120)
        left.addWidget(self.pad)
        dynamics = QHBoxLayout()
        for key, lo, hi, default in (('comp', 0, 10, 0), ('gate', -80, -10, -55)):
            column = QVBoxLayout()
            label = QLabel()
            setattr(self, key+'_label', label)
            column.addWidget(label)
            control = slider(False, lo, hi, self.number_setting(key, default, lo, hi))
            setattr(self, key, control)
            column.addWidget(control)
            dynamics.addLayout(column)
        left.addLayout(dynamics)
        self.noise_button = QPushButton('Supresión de ruido: OFF')
        self.noise_button.setCheckable(True)
        self.noise_button.setChecked(str(self.settings.value('noise_enabled', 'false')).lower() == 'true')
        self.noise_button.toggled.connect(self.toggle_noise)
        left.addWidget(self.noise_button)
        self.noise_strength_label = QLabel()
        left.addWidget(self.noise_strength_label)
        self.noise_strength = slider(False, 0, 100, self.number_setting('noise_strength', 70, 0, 100))
        left.addWidget(self.noise_strength)
        left.addStretch()
        self.gain_label = QLabel()
        self.gain_label.setObjectName('faderValue')
        left.addWidget(self.gain_label, 0, Qt.AlignmentFlag.AlignHCenter)
        faders = QHBoxLayout()
        faders.addStretch()
        self.meter = LevelMeter()
        faders.addWidget(self.meter)
        self.gain = slider(True, -60, 12, self.number_setting('gain', 0, -60, 12))
        self.gain.setMinimumHeight(120)
        faders.addWidget(self.gain)
        faders.addStretch()
        left.addLayout(faders, 1)
        switches = QHBoxLayout()
        self.mute = QPushButton('Silenciar')
        self.mute.setObjectName('mute')
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self.sync)
        switches.addWidget(self.mute)
        self.mono = QPushButton('Mono')
        self.mono.setCheckable(True)
        self.mono.setChecked(str(self.settings.value('mono', 'true')).lower() == 'true')
        self.mono.toggled.connect(self.sync)
        switches.addWidget(self.mono)
        left.addLayout(switches)

        hp = card(channels, '02 / SALIDA', 'Escritorio y auriculares', 'Audio del sistema → salida física')
        self.sink = combo()
        self.sink.currentIndexChanged.connect(self.output_changed)
        hp.addWidget(self.sink)
        section(hp, 'ECUALIZADOR DE SALIDA')
        eq_row = QHBoxLayout()
        self.eq, self.eq_labels = [], []
        for i, frequency in enumerate(('80', '250', '1k', '4k', '12k')):
            band = QVBoxLayout()
            label = QLabel('0 dB')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            band.addWidget(label)
            control = slider(True, -12, 12, self.number_setting(f'eq{i}', 0, -12, 12))
            control.setMinimumHeight(125)
            band.addWidget(control, 1, Qt.AlignmentFlag.AlignHCenter)
            band.addWidget(QLabel(frequency+' Hz'), 0, Qt.AlignmentFlag.AlignHCenter)
            self.eq.append(control)
            self.eq_labels.append(label)
            eq_row.addLayout(band)
        hp.addLayout(eq_row)
        reset = QPushButton('Restablecer EQ')
        reset.clicked.connect(self.reset_eq)
        hp.addWidget(reset)
        note = QLabel('El EQ afecta la salida. Tu micrófono virtual conserva su mezcla independiente.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        hp.addWidget(note)
        hp.addStretch()
        self.hp_label = QLabel()
        self.hp_label.setObjectName('faderValue')
        hp.addWidget(self.hp_label, 0, Qt.AlignmentFlag.AlignHCenter)
        faders = QHBoxLayout()
        faders.addStretch()
        self.hp_meter = LevelMeter()
        faders.addWidget(self.hp_meter)
        self.hp_gain = slider(True, -60, 12, self.number_setting('hp_gain', -6, -60, 12))
        self.hp_gain.setMinimumHeight(120)
        faders.addWidget(self.hp_gain)
        faders.addStretch()
        hp.addLayout(faders, 1)
        self.hp_mute = QPushButton('Silenciar salida')
        self.hp_mute.setObjectName('mute')
        self.hp_mute.setCheckable(True)
        self.hp_mute.toggled.connect(self.sync)
        hp.addWidget(self.hp_mute)

        bus = card(channels, '03 / CONTROL', 'Rutas y protección', 'Una voz limpia, sin duplicarla')
        badge = QLabel('●  LIMITADOR SIEMPRE ACTIVO')
        badge.setObjectName('badge')
        bus.addWidget(badge)
        self.ceiling_label = QLabel()
        bus.addWidget(self.ceiling_label)
        self.ceiling = slider(False, -12, -1, self.number_setting('ceiling', -1, -12, -1))
        bus.addWidget(self.ceiling)
        info = QLabel('El techo se aplica al final del micrófono. Anticipación de 5 ms para controlar picos repentinos.')
        info.setObjectName('muted')
        info.setWordWrap(True)
        bus.addWidget(info)
        section(bus, 'REDUCCIÓN DE PICOS')
        self.mic_reduction_label = QLabel('Micrófono · 0.0 dB')
        bus.addWidget(self.mic_reduction_label)
        self.mic_reduction = QProgressBar()
        self.mic_reduction.setRange(0, 360)
        self.mic_reduction.setTextVisible(False)
        self.mic_reduction.setFixedHeight(7)
        bus.addWidget(self.mic_reduction)
        self.hp_reduction_label = QLabel('Salida · 0.0 dB')
        bus.addWidget(self.hp_reduction_label)
        self.hp_reduction = QProgressBar()
        self.hp_reduction.setRange(0, 360)
        self.hp_reduction.setTextVisible(False)
        self.hp_reduction.setFixedHeight(7)
        bus.addWidget(self.hp_reduction)
        self.input_warning = QLabel('Entrada física sin alertas')
        self.input_warning.setObjectName('muted')
        self.input_warning.setWordWrap(True)
        bus.addWidget(self.input_warning)
        section(bus, 'ESCUCHA DE TU VOZ')
        self.listen = QPushButton('Oírme: OFF')
        self.listen.setCheckable(True)
        self.listen.setEnabled(False)
        self.listen.setToolTip('Activa una copia retardada de tu voz. Déjalo OFF para evitar ese eco.')
        self.listen.toggled.connect(self.monitor)
        bus.addWidget(self.listen)
        note = QLabel('OFF evita la copia retardada de tu voz. Con altavoces, usa auriculares para evitar eco acústico.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        bus.addWidget(note)
        section(bus, 'DISPOSITIVOS PARA TUS APPS')
        info = QLabel('ENTRADA  /  Voz_Clara_Microfono\n\nSALIDA  /  Voz_Clara_Altavoces')
        info.setWordWrap(True)
        bus.addWidget(info)
        bus.addStretch()
        protected = QPushButton('Aplicar voz protegida')
        protected.clicked.connect(self.protected_voice)
        bus.addWidget(protected)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_page = QWidget()
        settings_page.setObjectName('page')
        settings_layout = QHBoxLayout(settings_page)
        settings_layout.setContentsMargins(0, 14, 0, 0)
        form = card(settings_layout, 'MOTOR', 'Ajustes de audio', 'Detén el motor para cambiar frecuencia y búfer.')
        section(form, 'FRECUENCIA DE PROCESAMIENTO')
        self.rate = QComboBox()
        self.rate.addItems(['44100', '48000', '96000'])
        rate = str(self.settings.value('rate', '48000'))
        self.rate.setCurrentText(rate if rate in ('44100', '48000', '96000') else '48000')
        form.addWidget(self.rate)
        section(form, 'BÚFER DSP / MUESTRAS')
        self.buffer = QComboBox()
        self.buffer.addItems(['128', '256', '512', '1024', '2048'])
        buffer = str(self.settings.value('buffer', '512'))
        self.buffer.setCurrentText(buffer if buffer in ('128', '256', '512', '1024', '2048') else '512')
        form.addWidget(self.buffer)
        self.latency_label = QLabel()
        self.latency_label.setWordWrap(True)
        form.addWidget(self.latency_label)
        self.rate.currentTextChanged.connect(self.update_latency)
        self.buffer.currentTextChanged.connect(self.update_latency)
        self.runtime_label = QLabel('Procesamiento: detenido')
        self.runtime_label.setWordWrap(True)
        form.addWidget(self.runtime_label)
        self.refresh = QPushButton('Actualizar dispositivos')
        self.refresh.clicked.connect(self.load_devices)
        form.addWidget(self.refresh)
        form.addStretch()
        help_panel = card(settings_layout, 'ASISTENCIA', 'Recuperar audio estable', 'Empieza sin efectos y ajusta poco a poco.')
        tips = QLabel('01  Si hay cortes, prueba 512 o 1024 muestras.\n\n02  Si la entrada física satura, baja su ganancia en Linux o en el micrófono. El limitador protege lo que sale de la app.\n\n03  Oírme debe estar OFF si no quieres escuchar tu propia voz.\n\n04  RNNoise necesita 48 kHz y añade unos 30 ms; el limitador final añade otros 5 ms. No es una medición de la latencia total.')
        tips.setWordWrap(True)
        help_panel.addWidget(tips)
        help_panel.addStretch()
        safe = QPushButton('Restablecer audio seguro · sin escucha')
        safe.clicked.connect(self.safe_audio)
        help_panel.addWidget(safe)
        settings_scroll.setWidget(settings_page)
        tabs.addTab(settings_scroll, 'Motor y ayuda')
        self.status = QLabel('Listo para iniciar')
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.pad.x = self.number_setting('x', 0, -1, 1, float)
        self.pad.y = self.number_setting('y', 0, -1, 1, float)
        self.toggle_noise(self.noise_button.isChecked())
        self.sync()
        self.load_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(60)

    def number_setting(self, key, default, minimum, maximum, convert=int):
        try:
            value = convert(self.settings.value(key, default))
            return max(minimum, min(maximum, value)) if math.isfinite(value) else default
        except (ValueError, TypeError, OverflowError):
            return default

    def protected_voice(self):
        self.safe_audio()
        self.comp.setValue(3)
        self.gain.setValue(0)
        self.ceiling.setValue(-3)
        self.status.setText('Voz protegida: compresor suave, techo −3 dBFS y escucha OFF. Pulsa Iniciar audio.')

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
        ceiling = 10**(self.ceiling.value()/20)
        self.engine.safety.limiter.ceiling = ceiling
        self.ceiling_label.setText(f'Techo del micrófono · {self.ceiling.value()} dBFS')
        self.comp_label.setText(f'COMP · {p.comp}/10' if p.comp else 'COMP · Apagado')
        self.engine.headphones.gains = tuple(slider.value() for slider in self.eq)
        self.engine.headphones.volume_db = self.hp_gain.value()
        self.engine.headphones.muted = self.hp_mute.isChecked()
        self.engine.noise.strength = self.noise_strength.value()
        self.noise_strength_label.setText(f'Potencia · {self.noise_strength.value()} %')
        self.hp_label.setText(f'{self.hp_gain.value():+d} dB')
        for slider, label in zip(self.eq, self.eq_labels):
            label.setText(f'{slider.value():+d} dB')
        self.gate_label.setText(f'GATE · {p.gate_db} dBFS' if p.gate_db > -80 else 'GATE · Desactivado')
        self.gain_label.setText(f'{p.gain_db:+d} dB')

    def reset_eq(self):
        for slider in self.eq:
            slider.setValue(0)

    def safe_audio(self):
        self.start.setChecked(False)
        self.listen.setChecked(False)
        self.noise_button.setChecked(False)
        self.rate.setCurrentText('48000')
        self.buffer.setCurrentText('512')
        self.gate.setValue(-80)
        self.comp.setValue(0)
        self.ceiling.setValue(-1)
        self.gain.setValue(-6)
        self.hp_gain.setValue(-6)
        self.mute.setChecked(False)
        self.hp_mute.setChecked(False)
        self.mono.setChecked(True)
        self.pad.x = self.pad.y = 0
        self.pad.update()
        self.reset_eq()
        self.sync()
        self.status.setText('Ajustes seguros aplicados. Pulsa Iniciar audio. Oírme OFF evita la copia retardada de tu voz; usa auriculares para evitar eco acústico.')

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
        reserve = max(duration, 10)*3
        self.latency_label.setText(f'Bloque DSP: {duration:.2f} ms. Reserva solicitada de reproducción: {reserve:.1f} ms por flujo. '
            'Limitador final: 5 ms adicionales. No es la latencia total medida. Si hay cortes, prueba 512 o 1024 muestras.' +
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
                    self.noise_button.isChecked(), self.noise_strength.value(), configure=self.sync)
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
        self.meter.setValue(int(max(0, self.engine.safety.output_db+90)) if self.start.isChecked() else 0)
        self.hp_meter.setValue(int(max(0, self.engine.headphones.output_db+90)) if self.start.isChecked() else 0)
        running = self.start.isChecked()
        self.engine_badge.setText('●  MOTOR ACTIVO' if running else '●  MOTOR DETENIDO')
        mic_reduction = (self.engine.processor.limiter.reduction_db + self.engine.safety.limiter.reduction_db) if running else 0
        hp_reduction = self.engine.headphones.limiter.reduction_db if running else 0
        self.mic_reduction.setValue(round(mic_reduction*10))
        self.hp_reduction.setValue(round(hp_reduction*10))
        self.mic_reduction_label.setText(f'Micrófono · {mic_reduction:.1f} dB')
        self.hp_reduction_label.setText(f'Salida · {hp_reduction:.1f} dB')
        self.input_warning.setText('Entrada física muy alta: baja su ganancia en Linux o en el micrófono.' if running and self.engine.input_peak >= .98 else 'Entrada física sin alertas' if running else 'Entrada física · motor detenido')
        if self.start.isChecked():
            deadline = self.engine.frames/self.engine.rate*1000
            self.runtime_label.setText(f'DSP del último bloque: {self.engine.processing_ms:.2f} ms / {deadline:.2f} ms disponibles. '
                f'Bloques de escucha descartados: {self.engine.dropped}. ' +
                ('Entrada cerca de saturar: baja la ganancia física o el volumen de entrada de Linux. '
                 if self.engine.input_peak >= .98 else '') +
                (f'Protección de picos: micrófono {self.engine.processor.limiter.reduction_db:.1f} dB / '
                 f'salida {self.engine.headphones.limiter.reduction_db:.1f} dB.'))
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
                ceiling=self.ceiling.value(), rate=self.rate.currentText(), buffer=self.buffer.currentText(), source=self.source.currentData(), sink=self.sink.currentData()).items():
            if value is not None:
                self.settings.setValue(key, value)
        for i, slider in enumerate(self.eq):
            self.settings.setValue(f'eq{i}', slider.value())
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    window.show()
    sys.exit(app.exec())
