"""Event priorities and timing for fixed-layer character animation."""
import random


class MotionPlayer:
    def __init__(self, library, rng=None):
        self.library = library
        self.random = rng or random.Random()
        self.elapsed = 0.0
        self.action = None
        self.queued = None
        self.mode = "idle"
        self._thinking = False
        self.pose_transition = None
        self.pose_elapsed = 0.0
        self.blink_in = self.random.uniform(2.8, 4.8)
        self.gesture_in = self.random.uniform(13, 22)

    @property
    def thinking(self):
        return self._thinking

    @thinking.setter
    def thinking(self, value):
        value = bool(value)
        if value != self._thinking and self.mode == "idle" and self.action is None:
            self.pose_transition = ("thinking" if self._thinking else "neutral",
                                    "thinking" if value else "neutral")
            self.pose_elapsed = 0
        self._thinking = value

    def trigger(self, action, force=False):
        if not self.library.available or action not in self.library.clips:
            return False
        if self.action and force:
            self.queued = action
            return True
        # Repeated clicks must not keep restarting the first pose.
        if self.action and self.action not in ("blink", "glance") and not force:
            return False
        if self.mode in ("sleep", "drag") and not force:
            return False
        self.mode = "idle"
        self.pose_transition = None
        self.action = action
        self.elapsed = 0.0
        if action != "blink":
            self.gesture_in = self.random.uniform(13, 22)
        return True

    def update(self, dt, sleeping=False, dragging=False, roaming=False):
        if not self.library.available:
            return
        target = "drag" if dragging else "sleep" if sleeping else "idle"
        if target != self.mode:
            old_pose = self.mode if self.mode != "idle" else "thinking" if self.thinking else "neutral"
            if self.action:
                old_pose = self.library.pose_for_action(self.action, self.elapsed)
            new_pose = target if target != "idle" else "thinking" if self.thinking else "neutral"
            self.pose_transition = old_pose, new_pose
            self.pose_elapsed = 0
            self.action, self.elapsed = None, 0
            self.queued = None
            self.mode = target
            self.blink_in = self.random.uniform(1.5, 3)
        if self.pose_transition:
            self.pose_elapsed += dt
            if self.pose_elapsed >= 0.18:
                self.pose_transition = None
            else:
                return
        if self.mode != "idle":
            return
        if self.action:
            self.elapsed += dt
            if self.elapsed >= self.library.duration(self.action):
                finished = self.action
                self.action, self.elapsed = None, 0
                if finished == "blink":
                    self.blink_in = self.random.uniform(2.8, 5.8)
                else:
                    self.blink_in = self.random.uniform(1, 2.2)
                if self.thinking:
                    self.pose_transition = "neutral", "thinking"
                    self.pose_elapsed = 0
                if self.queued:
                    queued, self.queued = self.queued, None
                    self.trigger(queued)
            return
        self.blink_in -= dt
        self.gesture_in -= dt
        if self.blink_in <= 0:
            self.trigger("blink")
        elif self.gesture_in <= 0 and not roaming and not self.thinking:
            self.trigger("glance" if self.random.random() < 0.7 else "wave")

    @property
    def label(self):
        if self.mode == "sleep":
            return "小憩"
        if self.mode == "drag":
            return "被提起来啦"
        return {"blink": "眨眨眼", "wave": "挥手", "pat": "摸头回应", "glance": "看看你"}.get(
            self.action, "想一想" if self.thinking else "陪伴中")

    def frame(self):
        if self.pose_transition:
            start, end = self.pose_transition
            t = min(1, self.pose_elapsed / 0.18)
            t = t * t * (3 - 2 * t)
            return self.library.transition_frame(start, end, t)
        if self.mode in ("sleep", "drag"):
            return self.library.still_frame(self.mode)
        if self.action:
            return self.library.clip_frame(self.action, self.elapsed)
        return self.library.still_frame("thinking" if self.thinking else "neutral")
