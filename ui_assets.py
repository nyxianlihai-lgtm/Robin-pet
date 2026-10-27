"""Neutral code-drawn application mark, independent of any game character."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def placeholder(size=256):
    image = QPixmap(size, size)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#8b78b5'))
    painter.drawRoundedRect(QRectF(size * .08, size * .08, size * .84, size * .84),
                            size * .25, size * .25)
    painter.setPen(QColor('#ffffff'))
    painter.setFont(QFont('Segoe UI', round(size * .42), QFont.Weight.Bold))
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, 'R')
    painter.end()
    return image


def app_icon():
    return QIcon(placeholder(128))
