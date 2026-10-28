"""Check the real default character ships completely and loads without setup assets."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from config import ROOT
from ui_assets import character_image
from video_motion import MotionLibrary, MotionPlayer


def main():
    app = QApplication([])
    lib = MotionLibrary(ROOT / 'assets' / 'video2_hq')
    assert lib.available, lib.problem
    assert len(lib.paths) == lib.manifest['frames']
    assert lib.frame_count == 484
    if not os.environ.get('ROBIN_PET_ASSETS') and not (ROOT / 'data/pet-assets/manifest.json').exists():
        default = MotionLibrary()
        assert default.available, default.problem
        assert default.directory == ROOT / 'assets/video2_hq'
    assert {'idle', 'wave', 'turn', 'walk_in', 'walk', 'walk_out'} <= set(lib.clips)
    for path in lib.paths:
        image = QImage(str(path))
        assert not image.isNull() and image.hasAlphaChannel(), path
        assert [image.width(), image.height()] == lib.manifest['canvas']
        for x, y in ((0, 0), (image.width()-1, 0), (0, image.height()-1)):
            assert image.pixelColor(x, y).alpha() == 0, path
    image = character_image()
    assert not image.isNull() and image.hasAlphaChannel()
    assert (ROOT / 'assets/robin.png').is_file()
    lib.resize(180)
    assert lib.available and len(lib.cache) == 484
    player = MotionPlayer(lib)
    player.update(.2)
    assert player.trigger('wave') and player.current == 'wave'
    assert player.elapsed == 44 / lib.fps
    player.update(.13)
    assert player.transition_from is None
    player.update(lib.duration('wave') - player.elapsed)
    assert player.current == 'idle'
    assert player.trigger('walk') and player.current == 'walk_in'
    player.update(lib.duration('walk_in') - player.elapsed)
    assert player.current == 'walk'
    player.update(.2)
    assert abs(player.travel_seconds - .2) < 1e-7
    assert player.trigger('idle') and player.current == 'idle'
    print('PASS: bundled character image, all 484 alpha frames, immediate gestures, idle return and walking')


if __name__ == '__main__':
    main()
