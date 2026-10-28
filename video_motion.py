"""Play the actual keyed video frames. No rig, synthetic gestures, or flow."""
import json
import random
import os
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from config import ROOT


class MotionLibrary:
    video_mode = True

    def __init__(self, directory=None):
        requested = directory if directory is not None else os.environ.get("ROBIN_PET_ASSETS")
        self.directory = Path(requested) if requested is not None else ROOT / "data" / "pet-assets"
        # Custom local packs take precedence over the bundled default character.
        if requested is None and not (self.directory / "manifest.json").is_file():
            bundled = ROOT / "assets" / "video2_hq"
            if (bundled / "manifest.json").is_file():
                self.directory = bundled
        self.available = False
        self.problem = ""
        self.interpolation_problem = ""
        self.interpolator = None
        self.cache = []
        self.clips = {"idle": {}}
        try:
            self.manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
            if self.manifest["version"] not in (1, 2):
                raise ValueError("不支持的视频动作格式。")
            self.fps = float(self.manifest["fps"])
            self.frame_count = int(self.manifest["frames"])
            self.clips = self.manifest.get("clips") or {"idle": {"order": self.manifest["order"], "next": "idle"}}
            if self.manifest.get("revision") == "hq-enclosed-iris":
                # Preserve entry timing for pre-existing private local packs.
                for name, offset in (("wave", 44), ("turn", 20), ("walk_in", 20)):
                    if name in self.clips:
                        self.clips[name].setdefault("entry_frame", offset)
            self.order = self.clips["idle"]["order"]
            self.anchor = self.manifest["anchor"]
            self.bounds = self.manifest["bounds"]
            if not (1 <= self.fps <= 120 and 1 <= self.frame_count <= 3000 and self.order):
                raise ValueError("视频帧数或帧率不正确。")
            for clip in self.clips.values():
                if not clip["order"] or any(type(index) is not int or not 0 <= index < self.frame_count for index in clip["order"]):
                    raise ValueError("视频循环索引不正确。")
                if clip["next"] not in self.clips:
                    raise ValueError("视频动作接续不存在。")
            self.paths = []
            for index in range(self.frame_count):
                path = (self.directory / self.manifest["pattern"].format(index=index)).resolve()
                if not path.is_relative_to(self.directory.resolve()) or not path.is_file():
                    raise ValueError("视频帧路径不存在或超出素材目录。")
                self.paths.append(path)
            self.available = True
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            self.problem = str(error)

    def resize(self, height, device_pixel_ratio=1.0):
        if not self.available:
            return
        rendered = []
        scale = min((height - 12) / (self.bounds[3] - self.bounds[1]),
                    (height - 12) / (self.bounds[2] - self.bounds[0]))
        for path in self.paths:
            image = QImage(str(path))
            if image.isNull() or not image.hasAlphaChannel():
                self.available = False
                self.problem = "透明视频帧读取失败：" + path.name
                self.cache.clear()
                return
            ratio = max(1.0, float(device_pixel_ratio))
            pixmap = QPixmap(round(height * ratio), round(height * ratio))
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(QRectF(height / 2 - self.anchor[0] * scale,
                                    height - 5 - self.anchor[1] * scale,
                                    image.width() * scale, image.height() * scale), image)
            painter.end()
            rendered.append(pixmap)
        self.cache = rendered

    def duration(self, name="idle"):
        return len(self.clips[name]["order"]) / self.fps

    def source_index(self, elapsed, name="idle"):
        order = self.clips[name]["order"]
        return order[int(max(0, elapsed) * self.fps + 1e-7) % len(order)]

    def clip_frame(self, name, elapsed):
        return self.cache[self.source_index(elapsed, name)]

    def still_frame(self, name="neutral"):
        return self.cache[self.order[0]]

    def wait_ready(self):
        pass

    def close(self):
        pass


class MotionPlayer:
    video_mode = True

    def __init__(self, library, rng=None):
        self.library = library
        self.elapsed = 0.0
        self.action = None
        self.mode = "idle"
        self.thinking = False
        self.queued = None
        self.pose_transition = None
        self.current = "idle"
        self.rng = rng or random.Random()
        self.roam_after = 22.0
        self.walk_cycles = 0
        self.stop_requested = False
        self.travel_seconds = 0.0
        self.transition_from = None
        self.transition_elapsed = 0.0
        self.transition_duration = .12

    def _start(self, target):
        previous_frame = self.frame() if self.library.cache else None
        self.current = target
        self.action = None if target == "idle" else target
        # These clips contain a long static lead-in. Enter just before motion.
        entry = self.library.clips[target].get("entry_frame", 0)
        self.elapsed = min(entry / self.library.fps, self.library.duration(target) - 1 / self.library.fps)
        self.queued = None
        self.stop_requested = False
        self.travel_seconds = 0.0
        self.walk_cycles = 0
        self.roam_after = self.rng.uniform(22, 38)
        self.transition_from = previous_frame
        self.transition_elapsed = 0.0

    def trigger(self, action, force=False):
        if not self.library.available:
            return False
        if action == "idle":
            self._start("idle")
            return True
        target = {"walk": "walk_in"}.get(action, action)
        if target not in self.library.clips or target not in ("wave", "turn", "walk_in"):
            return False
        # Explicit interactions take effect now, including while another action
        # is playing. Blend whole frames briefly; never stitch or warp limbs.
        self._start(target)
        return True

    def stop_walk(self):
        self.stop_requested = True

    def update(self, dt, sleeping=False, dragging=False, roaming=False):
        self.mode = "drag" if dragging else "sleep" if sleeping else "idle"
        self.travel_seconds = 0.0
        if not self.library.available or sleeping or dragging:
            return
        self.transition_elapsed += max(0.0, dt)
        if self.transition_elapsed >= self.transition_duration:
            self.transition_from = None
        remaining = max(0.0, dt)
        self.roam_after -= remaining
        if (roaming and "walk_in" in self.library.clips and self.roam_after <= 0
                and self.current == "idle" and self.queued is None):
            self.queued = "walk_in"
        while remaining > 1e-9:
            step = min(remaining, self.library.duration(self.current) - self.elapsed)
            if self.current == "walk":
                self.travel_seconds += step
            self.elapsed += step
            remaining -= step
            if self.elapsed + 1e-9 >= self.library.duration(self.current):
                previous = self.current
                following = self.library.clips[previous]["next"]
                if previous == "idle" and self.queued:
                    following, self.queued = self.queued, None
                if previous == "walk_in":
                    self.walk_cycles = 0
                    self.stop_requested = False
                if previous == "walk":
                    self.walk_cycles += 1
                    if self.stop_requested or self.walk_cycles >= 2:
                        following = "walk_out"
                self.current = following
                self.action = None if following == "idle" else following
                self.elapsed = 0.0
                if following == "idle" and previous != "idle":
                    self.roam_after = self.rng.uniform(22, 38)

    @property
    def label(self):
        return "已暂停" if self.mode == "sleep" else {
            "idle": "视频待机", "wave": "抬手招呼", "turn": "转身查看",
            "walk_in": "准备散步", "walk": "向左散步", "walk_out": "散步结束"
        }[self.current]

    def frame(self):
        current = self.library.clip_frame(self.current, self.elapsed)
        if self.transition_from is None:
            return current
        amount = min(1.0, self.transition_elapsed / self.transition_duration)
        if amount <= 0:
            return self.transition_from
        blended = QPixmap(current.size())
        blended.setDevicePixelRatio(current.devicePixelRatio())
        blended.fill(Qt.GlobalColor.transparent)
        painter = QPainter(blended)
        painter.setOpacity(1 - amount)
        painter.drawPixmap(0, 0, self.transition_from)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setOpacity(amount)
        painter.drawPixmap(0, 0, current)
        painter.end()
        return blended
