"""Robin desktop companion. Run with .venv/Scripts/pythonw.exe main.py."""
import hashlib
import os
import sys
import traceback
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QPoint, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from config import APP_NAME, APP_TITLE, APP_VERSION, Config, ROOT
from panel import Panel
from pet import Pet
from security import protect, unprotect
from services import ChatClient, Speaker, endpoint_url


class Companion(QObject):
    def __init__(self, app, config=None, use_tray=True):
        super().__init__(app)
        self.app = app
        self.config = config or Config()
        self.history = []
        self.last_answer = ""
        self.pending = ""
        self.closing = False
        self.key = ""
        warning = self.config.warning
        try:
            self.key = unprotect(self.config["key_encrypted"])
        except (OSError, ValueError):
            warning = "API Key 无法解密，请在设置中重新填写。"
        self.pet = Pet(self.config.values)
        self.panel = Panel(self.config.values, self.key)
        self.chat = ChatClient(self)
        self.speaker = Speaker(self)
        self.tray = None
        self.pet.open_panel.connect(self.show_panel)
        self.pet.preferences_changed.connect(self.update_preferences)
        self.pet.quit_requested.connect(self.quit)
        self.panel.send_message.connect(self.send)
        self.panel.save_settings.connect(self.save_settings)
        self.panel.stop_request.connect(self.chat.cancel)
        self.panel.clear_chat.connect(self.clear_chat)
        self.panel.speak_latest.connect(lambda: self.speaker.speak(self.last_answer) if self.last_answer else None)
        self.panel.stop_speech.connect(self.speaker.stop)
        self.panel.pet_action.connect(self.pet_action)
        self.chat.succeeded.connect(self.on_answer)
        self.chat.failed.connect(self.on_error)
        self.chat.busy_changed.connect(self.panel.set_busy)
        self.chat.busy_changed.connect(self.pet.set_thinking)
        self.speaker.failed.connect(self.report)
        if use_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(str(ROOT / "assets" / "robin.png")), self)
            self.tray.setToolTip(APP_TITLE + " · 双击打开陪伴面板")
            menu = QMenu()
            menu.addAction("打开陪伴面板", self.show_panel)
            menu.addAction("显示 / 隐藏桌宠", self.pet.toggle_visible)
            menu.addAction("回到屏幕右下角", self.pet.home)
            menu.addSeparator()
            menu.addAction("退出桌宠", self.quit)
            self.tray_menu = menu
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self.tray_activated)
            self.tray.show()
        self.pet.show()
        if "x" in self.config.values and "y" in self.config.values:
            self.pet.move(self.config["x"], self.config["y"])
            self.pet.clamp()
        else:
            self.pet.home()
        self.panel.add_message("system", "很高兴在这里与你见面。先到「模型与设置」填入 API Key，再回来聊聊吧。\n单击角色可以摸摸头，拖动可以移动，右键有更多控制。")
        if self.key:
            self.panel.status.setText("模型已配置 · " + self.config["model"])
        if warning:
            self.report(warning)
        if not self.pet.motion_library.available:
            self.report("视频动作未加载，暂用原正面图。请检查 assets/video2_hq。")
        app.aboutToQuit.connect(self.shutdown)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_panel()

    def show_panel(self):
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def report(self, message):
        self.panel.status.setText(message)
        self.pet.say(message, 7)

    def pet_action(self, action):
        {"pet": self.pet.interact, "preview": lambda: self.pet.preview_action("idle"),
         "sleep": self.pet.toggle_sleep, "home": self.pet.home}[action]()

    def update_preferences(self, updates):
        try:
            self.config.save(updates)
            self.panel.topmost.setChecked(self.config["topmost"])
            self.panel.wander.setChecked(self.config["wander"])
        except OSError:
            self.report("设置暂时无法保存，请检查项目 data 目录的写入权限。")

    def save_settings(self, values, key):
        try:
            endpoint_url(values["base_url"])
            if not values["model"] or not values["persona"]:
                raise ValueError("模型名称和角色性格不能为空。")
            if "\n" in key or "\r" in key:
                raise ValueError("API Key 不能包含换行。")
            encrypted = protect(key)
            reset = any(values[name] != self.config[name] for name in ("base_url", "model", "persona"))
            self.config.save({**values, "key_encrypted": encrypted})
        except (OSError, ValueError) as error:
            self.report("保存失败：" + str(error))
            return
        self.key = key
        self.pet.resize_pet(values["size"])
        self.pet.settings.update(values)
        self.pet.apply_topmost(values["topmost"])
        if not values["voice"]:
            self.speaker.stop()
        if reset:
            self.clear_chat()
        self.report("设置已保存。现在可以回到「聊聊天」发送消息。")

    def send(self, text):
        if self.chat.busy:
            return
        if len(text) > 6000:
            self.report("这条消息有些长，请缩短到 6000 字以内。")
            return
        local = urlsplit(self.config["base_url"]).hostname in ("localhost", "127.0.0.1", "::1")
        if not self.key and not local:
            self.panel.tabs.setCurrentIndex(1)
            self.panel.key.setFocus()
            self.report("请先填写 API Key 并保存设置，消息还没有发送。")
            return
        messages = [{"role": "system", "content": self.config["persona"]},
                    *self.history[-20:], {"role": "user", "content": text}]
        try:
            self.pending = text
            self.chat.send(self.config.values, self.key, messages)
        except ValueError as error:
            self.pending = ""
            self.report(str(error))
            return
        self.panel.add_message("user", text)
        self.panel.input.clear()
        self.panel.status.setText("知更鸟正在听你说话…")
        self.pet.say("让我想一想…", 65)

    def on_answer(self, answer):
        self.history.extend([{"role": "user", "content": self.pending},
                             {"role": "assistant", "content": answer}])
        self.history = self.history[-20:]
        self.pending = ""
        self.last_answer = answer
        self.panel.listen_button.setEnabled(True)
        self.panel.add_message("assistant", answer)
        self.panel.status.setText("回复来自 " + self.config["model"])
        self.pet.asleep = False
        self.pet.motion.update(0, sleeping=False)
        self.pet.say(answer, 10)
        if self.config["voice"]:
            self.speaker.speak(answer)

    def on_error(self, error):
        if self.pending:
            self.panel.input.setPlainText(self.pending)
            self.pending = ""
        self.panel.add_message("system", error + " 原消息已放回输入框，可修改后重试。")
        self.report(error)

    def clear_chat(self):
        if self.chat.busy:
            return
        self.history.clear()
        self.last_answer = ""
        self.panel.reset_messages()
        self.speaker.stop()
        self.panel.add_message("system", "已清空本次对话。接下来的消息会开始一段新聊天。")

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.chat.cancel()
        self.speaker.stop()
        self.pet.timer.stop()
        self.pet.motion_library.close()
        try:
            self.config.save({"x": self.pet.x(), "y": self.pet.y()})
        except OSError:
            pass
        if self.tray:
            self.tray.hide()

    def quit(self):
        self.shutdown()
        self.app.quit()


def load_fonts():
    # The offscreen Qt backend may not enumerate Windows' system fonts.
    for filename in ("msyh.ttc", "msyhbd.ttc", "seguisym.ttf", "segoeui.ttf"):
        font_path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", filename)
        if os.path.isfile(font_path):
            QFontDatabase.addApplicationFont(font_path)


def main():
    app = QApplication(sys.argv)
    load_fonts()
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(QIcon(str(ROOT / "assets" / "robin.png")))
    app.setQuitOnLastWindowClosed(False)
    name = "robin-pet-" + hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:16]
    socket = QLocalSocket()
    socket.connectToServer(name)
    if socket.waitForConnected(400):
        socket.write(b"show")
        socket.waitForBytesWritten(400)
        socket.disconnectFromServer()
        return 0
    server = QLocalServer()
    if not server.listen(name):
        QMessageBox.warning(None, "知更鸟", "另一个桌宠实例正在启动，请稍后再试。")
        return 1
    companion = Companion(app)

    def activate():
        connection = server.nextPendingConnection()
        if connection:
            connection.disconnectFromServer()
            connection.deleteLater()
        companion.show_panel()
        companion.pet.reveal()

    server.newConnection.connect(activate)

    def exception_hook(kind, value, tb):
        (ROOT / "data").mkdir(exist_ok=True)
        with (ROOT / "data" / "error.log").open("a", encoding="utf-8") as stream:
            traceback.print_exception(kind, value, tb, file=stream)
        companion.report("遇到错误，详情已记录到 data/error.log。")

    sys.excepthook = exception_hook
    QTimer.singleShot(350, companion.show_panel)
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        (ROOT / "data").mkdir(exist_ok=True)
        (ROOT / "data" / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
