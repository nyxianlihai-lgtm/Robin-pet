"""Continuous, fixed-texture 2D arm rig. No frame morphing or optical flow."""
from dataclasses import dataclass, fields
import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap

from config import ROOT


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * t * (t * (t * 6 - 15) + 10)


@dataclass(frozen=True)
class Pose:
    left_upper: float = 38.0
    right_upper: float = -38.0
    left_elbow: float = 0.0
    right_elbow: float = 0.0
    eyelids: float = 0.0
    lean: float = 0.0


def interpolate(a, b, t):
    t = ease(t)
    return Pose(**{field.name: getattr(a, field.name) * (1 - t) + getattr(b, field.name) * t
                   for field in fields(Pose)})


DURATIONS = {"blink": 0.30, "wave": 2.8, "pat": 2.3, "glance": 1.8}


def envelope(at, duration, rise, fall):
    return ease(at / rise) * ease((duration - at) / fall)


def action_pose(action, at):
    duration = DURATIONS[action]
    if at <= 0 or at >= duration:
        return Pose()
    if action == "blink":
        closure = ease(at / 0.075) if at < 0.075 else 1 - ease((at - 0.12) / 0.18)
        return Pose(eyelids=closure)
    if action == "wave":
        weight = envelope(at, duration, 0.7, 0.75)
        # One shoulder lift, then a continuous forearm oscillation, then settle.
        wrist = math.sin((at - 0.7) * math.tau * 1.55) * 8 * weight
        return Pose(left_upper=38 + 72 * weight, left_elbow=22 * weight + wrist)
    if action == "pat":
        weight = envelope(at, duration, 0.65, 0.8)
        return Pose(left_upper=38 + 62 * weight, right_upper=-38 - 62 * weight,
                    left_elbow=70 * weight, right_elbow=-70 * weight, eyelids=weight)
    weight = math.sin(math.pi * at / duration) ** 2
    return Pose(lean=1.3 * weight)


def still_pose(name):
    if name == "sleep":
        return Pose(eyelids=1)
    if name == "drag":
        return Pose(left_upper=62, right_upper=-62, left_elbow=12, right_elbow=-12)
    if name == "thinking":
        return Pose(left_upper=50, left_elbow=35)
    return Pose()


def alpha_bounds(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    raw = bytes(image.constBits())
    width, stride = image.width(), image.bytesPerLine()
    rows = []
    for y in range(image.height()):
        xs = [x for x, alpha in enumerate(raw[y * stride + 3:y * stride + width * 4:4]) if alpha >= 160]
        if len(xs) >= 4:
            rows.append((y, min(xs), max(xs)))
    if not rows:
        raise ValueError("角色图层为空。")
    return min(x for _, x, _ in rows), rows[0][0], max(x for _, _, x in rows), rows[-1][0]


class RigRenderer:
    def __init__(self, directory=None):
        self.directory = directory or ROOT / "assets" / "rig"
        self.body = QPixmap(str(self.directory / "body.png"))
        self.closed = QPixmap(str(self.directory / "eyes-closed.png"))
        arms = QPixmap(str(self.directory / "arms.png"))
        if any(image.isNull() or not image.hasAlphaChannel() for image in (self.body, self.closed, arms)):
            raise ValueError("缺少透明角色图层，请检查 assets/rig。")
        self.closed = self.closed.scaled(self.body.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
        self.arms = [arms.copy(0, 0, arms.width() // 2, arms.height()),
                     arms.copy(arms.width() // 2, 0, arms.width() - arms.width() // 2, arms.height())]
        self.bounds = alpha_bounds(self.body.toImage())
        self.width, self.height = self.body.width(), self.body.height()
        self.size = 280
        self.eye_path = QPainterPath()
        # Only these tiny patches may change during a blink. The rest of the
        # head, face, hair and costume always use exactly the same body texture.
        for rect in (QRectF(426, 521, 151, 116), QRectF(641, 519, 151, 118)):
            self.eye_path.addRoundedRect(rect, 30, 23)
        self.shoulders = QPainterPath()
        self.shoulders.moveTo(402, 753)
        for x, y in ((451, 736), (515, 775), (512, 816), (491, 854), (445, 842), (399, 817)):
            self.shoulders.lineTo(x, y)
        self.shoulders.closeSubpath()
        self.shoulders.moveTo(831, 753)
        for x, y in ((782, 736), (718, 775), (721, 816), (742, 854), (788, 842), (834, 817)):
            self.shoulders.lineTo(x, y)
        self.shoulders.closeSubpath()

    def resize(self, size):
        self.size = size

    def draw_arm(self, painter, side, upper_angle, elbow_angle):
        image = self.arms[side]
        sx, sy = image.width() / 768, image.height() / 1024
        root = (465 * sx, 170 * sy) if side == 0 else (300 * sx, 170 * sy)
        elbow = (418 * sx, 422 * sy) if side == 0 else (344 * sx, 422 * sy)
        natural_angle = math.degrees(math.atan2(-(elbow[0] - root[0]) * 1.6, elbow[1] - root[1]))
        body_root = (457, 814) if side == 0 else (776, 814)
        painter.save()
        painter.translate(*body_root)
        painter.rotate(upper_angle - natural_angle)
        # Sheet-to-body scale: keep both arms at the same physical length.
        painter.scale(0.205 * 1.6 / sx, 0.205 / sy)
        painter.translate(-root[0], -root[1])
        painter.save()
        painter.setClipRect(QRectF(0, 0, image.width(), 407 * sy))
        painter.drawPixmap(0, 0, image)
        painter.restore()
        painter.translate(*elbow)
        painter.rotate(elbow_angle)
        painter.translate(-elbow[0], -elbow[1])
        painter.setClipRect(QRectF(0, 390 * sy, image.width(), image.height() - 390 * sy))
        painter.drawPixmap(0, 0, image)
        painter.restore()

    def frame(self, pose=Pose()):
        result = QPixmap(self.size, self.size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        _, top, _, bottom = self.bounds
        scale = (self.size - 12) / (bottom - top + 1)
        painter.translate(self.size / 2, self.size - 5)
        painter.rotate(pose.lean)
        painter.scale(scale, scale)
        painter.translate(-self.width / 2, -bottom)
        painter.drawPixmap(0, 0, self.body)
        self.draw_arm(painter, 0, pose.left_upper, pose.left_elbow)
        self.draw_arm(painter, 1, pose.right_upper, pose.right_elbow)
        painter.save()
        painter.setClipPath(self.shoulders)
        painter.drawPixmap(0, 0, self.body)
        painter.restore()
        # A local two-pose blink avoids semi-visible irises under closed lashes.
        # Only the eyes change; there is no full-head dissolve or deformation.
        if pose.eyelids >= 0.5:
            painter.save()
            painter.setClipPath(self.eye_path)
            painter.drawPixmap(0, 0, self.closed)
            painter.restore()
        painter.end()
        return result
