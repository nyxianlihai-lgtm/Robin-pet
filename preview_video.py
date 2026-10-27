"""Preview the actual transparent idle video on light/dark backgrounds."""
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
from video_motion import MotionLibrary, MotionPlayer


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("知更鸟 · 学院装视频动作预览")
        self.setFixedSize(960, 520)
        self.library = MotionLibrary()
        if not self.library.available:
            raise RuntimeError("待机视频尚未准备完成：" + self.library.problem)
        self.library.resize(320, self.devicePixelRatioF())
        if not self.library.available:
            raise RuntimeError(self.library.problem)
        self.elapsed = 0
        self.player = MotionPlayer(self.library)
        self.paused = False
        self.last_tick = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(16)

    def advance(self):
        now = time.monotonic()
        if not self.paused:
            self.elapsed += now - self.last_tick
            self.player.update(min(.1, now - self.last_tick))
        self.last_tick = now
        self.update()

    def draw(self, painter, elapsed):
        painter.fillRect(0, 0, 960, 520, QColor("#f6f2fb"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#544169"))
        painter.setFont(QFont("Microsoft YaHei UI", 18, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 19, 960, 38), Qt.AlignmentFlag.AlignCenter, "知更鸟 · 学院装视频动作")
        painter.setFont(QFont("Microsoft YaHei UI", 10))
        painter.drawText(QRectF(0, 57, 960, 25), Qt.AlignmentFlag.AlignCenter,
                         "24 fps · " + self.player.label + " · 点击立即响应 · 同段返回含倒放")
        frame = self.player.frame()
        for x, background, foreground, title in ((20, "#ffffff", "#8b74a3", "浅色背景"),
                                                  (490, "#29232e", "#d0bfdf", "深色背景")):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(QRectF(x, 92, 450, 390), 18, 18)
            painter.drawPixmap(x + 65, 105, frame)
            painter.setPen(QColor(foreground))
            painter.setFont(QFont("Microsoft YaHei UI", 12))
            painter.drawText(QRectF(x, 444, 450, 25), Qt.AlignmentFlag.AlignCenter, title)
        painter.setPen(QColor("#9586a4"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(QRectF(0, 488, 960, 23), Qt.AlignmentFlag.AlignCenter,
                         "1 待机   2 抬手招呼   3 转身   4 散步   空格 暂停   → 下一帧   来源：参考视频2")

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw(painter, self.elapsed)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.paused = not self.paused
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.paused = True
            if event.key() == Qt.Key.Key_Right:
                self.player.update(1 / self.library.fps)
            else:
                self.player.elapsed = max(0, self.player.elapsed - 1 / self.library.fps)
        elif event.key() in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4):
            action = {Qt.Key.Key_1: "idle", Qt.Key.Key_2: "wave", Qt.Key.Key_3: "turn", Qt.Key.Key_4: "walk"}[event.key()]
            self.player.trigger(action, force=True)
            self.paused = False
        else:
            super().keyPressEvent(event)
        self.update()

    def closeEvent(self, event):
        self.timer.stop()
        self.library.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    load_fonts()
    window = Preview()
    if "--render" in sys.argv:
        window.timer.stop()
        output = ROOT / "qa" / "video-idle-preview"
        output.mkdir(parents=True, exist_ok=True)
        for index in range(300):
            window.player.update(1 / 30)
            frame = QPixmap(960, 520)
            painter = QPainter(frame)
            window.draw(painter, index / 30)
            painter.end()
            frame.save(str(output / f"frame_{index:04d}.png"))
        print("Rendered video preview:", output)
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
