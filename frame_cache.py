"""Bounded GUI-thread pixmap cache; decode upcoming frames between paints."""
from collections import OrderedDict
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QPixmap


class FrameCache(QObject):
    def __init__(self, count, render, failed, budget=96*1024*1024):
        super().__init__()
        self.count = count
        self.render = render
        self.failed = failed
        self.budget = budget
        self.bytes_used = 0
        self.data = OrderedDict()
        self.pending = []
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self._prefetch_one)

    def __len__(self):
        return 0 if self.closed else self.count

    @property
    def resident_count(self):
        return len(self.data)

    def __getitem__(self, index):
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        if index in self.data:
            self.data.move_to_end(index)
            return self.data[index]
        try:
            pixmap = self.render(index)
        except (ValueError, OSError) as error:
            self.timer.stop()
            self.pending.clear()
            self.failed(str(error))
            return next(iter(self.data.values()), QPixmap())
        self.data[index] = pixmap
        self.bytes_used += pixmap.width()*pixmap.height()*4
        while self.bytes_used > self.budget and len(self.data) > 1:
            _, old = self.data.popitem(last=False)
            self.bytes_used -= old.width()*old.height()*4
        return pixmap

    def prefetch(self, indices):
        self.pending = list(dict.fromkeys(i for i in indices if i not in self.data))
        if self.pending and not self.timer.isActive() and not self.closed:
            self.timer.start()
        elif not self.pending:
            self.timer.stop()

    def _prefetch_one(self):
        if self.pending:
            self[self.pending.pop(0)]
        if not self.pending:
            self.timer.stop()

    def clear(self):
        self.timer.stop()
        self.pending.clear()
        self.data.clear()
        self.bytes_used = 0
        self.closed = True
