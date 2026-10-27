"""Render the real frame player to PNGs for video QA, or open a live preview."""
import os
import sys
import time

if "--render" in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from config import ROOT
from main import load_fonts
from motion_rig import MotionLibrary


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("知更鸟 · 固定图层动作预览")
        self.comparison = "--compare" in sys.argv
        self.resize(960, 440)
        self.library = MotionLibrary()
        if not self.library.available:
            raise RuntimeError(self.library.problem)
        self.library.resize(280)
        self.legacy_library = None
        if self.comparison:
            from motion_legacy import MotionLibrary as LegacyLibrary
            self.legacy_library = LegacyLibrary()
            self.legacy_library.resize(280)
        self.time = 0
        self.last_time = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(16)

    def advance(self):
        now = time.monotonic()
        self.time += now - self.last_time
        self.last_time = now
        self.update()

    def draw(self, painter, at):
        painter.fillRect(0, 0, 960, 440, QColor("#f6f2fb"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#544169"))
        painter.setFont(QFont("Microsoft YaHei UI", 17, QFont.Weight.Bold))
        title = "知更鸟 A · 线条稳定性对比" if self.comparison else "知更鸟 A · 固定图层动作预览"
        painter.drawText(QRectF(0, 17, 960, 35), Qt.AlignmentFlag.AlignCenter, title)
        entries = ((("raw", "上一版：光流补帧", 0), ("wave", "新版：固定图层与关节转动", 0))
                   if self.comparison else (("blink", "局部眨眼", 0.04), ("wave", "连续挥手", 0.2), ("pat", "抬手回应", 0.6)))
        card_width = 462 if self.comparison else 304
        for column, (action, label, delay) in enumerate(entries):
            x = column * (card_width + 12) + 12
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(QRectF(x, 70, card_width, 350), 18, 18)
            if action == "raw":
                frame = self.legacy_wave(at)
            else:
                elapsed = (at + delay) % (self.library.duration(action) + 1.2)
                frame = (self.library.clip_frame(action, elapsed) if elapsed < self.library.duration(action)
                         else self.library.still_frame("neutral"))
            painter.drawPixmap(x + (card_width - 280) // 2, 85, frame)
            painter.setPen(QColor("#8e6eb4"))
            painter.setFont(QFont("Microsoft YaHei UI", 12))
            painter.drawText(QRectF(x, 376, card_width, 25), Qt.AlignmentFlag.AlignCenter, label)

    def legacy_wave(self, at):
        library = self.legacy_library
        elapsed = at % (library.duration("wave") + 1.2)
        return (library.clip_frame("wave", elapsed) if elapsed < library.duration("wave")
                else library.still_frame("neutral"))

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw(painter, self.time)

    def closeEvent(self, event):
        self.timer.stop()
        self.library.close()
        if self.legacy_library:
            self.legacy_library.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    load_fonts()
    window = Preview()
    if "--render" in sys.argv:
        window.timer.stop()
        window.library.wait_ready()
        if window.legacy_library:
            window.legacy_library.wait_ready()
        directory = ROOT / "qa" / ("rig-comparison" if window.comparison else "rig-preview")
        directory.mkdir(parents=True, exist_ok=True)
        for frame_number in range(240):
            frame = QPixmap(960, 440)
            painter = QPainter(frame)
            window.draw(painter, frame_number / 30)
            painter.end()
            frame.save(str(directory / f"frame_{frame_number:04d}.png"))
        window.library.close()
        if window.legacy_library:
            window.legacy_library.close()
        print(f"Rendered 240 preview frames to {directory}")
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
