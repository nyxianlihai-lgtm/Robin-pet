"""Build the second supplied video pack, retaining fixed framing per clip."""
from pathlib import Path
import hashlib
import json
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets' / 'video2_hq'
FILES = {'lower': '1793094244936', 'walk': '1793094247831',
         'turn': '1793094249251', 'greet': '1793095240081'}


def matte(frame):
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # This screen is muted green, not the saturated screen from video 1.
    green = cv2.inRange(hsv, np.array([35, 22, 0]), np.array([88, 255, 255]))
    mask = 255 - green
    mask[:, :round(w * .18)] = 0
    mask[:, round(w * .82):] = 0
    mask[round(h * .935):] = 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    keep = np.zeros(n, np.uint8)
    for k in range(1, n):
        if stats[k, 4] >= 30:
            keep[k] = 255
    mask = keep[labels]
    # Preserve small enclosed iris components, never a fixed opaque face area.
    # The actor moves in the source: an ellipse would expose the green screen.
    n, green_labels, stats, _ = cv2.connectedComponentsWithStats(green)
    eye_keep = np.zeros(n, np.uint8)
    b, g, r = [channel.astype(np.int16) for channel in cv2.split(frame)]
    skin = ((r - b > 12) & (r - g > 3) & (r > 150) & (b > 100)).astype(np.uint8)
    near_skin = cv2.dilate(skin, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    for k in range(1, n):
        x, y, bw, bh, area = stats[k]
        if (4 <= area <= 800 and bw <= 50 and bh <= 50
                and h * .35 < y < h * .65 and w * .18 < x < w * .82):
            component = green_labels[y:y+bh, x:x+bw] == k
            bright = np.percentile(frame[y:y+bh, x:x+bw, 1][component], 90) > 190
            facial = np.mean(near_skin[y:y+bh, x:x+bw][component]) > .5
            if bright and facial:
                eye_keep[k] = 255
    mask = cv2.bitwise_or(mask, eye_keep[green_labels])
    alpha = cv2.GaussianBlur(mask.astype(np.float32) / 255, (3, 3), .5)
    rgb = frame.astype(np.float32) / 255
    edge = (alpha > 0) & (alpha < .99)
    rgb[:, :, 1][edge] = np.minimum(rgb[:, :, 1][edge],
                                  np.maximum(rgb[:, :, 0][edge], rgb[:, :, 2][edge]))
    # Retain original 1280x720 samples; runtime downsamples once to display size.
    return np.uint8(np.clip(np.dstack([rgb, alpha]) * 255, 0, 255))


def box(frame):
    ys, xs = np.where(frame[:, :, 3] >= 160)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    qa = ROOT / 'qa' / 'video2-hq'
    qa.mkdir(parents=True, exist_ok=True)
    sources, frames = {}, []
    raw = {}
    for name, stem in FILES.items():
        source = ROOT / '参考视频2' / (stem + '.mp4')
        cap = cv2.VideoCapture(str(source))
        fps = cap.get(cv2.CAP_PROP_FPS)
        clip = []
        while True:
            ok, image = cap.read()
            if not ok:
                break
            clip.append(matte(image))
        assert len(clip) == int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 121
        cap.release()
        sources[name] = {'path': str(source.relative_to(ROOT)), 'fps': fps,
                         'frames': len(clip), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        raw[name] = clip
    # One fixed transform per video, never a per-frame bounding-box crop.
    reference = box(raw['greet'][0])
    for name in list(raw):
        clip = raw.pop(name)
        first = box(clip[0])
        scale = (reference[3] - reference[1]) / (first[3] - first[1])
        if name == 'walk':
            # A stride lifts a foot: use the median grounded-foot baseline.
            bottom = float(np.percentile([box(f)[3] for f in clip], 90))
            scale = (reference[3] - reference[1]) / float(np.median([box(f)[3] - box(f)[1] for f in clip]))
        else:
            bottom = first[3]
        matrix = np.float32([[scale, 0, 640 - (first[0] + first[2]) * .5 * scale],
                             [0, scale, 660 - bottom * scale]])
        sources[name]['transform'] = matrix.tolist()
        sources[name]['offset'] = len(frames)
        shifts = [0.0] * len(clip)
        if name == 'walk':
            # The supplied walking actor drifts sideways inside the fixed camera.
            # Track the head, not the changing arm/leg silhouette, to remove this
            # baked-in translation before the desktop supplies its own movement.
            template = cv2.cvtColor(clip[0][230:440, 490:650, :3], cv2.COLOR_BGR2GRAY)
            positions = []
            for f in clip:
                search = cv2.cvtColor(f[210:460, 300:880, :3], cv2.COLOR_BGR2GRAY)
                correlation = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
                _, _, _, (x, y) = cv2.minMaxLoc(correlation)
                fractional = 0.0
                if 0 < x < correlation.shape[1] - 1:
                    left, mid, right = correlation[y, x-1:x+2]
                    denominator = float(left - 2 * mid + right)
                    if abs(denominator) > 1e-6:
                        fractional = .5 * float(left - right) / denominator
                positions.append(x + fractional)
            positions = np.array(positions)
            shifts = (positions - positions[0]).tolist()
            sources[name]['head_x_translation_removed'] = shifts
        base_matrix = matrix.copy()
        for i, frame in enumerate(clip):
            matrix = base_matrix.copy()
            if name == 'walk':
                matrix[0, 2] += 40 - shifts[i] * scale
            # Crop unused canvas with the SAME rectangle for every source frame.
            matrix[0, 2] -= 360
            # Affine on premultiplied color avoids dark resize fringes.
            f = frame.astype(np.float32) / 255
            f[:, :, :3] *= f[:, :, 3:4]
            f = cv2.warpAffine(f, matrix, (580, 700), flags=cv2.INTER_LANCZOS4)
            f = np.clip(f, 0, 1)
            f[:, :, :3] = np.divide(f[:, :, :3], f[:, :, 3:4],
                                    out=np.zeros_like(f[:, :, :3]), where=f[:, :, 3:4] > 1e-6)
            f = np.uint8(np.clip(f * 255, 0, 255))
            frames.append(f)
            if i in (0, 44, 60, 120):
                a = f[:, :, 3:4] / 255
                preview = np.hstack([np.uint8(f[:, :, :3] * a + np.array(bg) * (1 - a))
                                     for bg in [(250, 250, 250), (39, 34, 45)]])
                cv2.imwrite(str(qa / f'{name}_{i:03d}.jpg'), preview)
        print('Keyed:', name, flush=True)
    def seq(name, indices):
        return [sources[name]['offset'] + i for i in indices]
    # Pick a forward walk interval with similar foot phases. No reversed walk.
    walk = frames[sources['walk']['offset']:sources['walk']['offset'] + 121]
    features = []
    for f in walk:
        a = f[450:670, 80:480, 3:4] / 255
        features.append(np.dstack([f[450:670, 80:480, :3] * a, a * 255]).astype(np.float32))
    best = min((float(np.mean(np.abs(features[a] - features[b]))), a, b)
               for a in range(32) for b in range(a + 48, 121))
    _, start, end = best
    sources['walk']['loop_range'] = [start, end]
    sources['walk']['join_mae'] = best[0]
    clips = {
        'idle': {'order': seq('greet', list(range(45)) + list(range(43, 0, -1))), 'next': 'idle'},
        'wave': {'order': seq('greet', list(range(121)) + list(range(119, 0, -1))), 'next': 'idle'},
        'turn': {'order': seq('turn', list(range(121)) + list(range(119, 0, -1))), 'next': 'idle'},
        'walk_in': {'order': seq('turn', range(45)), 'next': 'walk'},
        'walk': {'order': seq('walk', range(start, end)), 'next': 'walk'},
        'walk_out': {'order': seq('turn', range(44, -1, -1)), 'next': 'idle'},
    }
    (OUT / 'frames').mkdir(exist_ok=True)
    for i, f in enumerate(frames):
        cv2.imwrite(str(OUT / 'frames' / f'frame_{i:04d}.png'), f, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    boxes = np.array([box(f) for f in frames])
    bounds = [int(boxes[:, 0].min()), int(boxes[:, 1].min()), int(boxes[:, 2].max()), int(boxes[:, 3].max())]
    manifest = {'version': 2, 'fps': 24, 'canvas': [580, 700], 'frames': len(frames),
                'pattern': 'frames/frame_{index:04d}.png', 'anchor': [280, 660], 'bounds': bounds,
                'revision': 'hq-enclosed-iris', 'source_pixel_scale': 1,
                'sources': sources, 'clips': clips,
                'notes': ['待机、挥手、转身及走路退出含原帧倒放，不含生成补帧。',
                          '双手放下视频与单手抬手姿势不匹配，已处理存档但不强接。',
                          '仅向左行走；未镜像角色，未制作向右走路。',
                          '跨视频接点并非同一原帧，可能有轻微姿态差异。',
                          '平台标识和原视频保留于参考视频2，输出仅提取中央角色。']}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'bounds': bounds, 'walk_loop': [start, end], 'walk_join_mae': best[0]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
