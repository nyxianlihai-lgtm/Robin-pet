"""Runtime motion facade backed exclusively by fixed-texture joint animation."""
from config import ROOT
from rig import DURATIONS, RigRenderer, action_pose, interpolate, still_pose


class MotionLibrary:
    def __init__(self, directory=None):
        self.available = False
        self.problem = ""
        self.interpolation_problem = ""
        self.interpolator = None  # Compatibility; optical flow is never loaded.
        self.clips = {name: {"duration": duration} for name, duration in DURATIONS.items()}
        self.still = {name: [name, 0] for name in ("neutral", "sleep", "drag", "thinking")}
        self.cache = {}
        try:
            self.renderer = RigRenderer(directory)
            self.available = True
        except (OSError, ValueError) as error:
            self.problem = str(error)

    def resize(self, height):
        if self.available:
            self.renderer.resize(height)
            self.cache = {name: self.renderer.frame(still_pose(name)) for name in self.still}

    def still_frame(self, name):
        return self.cache[name]

    def clip_frame(self, name, elapsed):
        if elapsed <= 0 or elapsed >= self.duration(name):
            return self.cache["neutral"]
        return self.renderer.frame(action_pose(name, elapsed))

    def duration(self, name):
        return DURATIONS[name]

    def blend(self, a, b, progress):
        if a == b or progress <= 0:
            return self.cache[a[0]]
        if progress >= 1:
            return self.cache[b[0]]
        return self.renderer.frame(interpolate(still_pose(a[0]), still_pose(b[0]), progress))

    def pose_for_action(self, name, elapsed):
        return action_pose(name, elapsed)

    def transition_frame(self, start, end, progress):
        a = still_pose(start) if isinstance(start, str) else start
        b = still_pose(end) if isinstance(end, str) else end
        return self.renderer.frame(interpolate(a, b, progress))

    def wait_ready(self):
        pass

    def close(self):
        pass
