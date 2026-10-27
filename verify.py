"""Offline integration checks. No real model credentials or paid API calls."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from config import Config, ROOT
from main import Companion, load_fonts
from security import protect, unprotect
from services import endpoint_url


def wait_until(condition, timeout=5000):
    limit = time.monotonic() + timeout / 1000
    while not condition() and time.monotonic() < limit:
        QTest.qWait(20)
        time.sleep(0.005)  # Let the Python mock-server thread acquire the GIL.
    assert condition(), "Timed out waiting for Qt operation"


class MockAPI(BaseHTTPRequestHandler):
    requests = []
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append((self.path, dict(self.headers), payload))
        status = 200
        if self.path.startswith("/unauthorized"):
            status, body = 401, {"error": "bad key"}
        elif self.path.startswith("/invalid"):
            body = {"unrecognized": "response"}
        elif self.path.startswith("/redirect"):
            status, body = 302, {}
        else:
            if self.path.startswith("/slow"):
                time.sleep(0.6)
            body = {"choices": [{"message": {"content": "模拟回复：你好，今天也要开心呀。<b>纯文本</b>"}}]}
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 302:
            self.send_header("Location", "/should-not-follow/chat/completions")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def main():
    qa = ROOT / "qa"
    qa.mkdir(exist_ok=True)
    app = QApplication([])
    load_fonts()
    app.setQuitOnLastWindowClosed(False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockAPI)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    local = f"http://127.0.0.1:{server.server_port}"
    companion = None
    try:
        with tempfile.TemporaryDirectory(dir=qa) as tmp:
            config = Config(Path(tmp) / "settings.json")
            secret = "qa-fake-key-ONLY"
            encrypted = protect(secret)
            assert encrypted != secret and unprotect(encrypted) == secret
            config.save({"key_encrypted": encrypted, "base_url": local})
            assert secret not in config.path.read_text(encoding="utf-8")
            assert unprotect(Config(config.path)["key_encrypted"]) == secret
            print("PASS: encrypted credential persistence")

            assert endpoint_url(local + "/v1/") == local + "/v1/chat/completions"
            assert endpoint_url(local + "/chat/completions") == local + "/chat/completions"
            for bad in ("file:///tmp/key", "https://user:pass@example.org", "http://example.org", "https://example.org?key=test"):
                try:
                    endpoint_url(bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unsafe URL accepted: " + bad)
            print("PASS: endpoint validation")

            companion = Companion(app, config=config, use_tray=False)
            companion.show_panel()
            QTest.qWait(80)
            assert companion.pet.source.hasAlphaChannel()
            image = companion.pet.source.toImage()
            assert image.pixelColor(0, 0).alpha() == 0
            assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() > 240
            assert companion.pet.isVisible() and companion.panel.isVisible()
            companion.pet.grab().save(str(qa / "pet.png"))
            companion.panel.grab().save(str(qa / "panel.png"))
            print("PASS: translucent sprite, pet rendering, panel rendering")

            companion.pet.interact()
            assert companion.pet.happy_until > time.monotonic()
            companion.pet.toggle_sleep()
            assert companion.pet.asleep
            companion.pet.toggle_sleep()
            assert not companion.pet.asleep
            companion.pet.move(-100000, -100000)
            companion.pet.clamp()
            assert companion.pet.screen_bounds().contains(companion.pet.frameGeometry())
            companion.pet.resize_pet(180)
            assert companion.pet.sprite.height() == 180
            companion.pet.resize_pet(280)
            companion.pet.home()
            start = companion.pet.pos()
            QTest.mousePress(companion.pet, Qt.MouseButton.LeftButton, pos=QPoint(140, 180))
            QTest.mouseMove(companion.pet, QPoint(180, 180))
            QTest.mouseRelease(companion.pet, Qt.MouseButton.LeftButton, pos=QPoint(180, 180))
            assert companion.pet.drag_offset is None
            companion.pet.settings["wander"] = True
            # Idle must stay put; only actual gait footage moves the window.
            companion.pet.motion.queued = None
            companion.pet.motion.current = "idle"
            companion.pet.motion.elapsed = 0
            companion.pet.motion.roam_after = 22
            before = companion.pet.x()
            QTest.qWait(200)
            assert companion.pet.x() == before
            if companion.pet.motion_library.available and 'walk' in companion.pet.motion_library.clips:
                companion.pet.motion.current = "walk"
                companion.pet.motion.elapsed = 0
                QTest.qWait(200)
                assert companion.pet.x() < before
            else:
                QTest.qWait(200)
                assert companion.pet.x() == before
            companion.pet.settings["wander"] = False
            companion.pet.toggle_visible()
            assert not companion.pet.isVisible()
            companion.pet.reveal()
            assert companion.pet.isVisible()
            print("PASS: interaction, sleep, offscreen recovery, resize, drag, roaming, hide/show")

            companion.send("第一条测试消息")
            wait_until(lambda: not companion.chat.busy)
            assert len(companion.history) == 2, companion.panel.status.text()
            assert companion.history[0]["content"] == "第一条测试消息"
            assert companion.last_answer.startswith("模拟回复")
            assert companion.panel.listen_button.isEnabled()
            assert any(label.text() == companion.last_answer and label.textFormat() == Qt.TextFormat.PlainText
                       for label in companion.panel.chat_content.findChildren(QLabel))
            companion.send("第二条测试消息")
            wait_until(lambda: not companion.chat.busy)
            request = MockAPI.requests[-1]
            assert request[1]["Authorization"] == "Bearer " + secret
            assert len(request[2]["messages"]) == 4
            assert len(companion.history) == 4
            print("PASS: asynchronous chat, authorization, multi-turn context, plain-text rendering")

            history = companion.history.copy()
            for suffix, expected in (("/unauthorized", "401"), ("/invalid", "文本回复"), ("/redirect", "302")):
                config.values["base_url"] = local + suffix
                companion.send("失败重试测试")
                wait_until(lambda: not companion.chat.busy)
                assert companion.history == history
                assert companion.panel.input.toPlainText() == "失败重试测试"
                assert expected in companion.panel.status.text()
                assert companion.panel.send_button.isEnabled()
            assert not any("should-not-follow" in item[0] for item in MockAPI.requests)
            config.values["base_url"] = local + "/slow"
            companion.send("取消测试")
            companion.chat.cancel()
            wait_until(lambda: not companion.chat.busy)
            assert companion.history == history and "取消" in companion.panel.status.text()
            companion.send("超时测试")
            companion.chat.timeout.start(30)
            wait_until(lambda: not companion.chat.busy)
            assert companion.history == history and "超时" in companion.panel.status.text()
            print("PASS: HTTP errors, malformed data, redirect refusal, cancellation, timeout, retry state")

            config.values["base_url"] = "https://api.deepseek.com"
            companion.key = ""
            count = len(MockAPI.requests)
            companion.send("没有 Key 不应发送")
            assert not companion.chat.busy and len(MockAPI.requests) == count
            assert companion.panel.tabs.currentIndex() == 1
            companion.clear_chat()
            assert not companion.history and not companion.last_answer
            assert not companion.panel.listen_button.isEnabled()
            companion.panel.close()
            assert not companion.panel.isVisible() and companion.pet.isVisible()
            print("PASS: missing-key guard, context reset, close-to-hide behavior")
            companion.shutdown()
            companion = None
    finally:
        if companion:
            companion.shutdown()
        server.shutdown()
        server.server_close()
    print("All checks passed. Screenshots: qa/panel.png, qa/pet.png")


if __name__ == "__main__":
    main()
