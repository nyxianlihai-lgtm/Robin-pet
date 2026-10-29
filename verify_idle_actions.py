"""Check the 30-second scheduler with simulated time and actual clip orders."""
import random
from video_motion import MotionLibrary,MotionPlayer


def main():
    lib=MotionLibrary();assert lib.available,lib.problem
    p=MotionPlayer(lib,random.Random(7))
    p.update(29.99,automatic=True,roaming=True)
    assert p.current=='idle' and p.queued is None
    p.update(.01,automatic=True,roaming=False)
    assert p.current in ('wave','shy','sing','stretch') and p.idle_seconds==0
    previous=p.current
    p.update(lib.duration(p.current)-p.elapsed,automatic=True)
    assert p.current=='idle' and p.idle_seconds==0
    p.update(29.99,automatic=True);assert p.current=='idle'
    p.update(.01,automatic=True)
    assert p.current!='idle' and p.current!=previous
    p.trigger('idle');p.update(29,automatic=True)
    p.update(10,sleeping=True,automatic=True);assert p.idle_seconds==0
    p.update(29,automatic=True);assert p.current=='idle'
    p.update(1,dragging=True,automatic=True);assert p.idle_seconds==0
    p.update(29,automatic=True);p.thinking=True
    p.update(10,automatic=True);assert p.current=='idle' and p.idle_seconds==0
    p.thinking=False;p.update(29,automatic=True)
    p.trigger('wave');assert p.idle_seconds==0 and p.current=='wave'
    p.update(lib.duration('wave'),automatic=True);assert p.current=='idle'
    # Crossing the threshold by a large dt must consume only idle time first.
    p.update(30.05,automatic=True)
    assert p.current!='idle' and abs(p.elapsed-.05)<1e-6
    p.trigger('idle');p.update(120)
    assert p.current=='idle'  # Standalone previews don't enable auto actions.
    # Walk is eligible only if the desktop allows roaming and has space.
    class ChooseLast(random.Random):
        def choice(self,choices): return choices[-1]
    walk=MotionPlayer(lib,ChooseLast())
    walk.update(30,automatic=True,roaming=True)
    assert walk.current=='walk_in'
    walk.update(289/24,automatic=True,roaming=True)
    assert walk.current=='idle' and walk.idle_seconds==0
    print('PASS: exact 30s threshold; full idle interval after each action; no immediate repeats; pause/drag/thinking/manual reset; no interruption; roaming permission; previews unchanged')


if __name__=='__main__':main()
