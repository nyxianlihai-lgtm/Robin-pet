"""Test optional packs using generated geometry, not any character artwork."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from config import ROOT
from video_motion import MotionLibrary, MotionPlayer


def main():
    app = QApplication([])
    (ROOT / 'qa').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='generic-video-', dir=ROOT / 'qa') as temporary:
        directory = Path(temporary)
        missing = MotionLibrary(directory / 'no-pack')
        assert not missing.available and not MotionPlayer(missing).trigger('wave')
        source = directory / 'geometry.avi'
        writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 24, (320, 240))
        assert writer.isOpened()
        for i in range(12):
            image = np.zeros((240, 320, 3), np.uint8)
            image[:] = (0, 180, 0)
            cv2.ellipse(image, (160+i%3, 125), (60, 75), 0, 0, 360, (190, 70, 200), -1)
            if i != 7:
                cv2.circle(image, (145+i%3, 110), 7, (250, 250, 250), -1)
            writer.write(image)
        writer.release()
        output = directory / 'pack'
        command = [sys.executable, str(ROOT / 'tools/prepare_video2.py'), '--input', str(source),
                   '--output', str(output)]
        for flag in ('--wave', '--turn', '--walk-in', '--walk', '--walk-out'):
            command += [flag, str(source)]
        subprocess.run(command, check=True, capture_output=True)
        lib = MotionLibrary(output)
        assert lib.available, lib.problem
        assert lib.frame_count == 72 and lib.fps == 24
        assert set(lib.clips) == {'idle', 'wave', 'turn', 'walk_in', 'walk', 'walk_out'}
        for path in lib.paths:
            image = QImage(str(path))
            assert image.pixelColor(0, 0).alpha() == 0
            assert image.pixelColor(160, 125).alpha() == 255
        lib.resize(180, 2)
        assert lib.cache[0].devicePixelRatio() == 2
        assert lib.cache[0].deviceIndependentSize().height() == 180
        p = MotionPlayer(lib)
        p.update(.1)
        assert p.trigger('wave') and p.current == 'wave' and p.queued is None
        p.update(.13)
        assert p.transition_from is None
        at = p.elapsed
        p.update(1, sleeping=True)
        assert p.elapsed == at
        p.update(1, dragging=True)
        assert p.elapsed == at and p.travel_seconds == 0
        p.update(lib.duration('wave') - p.elapsed)
        assert p.current == 'idle'
        assert p.trigger('turn') and p.current == 'turn'
        assert p.trigger('idle') and p.current == 'idle' and p.elapsed == 0
        p.update(lib.duration() * 3 + .1)
        assert p.current == 'idle'
        assert p.trigger('walk') and p.current == 'walk_in'
        p.update(lib.duration('walk_in'))
        assert p.current == 'walk' and p.travel_seconds == 0
        p.update(.1)
        assert abs(p.travel_seconds - .1) < 1e-7
        assert p.trigger('idle') and p.travel_seconds == 0
        p.update(.2)
        assert p.current == 'idle' and p.travel_seconds == 0
        # Explicitly reject replacing user packs unless the user asks for it.
        again = subprocess.run(command, capture_output=True)
        assert again.returncode != 0
        idle_only = directory / 'idle-only'
        subprocess.run([sys.executable, str(ROOT / 'tools/prepare_video2.py'), '--input', str(source),
                        '--fps', '12', '--output', str(idle_only)], check=True, capture_output=True)
        simple = MotionLibrary(idle_only)
        assert simple.available and simple.frame_count == 6
        simple.resize(180)
        idle_player = MotionPlayer(simple)
        idle_player.roam_after = 0
        idle_player.update(3, roaming=True)
        assert idle_player.current == 'idle' and idle_player.queued is None
        assert not idle_player.trigger('walk')
        print('PASS: missing-pack fallback; generic video processing/resampling; alpha; DPI; immediate actions; idle loop; gait-only travel; optional actions; overwrite guard')


if __name__ == '__main__':
    main()
