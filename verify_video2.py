"""Check supplied clip integrity, transparency, and movement boundaries."""
import hashlib
import os
import sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from config import ROOT
from video_motion import MotionLibrary, MotionPlayer


def main():
    app = QApplication([])
    lib = MotionLibrary()
    assert lib.available, lib.problem
    assert lib.manifest['version'] == 2 and lib.frame_count == 484 and lib.fps == 24
    assert lib.manifest['revision'] == 'hq-enclosed-iris'
    assert lib.manifest['canvas'] == [580, 700]
    for s in lib.manifest['sources'].values():
        assert hashlib.sha256((ROOT / s['path']).read_bytes()).hexdigest() == s['sha256']
    print('PASS: four original videos unchanged; all 484 transparent frames present')
    for path in lib.paths:
        image = QImage(str(path))
        assert not image.isNull() and image.hasAlphaChannel(), path
        w, h = image.width(), image.height()
        for x, y in [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1), (w-1, h//2)]:
            assert image.pixelColor(x, y).alpha() == 0, (path, x, y)
    eye_pixels = 0
    for index in (lib.order[0], lib.order[30]):
        image = QImage(str(lib.paths[index]))
        for y in range(280, 390):
            for x in range(180, 390):
                c = image.pixelColor(x, y)
                if c.green() > max(c.red(), c.blue()) + 25 and c.alpha() >= 250:
                    eye_pixels += 1
    assert eye_pixels > 40
    # Regression: the old fixed ellipse exposed a screen crescent on walk 54.
    image = QImage(str(lib.paths[121+54]))
    # Old 640x360 pixel (242,165), now native-resolution, with fixed canvas crop.
    for x, y in [(124, 330), (128, 334), (132, 338)]:
        assert image.pixelColor(x, y).alpha() == 0, (x, y, image.pixelColor(x, y).alpha())
    for name in ('idle', 'wave', 'turn'):
        order = lib.clips[name]['order']
        assert all(abs(a - b) == 1 for a, b in zip(order, order[1:] + order[:1]))
    print('PASS: transparent background, teal eyes; adjacent-frame idle/gesture/turn returns')
    lib.resize(280)
    assert lib.available and len(lib.cache) == 484
    lib.resize(280, 2)
    frame = lib.cache[lib.order[0]]
    assert frame.width() == 560 and frame.devicePixelRatio() == 2
    assert frame.deviceIndependentSize().height() == 280
    lib.resize(280)
    p = MotionPlayer(lib)
    p.update(.5)
    before = (p.current, p.elapsed, p.frame().cacheKey())
    assert p.trigger('wave')
    assert p.current == 'wave' and p.queued is None
    assert p.elapsed == 44 / lib.fps
    assert p.frame().cacheKey() == before[2]
    at = p.elapsed
    p.update(10, sleeping=True)
    assert p.elapsed == at and p.frame().cacheKey() == before[2]
    p.update(10, dragging=True)
    assert p.elapsed == at and p.travel_seconds == 0
    p.update(.13)
    assert p.transition_from is None and p.elapsed > at
    p.update(lib.duration('wave') - p.elapsed)
    assert p.current == 'idle' and p.elapsed == 0
    assert p.trigger('turn')
    assert p.current == 'turn' and p.elapsed == 20 / lib.fps
    p.update(.5)
    assert p.trigger('wave', force=True)
    assert p.current == 'wave' and p.elapsed == 44 / lib.fps and p.queued is None
    p.update(.2)
    assert p.trigger('idle')
    assert p.current == 'idle' and p.elapsed == 0 and p.queued is None
    p.update(.13)
    first = bytes(p.frame().toImage().constBits())
    p.update(1.2)
    blink = bytes(p.frame().toImage().constBits())
    assert blink != first, 'Idle must animate after explicitly selecting it'
    p.update(lib.duration() * 3)
    assert p.current == 'idle'
    print('PASS: immediate interaction/replacement; 120ms whole-frame transition; idle resumes and loops')
    assert p.trigger('walk')
    assert p.current == 'walk_in' and p.travel_seconds == 0
    p.update(lib.duration('walk_in') - p.elapsed)
    assert p.current == 'walk' and p.travel_seconds == 0
    p.update(.25)
    assert abs(p.travel_seconds - .25) < 1e-6
    assert p.trigger('idle')
    assert p.current == 'idle' and p.travel_seconds == 0
    p.update(.2)
    assert p.travel_seconds == 0
    assert p.trigger('walk')
    p.update(lib.duration('walk_in') - p.elapsed)
    p.update(.25)
    p.stop_walk()
    p.update(lib.duration('walk') - p.elapsed)
    assert p.current == 'walk_out'
    p.update(.25)
    assert p.travel_seconds == 0
    p.update(lib.duration('walk_out') - p.elapsed)
    assert p.current == 'idle'
    p.roam_after = 0
    p.update(.1, roaming=True)
    assert p.queued == 'walk_in' and p.travel_seconds == 0
    assert not p.trigger('pat') and not p.trigger('right_walk')
    assert not any(n in sys.modules for n in ('rig', 'tween', 'cv2'))
    print('PASS: turn before gait, travel only during walk, graceful stop; no synthetic right walk')
    print('Walk range / seam MAE:', lib.manifest['sources']['walk']['loop_range'],
          lib.manifest['sources']['walk']['join_mae'])
    print('All video2 checks passed.')


if __name__ == '__main__':
    main()
