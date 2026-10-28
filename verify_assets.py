"""Test optional packs using generated geometry, not any character artwork."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import subprocess
import sys
import tempfile
import json

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
        assert p.trigger('wave') and p.elapsed == at  # No restart on repeated petting.
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
        at = idle_player.elapsed
        idle_player.queued = 'walk_in'
        assert idle_player.trigger('idle')
        assert idle_player.elapsed == at and idle_player.queued is None
        # Refined transparent frames must bypass green-screen keying entirely.
        sequence = directory / 'refined'
        sequence.mkdir()
        for i in range(4):
            rgba = np.zeros((240, 320, 4), np.uint8)
            rgba[50:190, 100:220] = (40, 180, 80, 255)
            rgba[100, 160] = (0, 255, 0, 128)
            assert cv2.imwrite(str(sequence / f'{i:04d}.png'), rgba)
        refined = directory / 'refined-pack'
        subprocess.run([sys.executable, str(ROOT / 'tools/prepare_video2.py'),
                        '--input', str(sequence), '--output', str(refined),
                        '--idle-loop', 'forward'], check=True, capture_output=True)
        refined_lib = MotionLibrary(refined)
        assert refined_lib.available, refined_lib.problem
        assert len(refined_lib.order) == 4  # Naturally closed idle plays forward.
        saved = cv2.imread(str(refined_lib.paths[0]), cv2.IMREAD_UNCHANGED)
        assert np.array_equal(saved, rgba)  # Includes green and partial alpha.
        # Gait displacement follows source-frame progress, independent of ticks.
        manifest_path = output / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['clips']['walk']['stride'] = 80
        manifest['clips']['walk']['travel_curve'] = [0] * 7 + [i / 6 for i in range(1, 7)]
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        gait_lib = MotionLibrary(output)
        assert gait_lib.available, gait_lib.problem
        gait_lib.resize(180)
        assert abs(gait_lib.walk_stride(180) - 80 * gait_lib.render_scale) < 1e-8
        a, b = MotionPlayer(gait_lib), MotionPlayer(gait_lib)
        for player in (a, b):
            player.current = 'walk'
        a.update(.5)
        distance = 0
        for dt in (.1, .15, .05, .2):
            b.update(dt)
            distance += b.travel_cycles
        assert abs(a.travel_cycles - distance) < 1e-8 and abs(distance - 1) < 1e-8
        c = MotionPlayer(gait_lib)
        c.current = 'walk'
        c.update(.2)
        assert c.travel_cycles == 0  # An authored stationary phase stays stationary.
        c.update(1, dragging=True)
        assert c.travel_cycles == 0
        c.trigger('idle')
        assert c.elapsed == gait_lib.closest_idle_time(gait_lib.source_index(.2, 'walk'))
        c.trigger('walk')
        c.stop_walk()
        c.update(gait_lib.duration('walk_in'))
        assert c.current == 'walk_out' and c.travel_cycles == 0
        manifest['clips']['walk']['travel_curve'][2] = .9
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        assert not MotionLibrary(output).available
        print('PASS: refined alpha preserved; forward idle; repeated gesture continuity; frame-based gait curves; tick-independent displacement; early walk stop; invalid curve rejection')
        print('PASS: missing-pack fallback; generic video processing/resampling; alpha; DPI; immediate actions; idle loop; gait-only travel; optional actions; overwrite guard')


if __name__ == '__main__':
    main()
