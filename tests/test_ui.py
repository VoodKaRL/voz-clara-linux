"""Offscreen UI checks; no microphone, desktop audio, or user settings access."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
import main


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(self.temp.name+'/test.ini', QSettings.Format.IniFormat)
        self.addCleanup(patch.stopall)
        patch.object(main, 'QSettings', return_value=self.settings).start()
        patch.object(main, 'configure_audio').start()
        patch.object(main, 'devices', side_effect=lambda kind: [('physical-'+kind, 'Equipo USB de prueba')]).start()

    def window(self):
        window = main.Window()
        self.addCleanup(window.close)
        return window

    def test_corrupt_settings_fall_back_without_crashing(self):
        for key, value in {'gain':'broken', 'x':'nan', 'y':'inf', 'comp':500,
                           'rate':'oops', 'buffer':None, 'ceiling':'oops'}.items():
            self.settings.setValue(key, value)
        w = self.window()
        self.assertEqual(w.gain.value(), 0)
        self.assertEqual(w.pad.x, 0)
        self.assertEqual(w.pad.y, 0)
        self.assertEqual(w.comp.value(), 10)
        self.assertEqual(w.rate.currentText(), '48000')
        self.assertEqual(w.buffer.currentText(), '512')
        self.assertEqual(w.ceiling.value(), -1)

    def test_protected_preset_applies_final_ceiling_without_monitoring(self):
        w = self.window()
        w.protected_voice()
        self.assertEqual(w.comp.value(), 3)
        self.assertEqual(w.gate.value(), -80)
        self.assertAlmostEqual(w.engine.safety.limiter.ceiling, 10**(-3/20))
        self.assertFalse(w.listen.isChecked())
        self.assertIsNone(w.engine.monitor_queue)
        self.assertFalse(w.start.isChecked())

    def test_ceiling_is_saved_and_applied_immediately(self):
        w = self.window()
        w.ceiling.setValue(-8)
        self.assertAlmostEqual(w.engine.safety.limiter.ceiling, 10**(-8/20))
        w.close()
        self.assertEqual(self.settings.value('ceiling'), -8)

    def test_missing_devices_do_not_erase_saved_selection(self):
        self.settings.setValue('source', 'remember-this-mic')
        w = self.window()
        w.source.clear()
        w.close()
        self.assertEqual(self.settings.value('source'), 'remember-this-mic')

    def test_meter_and_layout_render_without_starting_audio(self):
        w = self.window()
        w.show()
        self.app.processEvents()
        w.tick()
        self.assertFalse(w.grab().isNull())
        self.assertEqual(w.engine_badge.text(), '●  MOTOR DETENIDO')
        self.assertFalse(w.engine.processes)
