"""Turn user-supplied fixed-camera green-screen videos into an optional pack."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def matte(frame, protect_eyes=False):
    """Key green only; do not erase text, logos, or add character features."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([35, 22, 0]), np.array([88, 255, 255]))
    mask = 255 - green
    if protect_eyes:
        # Small enclosed green iris regions near warm face colors. Never paint
        # a fixed opaque ellipse over a moving character or its background.
        n, labels, stats, _ = cv2.connectedComponentsWithStats(green)
        b, g, r = [channel.astype(np.int16) for channel in cv2.split(frame)]
        skin = ((r - b > 12) & (r - g > 3) & (r > 150) & (b > 100)).astype(np.uint8)
        near_skin = cv2.dilate(skin, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
        for k in range(1, n):
            x, y, w, h, area = stats[k]
            if 4 <= area <= 800 and w <= 50 and h <= 50:
                region = labels[y:y+h, x:x+w] == k
                if (np.percentile(frame[y:y+h, x:x+w, 1][region], 90) > 190
                        and np.mean(near_skin[y:y+h, x:x+w][region]) > .5):
                    mask[y:y+h, x:x+w][region] = 255
    alpha = cv2.GaussianBlur(mask.astype(np.float32) / 255, (3, 3), .5)
    color = frame.astype(np.float32) / 255
    edge = (alpha > 0) & (alpha < .99)
    color[:, :, 1][edge] = np.minimum(color[:, :, 1][edge],
                                    np.maximum(color[:, :, 0][edge], color[:, :, 2][edge]))
    return np.uint8(np.clip(np.dstack([color, alpha]) * 255, 0, 255))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', '--idle', dest='idle', type=Path, required=True,
                        help='Your own idle video; no video is bundled with the repository.')
    for action in ('wave', 'turn', 'walk-in', 'walk', 'walk-out'):
        parser.add_argument('--' + action, type=Path)
    for action in ('idle', 'wave', 'turn', 'walk-in', 'walk', 'walk-out'):
        parser.add_argument('--' + action + '-start', type=float, default=0,
                            help='Trim static lead-in, in seconds.')
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'pet-assets')
    parser.add_argument('--fps', type=float, default=24)
    parser.add_argument('--protect-eyes', action='store_true')
    parser.add_argument('--replace', action='store_true', help='Replace an existing generated pack.')
    args = parser.parse_args(argv)
    if not 1 <= args.fps <= 120:
        parser.error('--fps must be between 1 and 120')
    walking = [args.walk_in, args.walk, args.walk_out]
    if any(walking) and not all(walking):
        parser.error('Walking requires --walk-in, --walk and --walk-out together.')
    inputs = {name: getattr(args, name) for name in ('idle', 'wave', 'turn', 'walk_in', 'walk', 'walk_out')
              if getattr(args, name) is not None}
    for name, path in inputs.items():
        if not path.is_file():
            parser.error(f'Input video does not exist: {path}')
        if getattr(args, name + '_start') < 0:
            parser.error('Lead-in trimming must not be negative')
    output = args.output.resolve()
    if (output / 'manifest.json').exists() and not args.replace:
        parser.error('Output already contains a pack. Choose another --output or use --replace.')
    (output / 'frames').mkdir(parents=True, exist_ok=True)
    sources, clips, boxes = {}, {}, []
    count = 0
    canvas = None
    for name, path in inputs.items():
        capture = cv2.VideoCapture(str(path.resolve()))
        if not capture.isOpened():
            raise ValueError(f'Cannot open {path}')
        source_fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not 0 < source_fps <= 240:
            raise ValueError('Invalid source frame rate')
        start = round(getattr(args, name + '_start') * source_fps)
        capture.set(cv2.CAP_PROP_POS_FRAMES, start)
        order = []
        read_count, next_output = 0, 0
        while True:
            ok, image = capture.read()
            if not ok:
                break
            shape = [image.shape[1], image.shape[0]]
            if canvas is None:
                canvas = shape
            if shape != canvas:
                raise ValueError('Use videos with matching canvas sizes and character framing.')
            if read_count + 1 > next_output * source_fps / args.fps:
                frame = matte(image, args.protect_eyes)
                ys, xs = np.where(frame[:, :, 3] >= 160)
                if not len(xs):
                    raise ValueError(f'No foreground found in {name} frame {read_count}')
                boxes.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
                while read_count + 1 > next_output * source_fps / args.fps:
                    target = output / 'frames' / f'frame_{count:04d}.png'
                    if not cv2.imwrite(str(target), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
                        raise OSError(f'Cannot write frame {count}')
                    order.append(count)
                    count += 1
                    next_output += 1
                    if len(order) > 2400:
                        raise ValueError('Keep each source action below 2400 output frames.')
            read_count += 1
        capture.release()
        if not order:
            raise ValueError(f'No frames after trimming {path}')
        # Idle ping-pongs real frames; other user-provided clips play forward.
        if name == 'idle' and len(order) > 2:
            order = order + order[-2:0:-1]
        following = {'walk_in': 'walk', 'walk': 'walk', 'walk_out': 'idle'}.get(name, 'idle')
        clips[name] = {'order': order, 'next': following, 'entry_frame': 0}
        sources[name] = {'file': path.name, 'fps': source_fps, 'frames_read': read_count,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        print(f'Prepared {name}: {next_output} frames', flush=True)
    bounds = [min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)]
    manifest = {'version': 2, 'fps': args.fps, 'canvas': canvas, 'frames': count,
                'pattern': 'frames/frame_{index:04d}.png', 'bounds': bounds,
                'anchor': [(bounds[0] + bounds[2]) / 2, bounds[3]],
                'clips': clips, 'sources': sources, 'source_pixel_scale': 1,
                'notes': ['Generated locally from user-supplied videos. No artwork is bundled.']}
    temporary = output / 'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(output / 'manifest.json')
    print(f'Pack ready: {output}', flush=True)


if __name__ == '__main__':
    main()
