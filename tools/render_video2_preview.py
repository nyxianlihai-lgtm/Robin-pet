"""Render the actual runtime frames and action sequencing for review."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication
from main import load_fonts
from config import ROOT
from video_motion import MotionLibrary, MotionPlayer


def main():
    app = QApplication([])
    load_fonts()
    lib = MotionLibrary()
    lib.resize(220)
    assert lib.available, lib.problem
    players = [MotionPlayer(lib) for _ in range(4)]
    for player, action in zip(players[1:], ('wave', 'turn', 'walk')):
        player.trigger(action)
    travel = 0
    out = ROOT / 'qa' / 'video2-hq'
    out.mkdir(exist_ok=True)
    writer = cv2.VideoWriter(str(out / '动作预览-raw.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 24, (960, 640))
    assert writer.isOpened()
    for i in range(24 * 16):
        image = QImage(960, 640, QImage.Format.Format_RGB888)
        image.fill(QColor('#eee9f6'))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for j, (player, title) in enumerate(zip(players, ('待机 / 自然眨眼', '抬手招呼 / 原帧收手',
                                                           '正面 → 侧面 → 背面 → 返回', '转向 → 向左散步 → 停下返回'))):
            x, y = j % 2 * 480, j // 2 * 320
            dark = j >= 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#29232e' if dark else '#ffffff'))
            painter.drawRoundedRect(QRectF(x+8, y+8, 464, 304), 14, 14)
            painter.setPen(QColor('#d5c7e6' if dark else '#574567'))
            painter.setFont(QFont('Microsoft YaHei UI', 11))
            painter.drawText(QRectF(x, y+15, 480, 27), Qt.AlignmentFlag.AlignCenter, title)
            dx = -travel if j == 3 else 0
            painter.drawPixmap(round(x + 130 + dx), y+52, player.frame())
            painter.setFont(QFont('Microsoft YaHei UI', 9))
            painter.drawText(QRectF(x, y+280, 480, 24), Qt.AlignmentFlag.AlignCenter,
                             f'{i/24:.1f}s · {player.label}')
        painter.end()
        arr = np.frombuffer(image.constBits(), np.uint8).reshape(640, image.bytesPerLine())[:, :960*3].reshape(640, 960, 3)
        writer.write(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        if i in (0, 6*24, 9*24, 12*24, 14*24):
            image.save(str(out / f'preview_{i:04d}.png'))
        for player in players:
            player.update(1/24)
        travel += players[3].travel_seconds * 22
    writer.release()
    print(out / '动作预览-raw.mp4')


if __name__ == '__main__':
    main()
