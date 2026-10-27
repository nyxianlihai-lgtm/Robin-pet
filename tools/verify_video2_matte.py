"""Audit every keyed frame against actual source screen pixels, not just corners."""
import json
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'assets' / 'video2_hq'


def main():
    manifest = json.loads((PACK / 'manifest.json').read_text('utf-8'))
    checked = 0
    for name, source in manifest['sources'].items():
        cap = cv2.VideoCapture(str(ROOT / source['path']))
        for i in range(source['frames']):
            ok, image = cap.read()
            assert ok
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            green = cv2.inRange(hsv, np.array([35, 22, 0]), np.array([88, 255, 255]))
            n, labels, stats, _ = cv2.connectedComponentsWithStats(green)
            screen = np.uint8(labels == 1 + np.argmax(stats[1:, 4]))
            # Ignore anti-aliased contours; check definite exterior screen.
            deep_screen = np.uint8(cv2.distanceTransform(screen, cv2.DIST_L2, 5) > 5)
            matrix = np.float32(source['transform'])
            if name == 'walk':
                matrix[0, 2] += 40 - source['head_x_translation_removed'][i] * matrix[0, 0]
            matrix[0, 2] -= 360
            expected_clear = cv2.warpAffine(deep_screen, matrix, (580, 700), flags=cv2.INTER_NEAREST)
            keyed = cv2.imread(str(PACK / manifest['pattern'].format(index=source['offset'] + i)), -1)
            leaked = (expected_clear > 0) & (keyed[:, :, 3] > 8)
            assert not np.any(leaked), (name, i, int(leaked.sum()))
            assert not np.any(keyed[[0, -1], :, 3] > 8), (name, i, 'top/bottom clip')
            assert not np.any(keyed[:, [0, -1], 3] > 8), (name, i, 'side clip')
            checked += 1
        cap.release()
    print(f'PASS: {checked} frames; exterior green-screen pixels transparent; no canvas clipping')


if __name__ == '__main__':
    main()
