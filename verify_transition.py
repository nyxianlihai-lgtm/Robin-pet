"""Regression checks for bright flashes when crossfading transparent sprites."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from types import SimpleNamespace
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from video_motion import MotionPlayer


def pixel(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    return list(bytes(image.constBits())[:4])


def sprite(color, ratio):
    result = QPixmap(8 * ratio, 8 * ratio)
    result.setDevicePixelRatio(ratio)
    result.fill(QColor(*color))
    return result


def main():
    app = QApplication([])
    for ratio in (1, 2):
        for left, right in (
            ((80,90,150,255),(80,90,150,255)),
            ((255,255,255,255),(255,255,255,255)),
            ((30,60,120,255),(210,180,150,255)),
            ((80,90,150,128),(80,90,150,128)),
            ((30,60,120,64),(210,180,150,192)),
            ((0,0,0,0),(210,180,150,255)),
        ):
            before, after = sprite(left, ratio), sprite(right, ratio)
            player = MotionPlayer(SimpleNamespace(clip_frame=lambda *args: after))
            player.transition_from = before
            a, b = pixel(before), pixel(after)
            for weight in (0, .1, .25, .5, .75, .9, 1):
                player.transition_elapsed = weight * player.transition_duration
                mixed = player.frame()
                assert mixed.devicePixelRatio() == ratio
                expected = [(1-weight)*x + weight*y for x,y in zip(a,b)]
                assert all(abs(actual-wanted) <= 2 for actual,wanted in zip(pixel(mixed),expected)), (left,right,weight,pixel(mixed),expected)
                if left[3] == right[3] == 255:
                    assert mixed.toImage().pixelColor(0,0).alpha() == 255
                # Check compositing on light/dark desktop backgrounds, too.
                for background in ('#ffffff', '#29232e'):
                    canvas = QPixmap(mixed.size())
                    canvas.setDevicePixelRatio(ratio)
                    canvas.fill(QColor(background))
                    painter = QPainter(canvas)
                    painter.drawPixmap(0,0,mixed)
                    painter.end()
                    assert canvas.toImage().pixelColor(0,0).alpha() == 255
    print('PASS: weighted premultiplied crossfade, stable brightness and alpha, transparent edges, 100%/200% DPI')


if __name__ == '__main__':
    main()
