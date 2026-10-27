"""Check fixed-head pixels, joint continuity, blink isolation and real rendering."""
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from config import ROOT
from motion_rig import MotionLibrary
from motion_player import MotionPlayer
from rig import DURATIONS, Pose, action_pose, alpha_bounds


def pixels(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return bytes(image.constBits())


def main():
    app = QApplication([])
    library = MotionLibrary()
    assert library.available, library.problem
    assert library.interpolator is None
    for size in (160, 280, 440):
        library.resize(size)
        for name in DURATIONS:
            for fraction in (0, 0.2, 0.4, 0.7, 1):
                image = library.clip_frame(name, library.duration(name) * fraction)
                assert image.width() == size and image.height() == size
                left, top, right, bottom = alpha_bounds(image.toImage())
                assert 0 < left < right < size - 1 and 0 < top < bottom <= size - 3, (name, size, (left, top, right, bottom))
    print("PASS: all action margins and transparent edges at 160/280/440px")
    library.resize(280)
    neutral = library.still_frame("neutral")
    head = pixels(neutral.copy(0, 0, 280, 150))
    start = time.perf_counter()
    distinct = set()
    for frame_number in range(169):
        image = library.clip_frame("wave", frame_number / 60)
        assert pixels(image.copy(0, 0, 280, 150)) == head, frame_number
        distinct.add(pixels(image))
    frame_ms = (time.perf_counter() - start) * 1000 / 169
    assert len(distinct) > 100, len(distinct)
    assert frame_ms < 16.7, frame_ms
    print(f"PASS: 169 waving frames have byte-identical head/face/hair; {frame_ms:.2f} ms/frame")

    for name, duration in DURATIONS.items():
        assert pixels(library.clip_frame(name, 0)) == pixels(neutral)
        assert pixels(library.clip_frame(name, duration)) == pixels(neutral)
        # Verify joint controls approach their endpoints with zero-speed easing.
        near = action_pose(name, duration - 0.00001)
        assert max(abs(near.left_upper - 38), abs(near.right_upper + 38),
                   abs(near.left_elbow), abs(near.right_elbow), abs(near.lean)) < 0.001
        previous = action_pose(name, 0)
        for step in range(1, math.ceil(duration * 60) + 1):
            current = action_pose(name, min(duration, step / 60))
            assert abs(current.left_upper - previous.left_upper) < 6
            assert abs(current.left_elbow - previous.left_elbow) < 7
            previous = current
    print("PASS: continuous joint trajectories and exact return-to-idle endpoints")

    # Closing eyes changes only the small eye patches, never halo or outer hair.
    opened = library.renderer.frame(Pose())
    closed = library.renderer.frame(Pose(eyelids=1))
    assert pixels(opened.copy(0, 0, 280, 110)) == pixels(closed.copy(0, 0, 280, 110))
    assert pixels(opened.copy(0, 150, 280, 130)) == pixels(closed.copy(0, 150, 280, 130))
    assert pixels(opened) != pixels(closed)
    print("PASS: eye-only blinking, no full-head crossfade")

    player = MotionPlayer(library, random.Random(8))
    assert player.trigger("wave")
    player.update(0.3)
    elapsed = player.elapsed
    assert not player.trigger("pat") and player.elapsed == elapsed
    player.update(5)
    assert player.action is None and pixels(player.frame()) == pixels(neutral)
    player.trigger("wave")
    player.update(0.9)
    assert player.trigger("pat", force=True) and player.action == "wave" and player.queued == "pat"
    player.update(5)
    assert player.action == "pat" and player.queued is None
    player.update(5)
    player.trigger("pat")
    player.update(0.5, sleeping=True)
    assert player.mode == "sleep" and player.action is None
    assert pixels(player.frame()) == pixels(library.still_frame("sleep"))
    player.update(0.3, dragging=True)
    assert player.mode == "drag"
    player.update(0.3)
    assert player.mode == "idle"
    observed = set()
    for _ in range(2400):
        player.update(1 / 30)
        if player.action:
            observed.add(player.action)
    assert "blink" in observed and observed.intersection({"wave", "glance"})
    print("PASS: gesture priorities, debounce, sleep/drag transitions and spontaneous actions")
    assert "cv2" not in sys.modules and "tween" not in sys.modules
    print("PASS: normal renderer never loads optical-flow code")
    (ROOT / "qa").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "qa") as missing:
        fallback = MotionLibrary(Path(missing))
        assert not fallback.available and fallback.problem
    print("All fixed-layer animation checks passed.")


if __name__ == "__main__":
    main()
