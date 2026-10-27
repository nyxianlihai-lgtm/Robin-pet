"""Windows DPAPI: API keys are encrypted for the current Windows account."""
import base64
import ctypes as c
from ctypes import wintypes as w
import os


class Blob(c.Structure):
    _fields_ = [("size", w.DWORD), ("data", c.POINTER(c.c_ubyte))]


def transform(value: bytes, encrypt: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("保存 API Key 需要 Windows 当前用户加密功能。")
    buffer = c.create_string_buffer(value)
    source = Blob(len(value), c.cast(buffer, c.POINTER(c.c_ubyte)))
    result = Blob()
    crypt = c.WinDLL("crypt32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.LocalFree.restype = c.c_void_p
    func = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    func.argtypes = [c.POINTER(Blob), c.c_void_p, c.c_void_p, c.c_void_p,
                     c.c_void_p, w.DWORD, c.POINTER(Blob)]
    func.restype = w.BOOL
    if not func(c.byref(source), None, None, None, None, 1, c.byref(result)):
        raise c.WinError(c.get_last_error())
    try:
        return c.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def protect(text: str) -> str:
    return base64.b64encode(transform(text.encode("utf-8"), True)).decode("ascii") if text else ""


def unprotect(text: str) -> str:
    return transform(base64.b64decode(text), False).decode("utf-8") if text else ""
