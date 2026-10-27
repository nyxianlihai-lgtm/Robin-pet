"""Asynchronous chat and local Windows speech, integrated with the Qt event loop."""
import base64
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


def endpoint_url(base):
    base = base.strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("请输入完整的 http:// 或 https:// 接口地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("接口地址不能包含密码、查询参数或锚点。")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("远程服务请使用 HTTPS；HTTP 仅用于本机模型。")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


class ChatClient(QObject):
    succeeded = Signal(str)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.buffer = bytearray()
        self.problem = ""
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timeout)

    @property
    def busy(self):
        return self.reply is not None

    def send(self, settings, key, messages):
        if self.busy:
            return
        url = endpoint_url(settings["base_url"])
        if not settings["model"].strip():
            raise ValueError("请填写模型名称。")
        payload = {"model": settings["model"].strip(), "messages": messages,
                   "stream": False, "max_tokens": 2048}
        if urlsplit(url).hostname == "api.deepseek.com" and settings["model"] in ("deepseek-flash", "deepseek-v4-pro"):
            payload["thinking"] = {"type": "disabled"}
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        if key:
            request.setRawHeader(b"Authorization", ("Bearer " + key).encode("utf-8"))
        self.buffer = bytearray()
        self.problem = ""
        self.reply = self.manager.post(request, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.reply.readyRead.connect(self._read)
        self.reply.finished.connect(self._finished)
        self.timeout.start(65000)
        self.busy_changed.emit(True)

    def _read(self):
        if self.reply is None:
            return
        self.buffer.extend(bytes(self.reply.readAll()))
        if len(self.buffer) > 4 * 1024 * 1024:
            self.problem = "模型返回的内容过大。"
            self.reply.abort()

    def _timeout(self):
        if self.reply:
            self.problem = "等待回复超时，请稍后重试。"
            self.reply.abort()

    def cancel(self):
        if self.reply:
            self.problem = "本次请求已取消。"
            self.reply.abort()

    def _finished(self):
        reply = self.reply
        if reply is None:
            return
        self.timeout.stop()
        self._read()
        self.reply = None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        reply.deleteLater()
        self.busy_changed.emit(False)
        if self.problem:
            self.failed.emit(self.problem)
            return
        if status is not None and not 200 <= int(status) < 300:
            hints = {401: "API Key 无效或已过期", 402: "账户余额不足", 403: "没有访问权限",
                     404: "接口路径或模型名称不正确", 429: "请求过多或额度不足"}
            self.failed.emit(f"HTTP {status}：{hints.get(int(status), '服务暂时不可用，请检查接口配置')}。")
            return
        if error != QNetworkReply.NetworkError.NoError:
            self.failed.emit("连接失败，请检查网络、证书和接口地址。")
            return
        try:
            content = json.loads(self.buffer)["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty response")
        except (ValueError, KeyError, IndexError, TypeError):
            self.failed.emit("接口未返回兼容的文本回复，请检查模型配置。")
            return
        self.succeeded.emit(content.strip())


class Speaker(QObject):
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.poller = QTimer(self)
        self.poller.timeout.connect(self._poll)

    def stop(self):
        self.poller.stop()
        if self.process is not None:
            old = self.process
            self.process = None
            old.kill()
            old.communicate(timeout=2)

    def speak(self, text):
        self.stop()
        text = re.sub(r"https?://\S+", "链接", text)
        text = re.sub(r"[*#`_]", "", text)[:1800]
        data = base64.b64encode(text.encode("utf-8")).decode("ascii")
        script = ("$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Speech; "
                  "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "try {$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet,"
                  "[System.Speech.Synthesis.VoiceAge]::NotSet,0,"
                  "[System.Globalization.CultureInfo]::GetCultureInfo('zh-CN'))} catch {}; "
                  f"$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{data}')); "
                  "try {$s.Speak($t)} finally {$s.Dispose()}")
        command = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        try:
            self.process = subprocess.Popen(
                [str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" /
                     "WindowsPowerShell" / "v1.0" / "powershell.exe"),
                 "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.failed.emit("无法启动 Windows 朗读。请确认系统安装了语音组件。")
            return
        self.poller.start(200)

    def _poll(self):
        if self.process is not None and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            self.poller.stop()
            if code:
                self.failed.emit("朗读失败，请在 Windows 设置中安装中文语音。")
