"""Shared mixer styling and an inexpensive segmented audio meter."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

STYLE = '''
QWidget { color: #dbe4f3; font-family: "Inter", "Noto Sans", sans-serif; font-size: 12px; }
QWidget#window { background: #10141d; }
QWidget#page { background: #10141d; }
QFrame#card { background: #191f2b; border: 1px solid #2a3445; border-radius: 12px; }
QLabel { background: transparent; }
QLabel#brand { font-size: 24px; font-weight: 800; color: #f2f6ff; }
QLabel#muted { color: #8f9eb5; }
QLabel#section { color: #a8b8d0; font-size: 10px; font-weight: 700; }
QLabel#channel { color: #f2f6ff; font-size: 17px; font-weight: 700; }
QLabel#badge { color: #80e9c2; background: #1c3734; border: 1px solid #305b50; border-radius: 7px; padding: 6px 9px; font-size: 10px; font-weight: 700; }
QLabel#engineBadge { color: #a7b5ca; background: #242c3a; border-radius: 7px; padding: 6px 12px; }
QLabel#faderValue { font-size: 24px; font-weight: 700; color: #f2f6ff; }
QPushButton { background: #252f40; border: 1px solid #35445a; border-radius: 7px; padding: 9px 12px; font-weight: 600; }
QPushButton:hover { background: #303e53; border-color: #667c99; }
QPushButton:pressed { background: #182535; }
QPushButton:checked { background: #204d45; color: #9af5d5; border-color: #3c9f83; }
QPushButton#primary { color: #0a231d; background: #77e5bd; border-color: #77e5bd; padding: 10px 20px; }
QPushButton#primary:hover { background: #9df4d6; }
QPushButton#primary:checked { background: #783c44; border-color: #bb6572; color: #ffe5e9; }
QPushButton#mute:checked { color: #ffcad1; background: #60333e; border-color: #a65b6b; }
QWidget:disabled { color: #677386; }
QPushButton:disabled { background: #1b2230; border-color: #293343; }
QComboBox { background: #111824; border: 1px solid #344359; border-radius: 6px; padding: 8px; min-height: 18px; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: #202b3b; color: #edf5ff; selection-background-color: #355a61; }
QTabWidget::pane { border: 0; }
QTabBar::tab { color: #91a1ba; padding: 12px 18px; border-bottom: 2px solid transparent; margin-right: 8px; }
QTabBar::tab:selected { color: #8ceecb; border-bottom: 2px solid #77e5bd; }
QTabBar::tab:hover { color: #edf5ff; }
QSlider::groove:vertical { background: #0e131d; width: 8px; border: 1px solid #2e3b50; border-radius: 4px; }
QSlider::sub-page:vertical { background: #0e131d; border-radius: 4px; }
QSlider::add-page:vertical { background: #386d64; border-radius: 4px; }
QSlider::handle:vertical { background: #dce5f2; border: 1px solid #8f9fb7; height: 22px; margin: 0 -12px; border-radius: 4px; }
QSlider::groove:horizontal { height: 5px; background: #0e131d; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #5bb99d; border-radius: 2px; }
QSlider::handle:horizontal { background: #dce5f2; width: 12px; margin: -5px 0; border-radius: 5px; }
QProgressBar { border: 0; background: #101722; border-radius: 3px; height: 7px; }
QProgressBar::chunk { background: #e8b96b; border-radius: 3px; }
QScrollArea { border: 0; background: #10141d; }
QScrollBar:vertical { background: #111722; width: 8px; }
QScrollBar::handle:vertical { background: #3e4d63; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #e2efff; background: #243144; border: 1px solid #456077; padding: 6px; }
'''


class LevelMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.level = 0
        self.setFixedWidth(58)
        self.setMinimumHeight(110)
        self.setToolTip('Nivel RMS en dBFS')

    def setValue(self, value):
        self.level = max(0, min(90, value))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        height = self.height()-16
        for i in range(30):
            y = int(8+height-(i+1)*height/30)
            active = self.level > i*3
            color = '#71e1b8' if i < 26 else '#edbf74' if i < 29 else '#f17d8b'
            p.fillRect(2, y, 19, max(2, int(height/30)-2), QColor(color if active else '#293344'))
        p.setPen(QColor('#8798b0'))
        font = p.font()
        font.setPixelSize(9)
        p.setFont(font)
        for db in (0, -12, -24, -48, -72):
            y = int(8+height*(-db)/90)
            p.drawText(27, min(self.height()-2, max(10, y+4)), str(db))
