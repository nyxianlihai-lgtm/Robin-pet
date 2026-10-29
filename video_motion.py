"""Play the actual keyed video frames. No rig, synthetic gestures, or flow."""
import json
import random
import os
import math
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from config import ROOT
from frame_cache import FrameCache


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
        self.render_width = 0
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
                # Repair the known legacy sequences only. Future user packs
                # retain their own timing and independently generated gait.
                wave = self.clips.get("wave", {})
                legacy_wave = list(range(363, 484)) + list(range(482, 363, -1))
                if wave.get("order") == legacy_wave:
                    wave["order"] = list(range(407, 446)) + list(range(444, 406, -1))
                    wave["entry_frame"] = 0
                walk = self.clips.get("walk", {})
                if walk.get("order") == list(range(132, 213)):
                    # Raw walk frame 54 jumps in position and pose. Use a
                    # matched full stride entirely before that discontinuity.
                    walk["order"] = list(range(134, 162))
            self.order = self.clips["idle"]["order"]
            self.anchor = self.manifest["anchor"]
            self.bounds = self.manifest["bounds"]
            self.frame_offsets = {}
            self.horizontal_padding = float(self.manifest.get("horizontal_padding", 0))
            if not math.isfinite(self.horizontal_padding) or not 0 <= self.horizontal_padding <= 1000:
                raise ValueError("动画水平留白参数不正确。")
            if not (1 <= self.fps <= 120 and 1 <= self.frame_count <= 3000 and self.order):
                raise ValueError("视频帧数或帧率不正确。")
            for clip in self.clips.values():
                if not clip["order"] or any(type(index) is not int or not 0 <= index < self.frame_count for index in clip["order"]):
                    raise ValueError("视频循环索引不正确。")
                if clip["next"] not in self.clips:
                    raise ValueError("视频动作接续不存在。")
                if type(clip.get("cycles", 2)) is not int or not 1 <= clip.get("cycles", 2) <= 8:
                    raise ValueError("散步循环次数不正确。")
                origin = clip.get("frame_offset", [0, 0])
                if (len(origin) != 2 or any(type(x) not in (int,float) or not math.isfinite(x)
                                           or abs(x) > 5000 for x in origin)):
                    raise ValueError("动画画布偏移不正确。")
                if origin != [0, 0]:
                    for index in clip["order"]:
                        self.frame_offsets[index] = origin
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
        self.cache.clear()
        scale = min((height - 12) / (self.bounds[3] - self.bounds[1]),
                    (height - 12) / (self.bounds[2] - self.bounds[0]))
        self.render_width = height + 2 * math.ceil(self.horizontal_padding * scale)
        ratio = max(1.0, float(device_pixel_ratio))

        def render(index):
            path = self.paths[index]
            image = QImage(str(path))
            if image.isNull() or not image.hasAlphaChannel():
                raise ValueError("透明视频帧读取失败：" + path.name)
            image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            pixmap = QPixmap(round(self.render_width * ratio), round(height * ratio))
            if pixmap.isNull():
                raise ValueError("动作图像缓存分配失败，请缩小桌宠尺寸后重新加载动作。")
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            origin = self.frame_offsets.get(index, (0, 0))
            painter.drawImage(QRectF(self.render_width / 2 + (origin[0] - self.anchor[0]) * scale,
                                    height - 5 + (origin[1] - self.anchor[1]) * scale,
                                    image.width() * scale, image.height() * scale), image)
            painter.end()
            return pixmap

        self.cache = FrameCache(len(self.paths), render, self._frame_error)
        self.cache[self.order[0]]
        if self.available:
            self.cache.prefetch(self.order[1:9])

    def _frame_error(self, message):
        self.available = False
        self.problem = message

    def duration(self, name="idle"):
        return len(self.clips[name]["order"]) / self.fps

    def source_index(self, elapsed, name="idle"):
        order = self.clips[name]["order"]
        return order[int(max(0, elapsed) * self.fps + 1e-7) % len(order)]

    def clip_frame(self, name, elapsed):
        order = self.clips[name]["order"]
        position = int(max(0, elapsed) * self.fps + 1e-7) % len(order)
        frame = self.cache[order[position]]
        if isinstance(self.cache, FrameCache) and self.available:
            upcoming = [order[(position+i) % len(order)] for i in range(1,9)]
            self.cache.prefetch(upcoming)
        return frame

    def still_frame(self, name="neutral"):
        return self.cache[self.order[0]]

    def wait_ready(self):
        pass

    def close(self):
        self.cache.clear()


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
        self.idle_seconds = 0.0
        self.last_auto_action = None

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
        self.idle_seconds = 0.0
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
        if target not in self.library.clips or target not in ("wave", "walk_in", "shy", "sing", "stretch"):
            return False
        # Explicit interactions take effect now, including while another action
        # is playing. Blend whole frames briefly; never stitch or warp limbs.
        self._start(target)
        return True

    def stop_walk(self):
        self.stop_requested = True

    def _automatic_action(self, roaming):
        choices = [name for name in ("wave", "shy", "sing", "stretch") if name in self.library.clips]
        if roaming and "walk_in" in self.library.clips:
            choices.append("walk_in")
        if len(choices) > 1:
            choices = [name for name in choices if name != self.last_auto_action]
        self.idle_seconds = 0.0
        if choices:
            target = self.rng.choice(choices)
            self._start(target)
            self.last_auto_action = target

    def update(self, dt, sleeping=False, dragging=False, roaming=False, automatic=False):
        self.mode = "drag" if dragging else "sleep" if sleeping else "idle"
        self.travel_seconds = 0.0
        if not self.library.available or sleeping or dragging:
            self.idle_seconds = 0.0
            return
        if self.thinking:
            self.idle_seconds = 0.0
        self.transition_elapsed += max(0.0, dt)
        if self.transition_elapsed >= self.transition_duration:
            self.transition_from = None
        remaining = max(0.0, dt)
        self.roam_after -= remaining
        if (not automatic and roaming and "walk_in" in self.library.clips and self.roam_after <= 0
                and self.current == "idle" and self.queued is None):
            self.queued = "walk_in"
        while remaining > 1e-9:
            step = min(remaining, self.library.duration(self.current) - self.elapsed)
            counting_idle = automatic and not self.thinking and self.current == "idle"
            if counting_idle:
                step = min(step, max(0.0, 30.0 - self.idle_seconds))
            if self.current == "walk":
                self.travel_seconds += step
            self.elapsed += step
            remaining -= step
            if counting_idle:
                self.idle_seconds += step
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
                    if self.stop_requested or self.walk_cycles >= self.library.clips["walk"].get("cycles", 2):
                        following = "walk_out"
                self.current = following
                self.action = None if following == "idle" else following
                self.elapsed = 0.0
                if previous == "wave" and following == "idle":
                    # The shortened greeting ends on a real idle source frame.
                    # Resume at that exact pose rather than snapping to idle[0].
                    last = self.library.clips[previous]["order"][-1]
                    idle_order = self.library.clips["idle"]["order"]
                    if last in idle_order:
                        self.elapsed = idle_order.index(last) / self.library.fps
                if following == "idle" and self.library.clips[previous].get("blend_to_idle") and self.library.cache:
                    last = self.library.clips[previous]["order"][-1]
                    self.transition_from = self.library.cache[last]
                    self.transition_elapsed = 0.0
                if following == "idle" and previous != "idle":
                    self.idle_seconds = 0.0
                    self.roam_after = self.rng.uniform(22, 38)
            if automatic and not self.thinking and self.current == "idle" and self.idle_seconds >= 30.0 - 1e-9:
                self._automatic_action(roaming)

    @property
    def label(self):
        return "已暂停" if self.mode == "sleep" else {
            "idle": "视频待机", "wave": "抬手招呼", "turn": "转身查看",
            "walk_in": "准备散步", "walk": "向左散步", "walk_out": "散步结束",
            "shy": "害羞回应", "sing": "唱歌", "stretch": "困困伸懒腰"
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
        # Qt raster opacity uses 8-bit weights and division by 256. Choose
        # complementary integer contributions so opaque pixels stay opaque.
        incoming_weight = round(amount * 255)
        painter.setOpacity((256 - incoming_weight) / 256)
        painter.drawPixmap(0, 0, self.transition_from)
        # Qt applies constant opacity after the saturated Plus operation.
        # Weight the incoming image on its own transparent surface first;
        # then add both premultiplied images at full painter opacity. Applying
        # opacity directly to Plus brightens RGB and drops alpha (white flash).
        incoming = QPixmap(current.size())
        incoming.setDevicePixelRatio(current.devicePixelRatio())
        incoming.fill(Qt.GlobalColor.transparent)
        incoming_painter = QPainter(incoming)
        incoming_painter.setOpacity((incoming_weight + 1) / 256)
        incoming_painter.drawPixmap(0, 0, current)
        incoming_painter.end()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setOpacity(1)
        painter.drawPixmap(0, 0, incoming)
        painter.end()
        return blended
