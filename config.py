"""Portable preferences. Chat messages are intentionally kept in memory only."""
import json
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
APP_NAME = "Robin-pet"
APP_VERSION = "1.2"
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"
DEFAULTS = {
    "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
    "key_encrypted": "", "size": 280, "topmost": True,
    "wander": False, "voice": False,
    "persona": "你是用户桌面上的 Robin，一位温柔、乐观、热爱音乐的虚拟陪伴角色。"
               "用自然的中文回应，通常控制在一到三句话。可以偶尔提及歌曲、星空和陪伴，"
               "但不要每句都加语气词。认真回答用户的问题，不要假装能看到屏幕或操作电脑。"
               "这是同人桌宠角色扮演，不要声称是游戏官方服务或真人。",
}


class Config:
    def __init__(self, path=None):
        self.path = Path(path) if path else ROOT / "data" / "settings.json"
        self.values = DEFAULTS.copy()
        self.warning = ""
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("配置格式错误")
                for name, default in DEFAULTS.items():
                    value = raw.get(name, default)
                    if type(value) is type(default):
                        self.values[name] = value
                for key in ("x", "y"):
                    if type(raw.get(key)) is int:
                        self.values[key] = raw[key]
            except (OSError, ValueError):
                self.warning = "配置文件无法读取，本次使用默认设置。"
        self.values["size"] = max(160, min(440, self.values["size"]))

    def __getitem__(self, key):
        return self.values[key]

    def save(self, updates=None):
        candidate = {**self.values, **(updates or {})}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        self.values = candidate
