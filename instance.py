"""A connected pipe alone does not prove the existing UI is responsive."""
import hashlib
from PySide6.QtNetwork import QLocalSocket


def server_name(root):
    return "robin-pet-" + hashlib.sha256(str(root).lower().encode()).hexdigest()[:16]


def activate_existing(name, timeout=2500):
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(400):
        return False
    socket.write(b"activate\n")
    socket.waitForBytesWritten(timeout)
    if socket.waitForReadyRead(timeout) and bytes(socket.readAll()).strip() == b"ok":
        socket.disconnectFromServer()
        return True
    socket.abort()
    raise RuntimeError("已有桌宠实例尚未回应，新的程序尚未启动。若正在加载，请稍候再试；长时间无响应时，请退出旧桌宠后重试，或在任务管理器结束本项目的 pythonw.exe。")


def attach_activation(server, callback):
    def accept():
        socket = server.nextPendingConnection()
        if socket is None:
            return
        handled = False

        def receive():
            nonlocal handled
            if handled or not socket.canReadLine():
                return
            handled = True
            command = bytes(socket.readLine()).strip()
            if command == b"activate":
                socket.write(b"ok\n")
                socket.flush()
                socket.disconnectFromServer()
                callback()
            else:
                socket.disconnectFromServer()

        socket.readyRead.connect(receive)
        socket.disconnected.connect(socket.deleteLater)
        receive()

    server.newConnection.connect(accept)
