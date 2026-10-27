"""Renderer-side optical-flow in-betweens for the existing character keyframes.

All source art remains unchanged. Flow estimation runs on one background worker;
the Qt thread only remaps cached fields and paints the resulting RGBA frame.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap


def image_array(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    rows = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
    return rows[:, :image.width() * 4].reshape(image.height(), image.width(), 4).copy().astype(np.float32) / 255


def estimate_flow(a, b):
    estimator = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    estimator.setFinestScale(0)
    estimator.setGradientDescentIterations(20)
    estimator.setVariationalRefinementIterations(5)
    forward = estimator.calc(a, b, None)
    backward = estimator.calc(b, a, None)
    return forward, backward


class FlowInterpolator:
    def __init__(self, frames):
        cv2.setNumThreads(2)
        self.arrays = {}
        self.gray = {}
        for key, pixmap in frames.items():
            array = image_array(pixmap)
            alpha = array[:, :, 3:4]
            premultiplied = array.copy()
            premultiplied[:, :, :3] *= alpha
            self.arrays[key] = premultiplied
            composite = premultiplied[:, :, :3] + (1 - alpha) * 0.96
            self.gray[key] = cv2.cvtColor(np.uint8(np.clip(composite * 255, 0, 255)), cv2.COLOR_RGB2GRAY)
        sample = next(iter(frames.values()))
        self.y, self.x = np.mgrid[0:sample.height(), 0:sample.width()].astype(np.float32)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="motion-inbetween")
        self.jobs = {}
        self.cache = OrderedDict()
        self.closed = False

    def prepare(self, pairs):
        for a, b in pairs:
            pair = tuple(sorted((a, b)))
            if a != b and pair not in self.jobs:
                self.jobs[pair] = self.worker.submit(estimate_flow, self.gray[pair[0]], self.gray[pair[1]])

    def wait_ready(self):
        for future in self.jobs.values():
            future.result(timeout=60)

    @property
    def ready(self):
        return all(future.done() for future in self.jobs.values())

    def frame(self, a, b, progress):
        if self.closed:
            return self._to_pixmap(self.arrays[b if progress >= 1 else a])
        if a == b or progress <= 0:
            return self._to_pixmap(self.arrays[a])
        if progress >= 1:
            return self._to_pixmap(self.arrays[b])
        # Quantize only the cache key, at a finer rate than normal display ticks.
        step = round(progress * 48)
        key = a, b, step
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        t = step / 48
        pair = tuple(sorted((a, b)))
        future = self.jobs.get(pair)
        if future is None:
            self.prepare([(a, b)])
            future = self.jobs[pair]
        if not future.done():
            # Startup only: cheap premultiplied dissolve until the worker is ready.
            blended = self.arrays[a] * (1 - t) + self.arrays[b] * t
            return self._to_pixmap(blended)
        forward, backward = future.result()
        if pair[0] != a:
            forward, backward = backward, forward
        # Invert each displacement field at the intermediate coordinates. A
        # refinement avoids sampling long hand movements at the wrong endpoint.
        ax, ay = self.x - t * forward[:, :, 0], self.y - t * forward[:, :, 1]
        bx, by = self.x - (1 - t) * backward[:, :, 0], self.y - (1 - t) * backward[:, :, 1]
        for _ in range(2):
            af = cv2.remap(forward, ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            bf = cv2.remap(backward, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            ax, ay = self.x - t * af[:, :, 0], self.y - t * af[:, :, 1]
            bx, by = self.x - (1 - t) * bf[:, :, 0], self.y - (1 - t) * bf[:, :, 1]
        warped_a = cv2.remap(self.arrays[a], ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        warped_b = cv2.remap(self.arrays[b], bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        blended = warped_a * (1 - t) + warped_b * t
        result = self._to_pixmap(blended)
        self.cache[key] = result
        if len(self.cache) > 32:
            self.cache.popitem(last=False)
        return result

    @staticmethod
    def _to_pixmap(premultiplied):
        rgba = premultiplied.copy()
        alpha = rgba[:, :, 3:4]
        rgba[:, :, :3] = np.divide(rgba[:, :, :3], alpha, out=np.zeros_like(rgba[:, :, :3]), where=alpha > 1e-5)
        raw = np.ascontiguousarray(np.clip(rgba * 255, 0, 255).astype(np.uint8))
        image = QImage(raw.data, raw.shape[1], raw.shape[0], raw.strides[0], QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(image.copy())

    def close(self):
        if not self.closed:
            self.closed = True
            self.worker.shutdown(wait=False, cancel_futures=True)
