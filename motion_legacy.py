"""Aligned sprite sheets and an elapsed-time animation state machine.

Frames are sliced in memory. Source artwork stays intact. The same cached image
is reused on every paint; resizing rebuilds only the display-size cache.
"""
from dataclasses import dataclass
import json
import random
import statistics

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from config import ROOT


@dataclass
class SourceFrame:
    image: QImage
    top: int
    bottom: int
    anchor_x: float


def locate_frame(image):
    """Find a foot anchor from substantial alpha, ignoring isolated edge specks."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    raw = bytes(image.constBits())
    stride = image.bytesPerLine()
    rows = []
    for y in range(height):
        alpha = raw[y * stride + 3:y * stride + width * 4:4]
        xs = [x for x, value in enumerate(alpha) if value >= 160]
        if len(xs) >= 4:
            rows.append((y, xs[0], xs[-1]))
    if not rows:
        raise ValueError("动画帧为空，或没有有效透明通道。")
    top, bottom = rows[0][0], rows[-1][0]
    # Foot-region centers stay stable when the head/hair/hands move sideways.
    foot_rows = [row for row in rows if row[0] >= bottom - max(8, (bottom - top) * 0.12)]
    anchor = statistics.median((left + right) / 2 for _, left, right in foot_rows)
    return SourceFrame(image, top, bottom, anchor)


class MotionLibrary:
    def __init__(self, directory=None):
        self.directory = directory or ROOT / "assets" / "motions"
        self.available = False
        self.problem = ""
        self.frames = {}
        self.scaled = {}
        self.clips = {}
        self.still = {}
        self.interpolator = None
        self.interpolation_height = None
        self.display_height = 280
        self.interpolation_problem = ""
        try:
            manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("version") != 1:
                raise ValueError("动画配置版本不受支持。")
            cols, rows = manifest["grid"]
            if not (1 <= cols <= 16 and 1 <= rows <= 16):
                raise ValueError("动画网格尺寸不正确。")
            for name, filename in manifest["sheets"].items():
                path = (self.directory / filename).resolve()
                if not path.is_relative_to(self.directory.resolve()):
                    raise ValueError("动画路径超出素材目录。")
                image = QImage(str(path))
                if image.isNull() or not image.hasAlphaChannel():
                    raise ValueError(f"动画素材无效：{filename}")
                cells = []
                for index in range(cols * rows):
                    column, row = index % cols, index // cols
                    x0, x1 = round(column * image.width() / cols), round((column + 1) * image.width() / cols)
                    y0, y1 = round(row * image.height() / rows), round((row + 1) * image.height() / rows)
                    cells.append(locate_frame(image.copy(x0, y0, x1 - x0, y1 - y0)))
                self.frames[name] = cells
            self.clips = manifest["clips"]
            self.still = manifest["still"]
            for clip in self.clips.values():
                if not clip["frames"]:
                    raise ValueError("动画片段没有帧。")
                for index, duration in clip["frames"]:
                    if not (0 <= index < len(self.frames[clip["sheet"]]) and 20 <= duration <= 5000):
                        raise ValueError("动画索引或帧时长无效。")
            for name in ("neutral", "sleep", "drag", "thinking"):
                sheet, index = self.still[name]
                self.frames[sheet][index]
            self.available = True
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            self.problem = str(error)
            self.frames.clear()

    def resize(self, height):
        if not self.available:
            return
        self.display_height = height
        self.scaled = self._render_frames(height)
        if self.interpolation_height != height and not self.interpolation_problem:
            try:
                from tween import FlowInterpolator
                if self.interpolator:
                    self.interpolator.close()
                self.interpolator = FlowInterpolator(self.scaled)
                self.interpolation_height = height
                pairs = []
                neutral = tuple(self.still["neutral"])
                for clip in self.clips.values():
                    keys = [neutral, *[(clip["sheet"], index) for index, _ in clip["frames"]], neutral]
                    pairs.extend(zip(keys, keys[1:]))
                for a in self.still.values():
                    for b in self.still.values():
                        pairs.append((tuple(a), tuple(b)))
                self.interpolator.prepare(pairs)
            except ImportError as error:
                self.interpolation_problem = str(error)

    def _render_frames(self, height):
        rendered = {}
        for sheet, frames in self.frames.items():
            # A fixed scale per sheet preserves in-frame movement. Scaling every
            # frame independently would make a nod inflate and shrink the body.
            nominal_height = statistics.median(frame.bottom - frame.top + 1 for frame in frames)
            scale = (height - 12) / nominal_height
            for index, frame in enumerate(frames):
                pixmap = QPixmap(height, height)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                target = QRectF(height / 2 - frame.anchor_x * scale,
                                height - 5 - frame.bottom * scale,
                                frame.image.width() * scale, frame.image.height() * scale)
                painter.drawImage(target, frame.image)
                painter.end()
                rendered[sheet, index] = pixmap
        return rendered

    def still_frame(self, name):
        return self.scaled[tuple(self.still[name])]

    def raw_clip_frame(self, name, elapsed):
        clip = self.clips[name]
        remaining = elapsed * 1000
        for index, duration in clip["frames"]:
            if remaining < duration:
                return self.scaled[clip["sheet"], index]
            remaining -= duration
        index = clip["frames"][-1][0]
        return self.scaled[clip["sheet"], index]

    def blend(self, a, b, progress):
        if a == b or progress <= 0:
            return self.scaled[a]
        if progress >= 1:
            return self.scaled[b]
        if self.interpolator is None:
            return self.scaled[a if progress < 0.5 else b]
        return self.interpolator.frame(a, b, progress)

    def clip_frame(self, name, elapsed):
        clip = self.clips[name]
        previous = tuple(self.still["neutral"])
        remaining = max(0, elapsed) * 1000
        frames = clip["frames"]
        for position, (index, duration) in enumerate(frames):
            current = clip["sheet"], index
            if remaining < duration:
                progress = remaining / duration
                # Ease the lift and return; the middle of a gesture keeps moving.
                if position <= 1 or position == len(frames) - 1:
                    progress = progress * progress * (3 - 2 * progress)
                return self.blend(previous, current, progress)
            remaining -= duration
            previous = current
        exit_ms = clip.get("exit_ms", 160)
        progress = min(1, remaining / max(1, exit_ms))
        progress = progress * progress * (3 - 2 * progress)
        return self.blend(previous, tuple(self.still["neutral"]), progress)

    def duration(self, name):
        clip = self.clips[name]
        return (sum(duration for _, duration in clip["frames"]) + clip.get("exit_ms", 160)) / 1000

    def wait_ready(self):
        if self.interpolator:
            self.interpolator.wait_ready()

    def close(self):
        if self.interpolator:
            self.interpolator.close()


class MotionPlayer:
    def __init__(self, library, rng=None):
        self.library = library
        self.random = rng or random.Random()
        self.elapsed = 0.0
        self.action = None
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
            new_pose = target if target != "idle" else "thinking" if self.thinking else "neutral"
            self.pose_transition = old_pose, new_pose
            self.pose_elapsed = 0
            self.action, self.elapsed = None, 0
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
            return self.library.blend(tuple(self.library.still[start]), tuple(self.library.still[end]), t)
        if self.mode in ("sleep", "drag"):
            return self.library.still_frame(self.mode)
        if self.action:
            return self.library.clip_frame(self.action, self.elapsed)
        return self.library.still_frame("thinking" if self.thinking else "neutral")
