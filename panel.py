"""Companion panel: plain-text chat, model settings, and pet preferences."""
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSlider, QTabWidget, QVBoxLayout, QWidget,
)
from config import APP_TITLE, ROOT
from ui_assets import app_icon, placeholder

STYLE = """
QWidget {font-family:'Microsoft YaHei UI'; font-size:13px; color:#473d59;}
QWidget#panel {background:#f7f4fc;}
QLabel#eyebrow {color:#9c88c5;font-size:11px;font-weight:600;letter-spacing:2px;}
QLabel#title {font-size:25px;font-weight:700;color:#493966;}
QLabel#muted {color:#9589a5;font-size:11px;}
QLabel#status {color:#82729b; background:#eee7f8;border-radius:10px;padding:6px 10px;}
QFrame#card {background:#fff;border:1px solid #ece5f4;border-radius:14px;}
QTabWidget::pane {border:0;}
QTabBar::tab {background:transparent;padding:10px 20px;color:#998bad;border-bottom:2px solid transparent;}
QTabBar::tab:selected {color:#7550a7;border-bottom:2px solid #a88acb;font-weight:600;}
QPushButton {background:#fff;border:1px solid #e6ddf0;border-radius:9px;padding:8px 13px;}
QPushButton:hover {background:#eee7f8;border-color:#cbb7e2;}
QPushButton:pressed {background:#e3d6f3;}
QPushButton:disabled {color:#b8aeca;background:#efecf3;}
QPushButton#primary {background:#9070ba;color:#fff;border:0;font-weight:600;}
QPushButton#primary:hover {background:#7e5fa8;}
QPushButton#primary:disabled {background:#c4b7d5;}
QLineEdit, QPlainTextEdit, QComboBox {background:#fff;border:1px solid #e3d9ef;border-radius:8px;padding:8px;selection-background-color:#d8c5ed;}
QLineEdit:focus, QPlainTextEdit:focus {border:1px solid #aa8bce;}
QScrollArea {background:transparent;border:0;}
QScrollArea > QWidget > QWidget {background:transparent;}
QScrollBar:vertical {width:7px;background:transparent;margin:3px;}
QScrollBar::handle:vertical {background:#dcd1e9;border-radius:3px;min-height:25px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
QSlider::groove:horizontal {height:5px;background:#e5dced;border-radius:2px;}
QSlider::handle:horizontal {background:#9c7bbf;width:16px;margin:-5px 0;border-radius:8px;}
QCheckBox {spacing:8px;}
"""


class ChatInput(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class Panel(QWidget):
    send_message = Signal(str)
    save_settings = Signal(dict, str)
    stop_request = Signal()
    clear_chat = Signal()
    speak_latest = Signal()
    stop_speech = Signal()
    pet_action = Signal(str)

    def __init__(self, settings, key):
        super().__init__()
        self.setObjectName("panel")
        self.setWindowTitle(APP_TITLE + " · 陪伴面板")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.setMinimumSize(440, 620)
        self.resize(480, 740)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        eyebrow = QLabel(APP_TITLE)
        eyebrow.setObjectName("eyebrow")
        title_box.addWidget(eyebrow)
        title = QLabel("Robin-pet")
        title.setObjectName("title")
        title_box.addWidget(title)
        subtitle = QLabel("陪你，把日子唱成歌。")
        subtitle.setObjectName("muted")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        portrait = QLabel()
        portrait.setPixmap(placeholder(88))
        header.addWidget(portrait)
        layout.addLayout(header)
        self.status = QLabel("填写 API Key 后，即可开始 AI 对话")
        self.status.setWordWrap(True)
        self.status.setObjectName("status")
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.make_chat(), "聊聊天")
        self.tabs.addTab(self.make_settings(settings, key), "模型与设置")
        layout.addWidget(self.tabs, 1)
        footer = QLabel("同人桌宠 · 双击角色打开面板 · 关闭面板后仍在托盘陪伴")
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        layout.addWidget(footer)

    def make_chat(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        quick = QHBoxLayout()
        for text, action in (("摸摸头", "pet"), ("待机视频", "preview"), ("暂停 / 继续", "sleep"), ("回到角落", "home")):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, a=action: self.pet_action.emit(a))
            quick.addWidget(button)
        layout.addLayout(quick)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.chat_content = QWidget()
        self.messages = QVBoxLayout(self.chat_content)
        self.messages.setContentsMargins(0, 5, 0, 5)
        self.messages.setSpacing(12)
        self.messages.addStretch()
        self.scroll.setWidget(self.chat_content)
        layout.addWidget(self.scroll, 1)
        tools = QHBoxLayout()
        self.clear_button = QPushButton("清空对话")
        self.clear_button.clicked.connect(self.clear_chat.emit)
        tools.addWidget(self.clear_button)
        tools.addStretch()
        self.listen_button = QPushButton("朗读回复")
        self.listen_button.setEnabled(False)
        self.listen_button.clicked.connect(self.speak_latest.emit)
        tools.addWidget(self.listen_button)
        stop = QPushButton("停止朗读")
        stop.clicked.connect(self.stop_speech.emit)
        tools.addWidget(stop)
        layout.addLayout(tools)
        self.input = ChatInput()
        self.input.setFixedHeight(82)
        self.input.setPlaceholderText("今天想聊点什么？\nEnter 发送，Shift + Enter 换行")
        self.input.submitted.connect(self.submit)
        layout.addWidget(self.input)
        bottom = QHBoxLayout()
        note = QLabel("对话仅保留在本次运行中")
        note.setObjectName("muted")
        bottom.addWidget(note)
        bottom.addStretch()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.stop_request.emit)
        self.cancel_button.hide()
        bottom.addWidget(self.cancel_button)
        self.send_button = QPushButton("发送  →")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.submit)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)
        return page

    def make_settings(self, settings, key):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 15, 6, 0)
        form = QFormLayout()
        form.setSpacing(13)
        self.base_url = QLineEdit(settings["base_url"])
        form.addRow("接口地址", self.base_url)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(["deepseek-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"])
        self.model.setCurrentText(settings["model"])
        form.addRow("模型名称", self.model)
        self.key = QLineEdit(key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("粘贴你的 API Key")
        form.addRow("API Key", self.key)
        layout.addLayout(form)
        key_note = QLabel("API Key 使用当前 Windows 用户加密保存。对话会发送至你配置的模型服务。支持 DeepSeek 和兼容接口。")
        key_note.setObjectName("muted")
        key_note.setWordWrap(True)
        layout.addWidget(key_note)
        self.persona = QPlainTextEdit(settings["persona"])
        self.persona.setFixedHeight(112)
        layout.addWidget(QLabel("角色性格"))
        layout.addWidget(self.persona)
        size_row = QHBoxLayout()
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(160, 440)
        self.size.setValue(settings["size"])
        self.size_label = QLabel(f"{settings['size']} px")
        self.size.valueChanged.connect(lambda value: self.size_label.setText(f"{value} px"))
        size_row.addWidget(QLabel("角色高度"))
        size_row.addWidget(self.size, 1)
        size_row.addWidget(self.size_label)
        layout.addLayout(size_row)
        self.topmost = QCheckBox("始终置顶")
        self.topmost.setChecked(settings["topmost"])
        self.wander = QCheckBox("偶尔向左散步（暂无向右走路素材）")
        self.wander.setChecked(settings["wander"])
        self.voice = QCheckBox("收到 AI 回复后自动朗读")
        self.voice.setChecked(settings["voice"])
        for check in (self.topmost, self.wander, self.voice):
            layout.addWidget(check)
        voice_note = QLabel("语音使用 Windows 本地朗读，声音取决于已安装的系统语音。当前未提供角色音色克隆或麦克风输入。")
        voice_note.setWordWrap(True)
        voice_note.setObjectName("muted")
        layout.addWidget(voice_note)
        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save)
        layout.addWidget(self.save_button)
        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def save(self):
        values = {"base_url": self.base_url.text().strip(), "model": self.model.currentText().strip(),
                  "persona": self.persona.toPlainText().strip(), "size": self.size.value(),
                  "topmost": self.topmost.isChecked(), "wander": self.wander.isChecked(),
                  "voice": self.voice.isChecked()}
        self.save_settings.emit(values, self.key.text().strip())

    def submit(self):
        text = self.input.toPlainText().strip()
        if text and self.send_button.isEnabled():
            self.send_message.emit(text)

    def set_busy(self, busy):
        self.send_button.setEnabled(not busy)
        self.input.setReadOnly(busy)
        self.cancel_button.setVisible(busy)
        self.clear_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.send_button.setText("正在聆听…" if busy else "发送  →")

    def add_message(self, role, text):
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(13, 10, 13, 12)
        name = QLabel({"user": "你", "assistant": "Robin", "system": "提示"}[role])
        name.setObjectName("muted")
        box.addWidget(name)
        body = QLabel(text)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(body)
        if role == "user":
            card.setStyleSheet("QFrame#card {background:#f0e9fa;}")
        self.messages.insertWidget(self.messages.count() - 1, card)
        # Bound the visible transcript as well as the API context.
        if self.messages.count() > 81:
            old = self.messages.takeAt(0).widget()
            old.deleteLater()
        QTimer.singleShot(0, self.scroll_bottom)

    def scroll_bottom(self):
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def reset_messages(self):
        while self.messages.count() > 1:
            item = self.messages.takeAt(0)
            item.widget().deleteLater()
        self.listen_button.setEnabled(False)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
