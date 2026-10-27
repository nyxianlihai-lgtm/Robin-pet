"""Key the supplied green-screen video into a transparent character sequence.

Uses real source frames only. No generated poses, optical flow, or body rig.
OpenCV/NumPy are build-time tools, not runtime desktop dependencies.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "参考视频1" / "3b0f3f020d6c42588032c7e1c2cc5a3b.mp4"


def matte(frame):
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([35, 45, 30]), np.array([88, 255, 255]))
    # The character is central; retain a fixed ROI, not moving per-frame crops.
    roi = np.zeros((height, width), np.uint8)
    roi[:round(height * 0.935), round(width * 0.28):round(width * 0.72)] = 255
    non_green = cv2.bitwise_and(cv2.bitwise_not(green), roi)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(non_green, 8)
    if count < 2:
        raise ValueError("No character detected")
    body_index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = stats[body_index, :4]
    # Green irises must remain opaque. This ellipse stays inside the head and
    # follows its bounding box; all keying math is bypassed inside this region.
    protect = np.zeros_like(green)
    cv2.ellipse(protect, (round(x + w * 0.5), round(y + h * 0.50)),
                (round(w * 0.26), round(h * 0.13)), 0, 0, 360, 255, -1)
    foreground = cv2.bitwise_and(cv2.bitwise_or(non_green, protect), roi)
    # Remove isolated codec specks, but preserve disconnected halo ornaments.
    count, components, component_stats, _ = cv2.connectedComponentsWithStats(foreground, 8)
    keep = np.zeros(count, np.uint8)
    for index in range(1, count):
        if component_stats[index, cv2.CC_STAT_AREA] >= 12:
            keep[index] = 255
    foreground = keep[components]
    kernel = np.ones((3, 3), np.uint8)
    inside = cv2.erode(foreground, kernel, iterations=1) > 0
    outside = cv2.dilate(foreground, kernel, iterations=2) == 0

    color = frame.astype(np.float32) / 255
    # Estimate the actual, uneven green-screen color rather than assuming #00ff00.
    background_pixels = color[(green > 0) & (roi == 0)]
    background = np.median(background_pixels[::16], axis=0)
    excess = color[:, :, 1] - np.maximum(color[:, :, 0], color[:, :, 2])
    screen_excess = max(0.05, float(background[1] - max(background[0], background[2])))
    alpha = np.clip(1 - np.maximum(excess, 0) / screen_excess, 0, 1)
    alpha[inside] = 1
    alpha[outside] = 0
    alpha[protect > 0] = 1
    alpha[roi == 0] = 0
    # Undo green background contribution only on semi-transparent contour pixels.
    edge = (alpha > 0.001) & (alpha < 0.999)
    straight = color.copy()
    straight[edge] = np.clip((color[edge] - (1 - alpha[edge, None]) * background) / alpha[edge, None], 0, 1)
    premultiplied = straight * alpha[:, :, None]
    small_rgb = cv2.resize(premultiplied, (640, 360), interpolation=cv2.INTER_AREA)
    small_alpha = cv2.resize(alpha, (640, 360), interpolation=cv2.INTER_AREA)
    straight_small = np.divide(small_rgb, small_alpha[:, :, None], out=np.zeros_like(small_rgb),
                               where=small_alpha[:, :, None] > 1e-5)
    rgba = np.dstack((straight_small, small_alpha))
    # Fixed translation: source feet are at y=329 on a 640x360 canvas.
    rgba = cv2.warpAffine(rgba, np.float32([[1, 0, 4], [0, 1, 1]]), (640, 360),
                          flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
    return np.uint8(np.clip(rgba * 255, 0, 255))  # BGRA for OpenCV encoders


def composite(frame, color):
    rgb = frame[:, :, :3].astype(np.float32)
    alpha = frame[:, :, 3:4].astype(np.float32) / 255
    return np.uint8(np.clip(rgb * alpha + np.array(color) * (1 - alpha), 0, 255))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    capture = cv2.VideoCapture(str(SOURCE))
    if not capture.isOpened():
        raise RuntimeError("Cannot open source video")
    fps = capture.get(cv2.CAP_PROP_FPS)
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    qa = ROOT / "qa" / "video-idle"
    qa.mkdir(parents=True, exist_ok=True)
    output = ROOT / "assets" / "video_idle"
    if not args.inspect:
        (output / "frames").mkdir(parents=True, exist_ok=True)
        (qa / "png").mkdir(exist_ok=True)
    samples = {0, round(count * 0.27), round(count * 0.54), count - 1}
    bounds = []
    frames = []
    for index in range(count):
        ok, source = capture.read()
        if not ok:
            raise RuntimeError(f"Source decode failed at frame {index}")
        if args.inspect and index not in samples:
            continue
        frame = matte(source)
        visible = np.argwhere(frame[:, :, 3] >= 160)
        bounds.append([int(visible[:, 1].min()), int(visible[:, 0].min()),
                       int(visible[:, 1].max()) + 1, int(visible[:, 0].max()) + 1])
        if index in samples:
            cv2.imwrite(str(qa / f"sample_{index:04d}.png"), frame)
            preview = np.hstack([composite(frame, (245, 245, 250)), composite(frame, (39, 34, 45))])
            cv2.imwrite(str(qa / f"edges_{index:04d}.jpg"), preview)
        if not args.inspect:
            cv2.imwrite(str(output / "frames" / f"frame_{index:04d}.webp"), frame,
                        [cv2.IMWRITE_WEBP_QUALITY, 101])
            cv2.imwrite(str(qa / "png" / f"frame_{index:04d}.png"), frame)
            frames.append(frame)
        if index % 30 == 0:
            print(f"Processed {index + 1}/{count}", flush=True)
    capture.release()
    if args.inspect:
        print("Inspection frames:", qa)
        return
    boxes = np.array(bounds)
    union = [int(boxes[:, 0].min()), int(boxes[:, 1].min()), int(boxes[:, 2].max()), int(boxes[:, 3].max())]
    # No morphing: a ping-pong idle loop has source-adjacent frames at both joins.
    # Slow idle motion remains intact; this avoids a first/last pose hard cut.
    order = list(range(count)) + list(range(count - 2, 0, -1))
    manifest = {"version": 1, "fps": fps, "canvas": [640, 360], "frames": count,
                "pattern": "frames/frame_{index:04d}.webp", "order": order,
                "anchor": [320, 330], "bounds": union, "loop": "ping-pong",
                "source": str(SOURCE.relative_to(ROOT)), "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                "source_duration": count / fps, "sleep_frame": min(count - 1, round(fps * 1.33)),
                "attribution": "源视频右下角含‘千问AI平台生成’标识；原文件保留。输出只提取中央角色层。"}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "frames": count, "bounds": union,
                      "loop_frames": len(order), "fps": fps}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
