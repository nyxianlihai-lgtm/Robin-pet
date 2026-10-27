"""Offline visual and state-transition checks for the new animation system."""
import os
from pathlib import Path
import random
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from config import ROOT
from main import load_fonts
from motion_legacy import MotionLibrary, MotionPlayer


def visible_bounds(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    raw = bytes(image.constBits())
    stride = image.bytesPerLine()
    occupied = []
    for y in range(image.height()):
        xs = [x for x, a in enumerate(raw[y * stride + 3:y * stride + image.width() * 4:4]) if a >= 160]
        if len(xs) > 3:
            occupied.append((y, min(xs), max(xs)))
    return min(x for _, x, _ in occupied), occupied[0][0], max(x for _, _, x in occupied), occupied[-1][0]


def main():
    app = QApplication([])
    load_fonts()
    library = MotionLibrary()
    assert library.available, library.problem
    for height in (160, 280, 440):
        library.resize(height)
        assert len(library.scaled) == 24
        baselines = []
        for key, frame in library.scaled.items():
            assert frame.width() == height and frame.height() == height
            left, top, right, bottom = visible_bounds(frame)
            assert top >= 1 and left > 0 and right < height - 1, (key, height, (left, top, right, bottom))
            assert bottom <= height - 3, (key, bottom)
            baselines.append(bottom)
        assert max(baselines) - min(baselines) <= 2, baselines
    print("PASS: all 24 frames, alpha, foot alignment, margins, three display sizes")
    library.resize(280)
    library.wait_ready()
    # Identity error in generated pat frame 4 (mirrored halo) is never played.
    assert 4 not in [i for i, _ in library.clips["pat"]["frames"]]
    for name in ("blink", "wave", "pat", "glance"):
        images = {bytes(library.clip_frame(name, time / 30).toImage().constBits())
                  for time in range(int(library.duration(name) * 30))}
        assert len(images) >= 3, name
    print("PASS: visible frame changes in each action; rejected pose excluded")

    player = MotionPlayer(library, random.Random(9))
    assert player.trigger("wave")
    player.update(0.23)
    before = player.elapsed
    assert not player.trigger("pat") and player.elapsed == before
    player.update(10)
    assert player.action is None
    assert player.frame().cacheKey() == library.still_frame("neutral").cacheKey()
    player.trigger("pat")
    player.update(0.5, sleeping=True)
    assert player.mode == "sleep" and player.action is None
    assert player.frame().cacheKey() == library.still_frame("sleep").cacheKey()
    assert not player.trigger("wave")
    player.update(0.1, sleeping=True, dragging=True)
    assert player.mode == "drag"
    player.update(0.1)
    assert player.mode == "idle" and player.action is None
    print("PASS: finish-to-idle, click debounce, sleep/drag priorities and wake-up")

    observed = set()
    for _ in range(2400):
        player.update(1 / 30)
        if player.action:
            observed.add(player.action)
    assert "blink" in observed and observed.intersection({"glance", "wave"}), observed
    player.thinking = True
    player.action = None
    player.update(0.25)
    assert player.frame().cacheKey() == library.still_frame("thinking").cacheKey()
    print("PASS: spontaneous gestures remain active alongside periodic blinks; thinking pose")

    with tempfile.TemporaryDirectory(dir=ROOT / "qa") as missing:
        fallback = MotionLibrary(Path(missing))
        assert not fallback.available and fallback.problem
        fallback.resize(280)
    print("PASS: absent/corrupt animation library falls back without a crash")
    library.close()
    print("All motion checks passed.")


if __name__ == "__main__":
    (ROOT / "qa").mkdir(exist_ok=True)
    main()
