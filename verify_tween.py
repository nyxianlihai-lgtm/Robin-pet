"""Check actual intermediate geometry, alpha and bounded renderer cost."""
import os
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from motion_legacy import MotionLibrary
from tween import FlowInterpolator, image_array


def marker(x):
    image = QPixmap(160, 160)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#49b7c5"))
    painter.drawEllipse(x, 50, 40, 55)
    painter.setBrush(QColor("#244554"))
    painter.drawEllipse(x + 9, 61, 5, 7)
    painter.drawEllipse(x + 26, 61, 5, 7)
    painter.end()
    return image


def main():
    app = QApplication([])
    frames = {("test", 0): marker(35), ("test", 1): marker(65)}
    renderer = FlowInterpolator(frames)
    renderer.prepare([(("test", 0), ("test", 1))])
    renderer.wait_ready()
    middle = image_array(renderer.frame(("test", 0), ("test", 1), 0.5))
    mask = np.uint8(middle[:, :, 3] > 0.8)
    ys, xs = np.nonzero(mask)
    assert 66 <= xs.mean() <= 74, xs.mean()
    count, _ = cv2.connectedComponents(mask)
    assert count == 2, count  # one solid intermediate shape plus background
    assert np.max(middle[:20, :, 3]) == 0
    cyan = middle[(middle[:, :, 3] > 0.99) & (middle[:, :, 1] > 0.6)]
    assert cyan.size and np.max(np.abs(cyan[:, :3].mean(axis=0) - np.array([73, 183, 197]) / 255)) < 0.015
    renderer.close()
    print("PASS: intermediate shape moves, no doubled silhouette, transparent background, no dark alpha fringe")

    library = MotionLibrary()
    library.resize(280)
    library.wait_ready()
    assert library.interpolator and library.interpolator.ready
    max_tail_difference = 0
    counts = {}
    elapsed = []
    for clip in ("blink", "wave", "pat", "glance"):
        pixels = set()
        for step in range(1, 41):
            at = library.duration(clip) * step / 42
            start = time.perf_counter()
            image = library.clip_frame(clip, at)
            elapsed.append(time.perf_counter() - start)
            pixels.add(bytes(image.toImage().constBits()))
        counts[clip] = len(pixels)
        assert counts[clip] > len(library.clips[clip]["frames"]), counts
        tail = image_array(library.clip_frame(clip, library.duration(clip) - 0.0001))
        neutral = image_array(library.still_frame("neutral"))
        difference = np.abs(tail - neutral).mean()
        max_tail_difference = max(max_tail_difference, float(difference))
        assert difference < 0.002, (clip, difference)
    print("PASS: true in-between frames in all actions, smooth return to neutral", counts)
    average_ms = 1000 * sum(elapsed) / len(elapsed)
    print(f"Renderer mean: {average_ms:.2f} ms at 280px; tail mean difference: {max_tail_difference:.6f}")
    assert average_ms < 30, average_ms
    assert len(library.interpolator.cache) <= 32
    library.close()
    print("PASS: bounded render cache and renderer budget")


if __name__ == "__main__":
    main()
