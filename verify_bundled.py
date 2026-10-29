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
    assert lib.frame_count == 1191
    if not os.environ.get('ROBIN_PET_ASSETS') and not (ROOT / 'data/pet-assets/manifest.json').exists():
        default = MotionLibrary()
        assert default.available, default.problem
        assert default.directory == ROOT / 'assets/video2_hq'
    assert {'idle', 'wave', 'walk_in', 'walk', 'walk_out', 'shy', 'sing', 'stretch'} <= set(lib.clips)
    frame_canvas={}
    for clip in lib.clips.values():
        for index in clip['order']:frame_canvas[index]=clip.get('canvas',lib.manifest['canvas'])
    for index,path in enumerate(lib.paths):
        image = QImage(str(path))
        assert not image.isNull() and image.hasAlphaChannel(), path
        assert [image.width(), image.height()] == frame_canvas[index]
        for x, y in ((0, 0), (image.width()-1, 0), (0, image.height()-1)):
            assert image.pixelColor(x, y).alpha() == 0, path
    image = character_image()
    assert not image.isNull() and image.hasAlphaChannel()
    assert (ROOT / 'assets/robin.png').is_file()
    lib.resize(180)
    assert lib.available and len(lib.cache) == 1191
    player = MotionPlayer(lib)
    player.update(.2)
    assert player.trigger('wave') and player.current == 'wave'
    assert player.elapsed == 0
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
    assert not player.trigger('turn')
    for name in ('shy','sing','stretch'):
        assert player.trigger(name)
        player.update(lib.duration(name));assert player.current=='idle'
    assert lib.clips['walk']['cycles']==1
    print('PASS: bundled v1.2 character, all 1191 alpha frames, immediate actions, idle return, full walk and new actions')


if __name__ == '__main__':
    main()
