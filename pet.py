"""Transparent pet window with aligned character animation and local interaction."""
import math
import random
import time

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from config import APP_TITLE, ROOT
from motion import MotionLibrary, MotionPlayer
from ui_assets import character_image


class Pet(QWidget):
    open_panel = Signal()
    preferences_changed = Signal(dict)
    quit_requested = Signal()

    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.source = character_image()
        self.motion_library = MotionLibrary()
        self.motion = MotionPlayer(self.motion_library)
        self.settings = settings.copy()
        self.asleep = False
        self.hidden_by_user = False
        self.drag_offset = None
        self.press_at = None
        self.dragged = False
        self.message = "双击我聊天 · 右键打开菜单"
        self.message_until = time.monotonic() + 9
        self.happy_until = 0
        self.phase = 0
        self.direction = random.choice((-1, 1))
        self.last_frame = time.monotonic()
        self.walk_x = None
        self.last_greeting = 0
        self.resize_pet(settings["size"])
        self.apply_topmost(settings["topmost"])
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def screen_bounds(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        return screen.availableGeometry()

    def clamp(self):
        area = self.screen_bounds()
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))
        self.walk_x = float(self.x())

    def home(self):
        area = self.screen_bounds()
        self.move(area.right() - self.width() - 36, area.bottom() - self.height() - 12)
        self.clamp()
        self.reveal()

    def reveal(self):
        self.hidden_by_user = False
        self.show()
        self.raise_()

    def toggle_visible(self):
        if self.isVisible():
            self.hidden_by_user = True
            self.hide()
        else:
            self.reveal()

    def resize_pet(self, height):
        previous_bottom = self.y() + self.height()
        self.settings["size"] = height
        self.sprite = self.source.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
        self.motion_library.resize(height, self.devicePixelRatioF())
        self.setFixedSize(max(280, self.sprite.width() + 32), height + 100)
        self.move(self.x(), previous_bottom - self.height())
        self.clamp()

    def event(self, event):
        if event.type() == QEvent.Type.DevicePixelRatioChange and hasattr(self, "settings"):
            self.motion_library.resize(self.settings["size"], self.devicePixelRatioF())
            self.update()
        return super().event(event)

    def apply_topmost(self, value):
        self.settings["topmost"] = value
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, value)
        if visible:
            self.show()

    def say(self, text, seconds=5):
        self.message = text[:58] + ("…" if len(text) > 58 else "")
        self.message_until = time.monotonic() + seconds
        self.update()

    def interact(self, action="pat"):
        self.asleep = False
        self.motion.update(0, sleeping=False, dragging=False)
        self.motion.trigger("wave")
        self.happy_until = time.monotonic() + 2.2
        self.say(random.choice(("收到一份摸摸，谢谢你 ♡", "今天也要照顾好自己呀。", "我在这里，随时陪你聊聊。", "把好心情分给你一点点 ♪")))

    def preview_action(self, action):
        self.asleep = False
        self.motion.update(0, sleeping=False, dragging=False)
        if self.motion.trigger(action, force=True):
            self.say({"wave": "向你打个招呼 ♪", "turn": "转过来看看。", "walk": "出去散散步。",
                      "idle": "恢复待机，陪着你。"}.get(action, "正在播放动作。"))
        else:
            self.say("还没有这个动作的视频素材。")

    def set_thinking(self, thinking):
        self.motion.thinking = thinking

    def toggle_sleep(self):
        self.asleep = not self.asleep
        self.say("待机视频已暂停，再点一次继续。" if self.asleep else "继续播放啦。")

    def tick(self):
        now = time.monotonic()
        delta = min(0.1, now - self.last_frame)
        self.last_frame = now
        if not self.isVisible():
            return
        area = self.screen_bounds()
        # Leave room to finish a gait cycle before reaching the screen edge.
        stride = self.motion_library.walk_stride(self.settings["size"]) if "walk" in self.motion_library.clips else 0
        near_left = self.x() <= area.left() + stride + 2
        if near_left:
            self.motion.stop_walk()
        self.motion.update(delta, sleeping=self.asleep,
                           dragging=self.drag_offset is not None and self.dragged,
                           roaming=self.settings["wander"] and not near_left)
        if not self.asleep:
            self.phase += delta
        if self.motion.travel_seconds > 0 and not self.asleep and self.drag_offset is None:
            left = area.left()
            if self.walk_x is None:
                self.walk_x = float(self.x())
            self.walk_x = max(left, self.walk_x - stride * self.motion.travel_cycles)
            self.move(round(self.walk_x), self.y())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        now = time.monotonic()
        bob = 0
        sway = 0
        sprite = self.motion.frame() if self.motion_library.available else self.sprite
        painter.save()
        logical_size = sprite.deviceIndependentSize()
        painter.translate(self.width() / 2, 88 + logical_size.height() / 2 + bob)
        painter.rotate(sway)
        painter.drawPixmap(round(-logical_size.width() / 2), round(-logical_size.height() / 2), sprite)
        painter.restore()
        if now < self.happy_until:
            painter.setPen(QColor("#ed8bb7"))
            painter.setFont(QFont("Segoe UI Symbol", 22))
            painter.drawText(self.width() - 55, 160 - int((now % 1) * 20), "♥")
        if now < self.message_until:
            rect = QRectF(9, 5, self.width() - 18, 66)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(89, 67, 136, 24))
            painter.drawRoundedRect(rect.translated(0, 3), 16, 16)
            painter.setBrush(QColor(253, 251, 255, 246))
            painter.drawRoundedRect(rect, 16, 16)
            painter.setPen(QColor("#514568"))
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            painter.drawText(rect.adjusted(12, 7, -12, -7), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             self.message)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_at = event.globalPosition().toPoint()
            self.drag_offset = self.press_at - self.pos()
            self.dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            current = event.globalPosition().toPoint()
            if (current - self.press_at).manhattanLength() > QApplication.startDragDistance():
                self.dragged = True
            if self.dragged:
                self.move(current - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_offset is not None:
            self.drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.clamp()
            if self.dragged:
                self.preferences_changed.emit({"x": self.x(), "y": self.y()})
            else:
                head = event.position().y() < 88 + self.sprite.height() * 0.61
                self.interact("pat" if head else "wave")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.asleep = False
            self.open_panel.emit()

    def contextMenuEvent(self, event):
        self.show_menu(event.globalPos())

    def show_menu(self, position=None):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu {background:#fcfaff;color:#46385e;padding:7px;border:1px solid #e6dff1;}"
                           "QMenu::item {padding:8px 24px;} QMenu::item:selected {background:#eee7fa;}")
        menu.addAction("和 Robin 聊聊", self.open_panel.emit)
        menu.addAction("摸摸头 ♡", lambda checked=False: self.interact())
        menu.addAction("继续播放" if self.asleep else "暂停待机", self.toggle_sleep)
        preview = menu.addMenu("动作预览")
        for label, action in (("视频待机", "idle"), ("抬手招呼", "wave"),
                              ("转身再回来", "turn"), ("向左散步", "walk")):
            preview.addAction(label, lambda checked=False, name=action: self.preview_action(name))
        menu.addSeparator()
        walk = menu.addAction("偶尔向左散步")
        walk.setCheckable(True)
        walk.setChecked(self.settings["wander"])
        walk.triggered.connect(lambda checked: self.change_preference("wander", checked))
        top = menu.addAction("始终置顶")
        top.setCheckable(True)
        top.setChecked(self.settings["topmost"])
        top.triggered.connect(lambda checked: self.change_preference("topmost", checked))
        menu.addAction("回到屏幕右下角", self.home)
        menu.addAction("隐藏桌宠" if self.isVisible() else "显示桌宠", self.toggle_visible)
        menu.addSeparator()
        menu.addAction("退出桌宠", self.quit_requested.emit)
        menu.exec(position or QCursor.pos())

    def change_preference(self, key, value):
        self.settings[key] = value
        if key == "topmost":
            self.apply_topmost(value)
        self.preferences_changed.emit({key: value})

    def closeEvent(self, event):
        event.ignore()
        self.hidden_by_user = True
        self.hide()

    def enterEvent(self, event):
        now = time.monotonic()
        if not self.asleep and now - self.last_greeting > 12:
            self.motion.trigger("glance")
            self.last_greeting = now
        super().enterEvent(event)
