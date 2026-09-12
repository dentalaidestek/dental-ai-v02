from __future__ import annotations

import math
from pathlib import Path


def _cv2():
    try:
        import cv2
        import numpy as np
        return cv2, np
    except Exception:
        return None, None


def load_gray(image_path: str):
    cv2, _ = _cv2()
    if cv2 is None or not Path(image_path).is_file():
        return None
    return cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)


def clip_bbox(bbox, width: int, height: int):
    if not bbox or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
    x1 = max(0, min(width - 1, x1)); x2 = max(x1 + 1, min(width, x2))
    y1 = max(0, min(height - 1, y1)); y2 = max(y1 + 1, min(height, y2))
    return x1, y1, x2, y2


def bbox_iou(a, b) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ax1, ay1, ax2, ay2 = map(float, a); bx1, by1, bx2, by2 = map(float, b)
    ix1, iy1 = max(ax1, bx1), max(ay1, by1); ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1); bb = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    den = aa + bb - inter
    return inter / den if den else 0.0


def bbox_distance(a, b) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return float("inf")
    ax1, ay1, ax2, ay2 = map(float, a); bx1, by1, bx2, by2 = map(float, b)
    dx = max(bx1 - ax2, ax1 - bx2, 0.0); dy = max(by1 - ay2, ay1 - by2, 0.0)
    return math.hypot(dx, dy)


def patch_stats(gray, bbox) -> dict:
    _, np = _cv2()
    if gray is None or np is None:
        return {}
    h, w = gray.shape[:2]
    clipped = clip_bbox(bbox, w, h)
    if not clipped:
        return {}
    x1, y1, x2, y2 = clipped
    patch = gray[y1:y2, x1:x2]
    if patch.size < 16:
        return {}
    p10, p50, p90 = [float(v) for v in np.percentile(patch, [10, 50, 90])]
    return {
        "mean": float(patch.mean()),
        "std": float(patch.std()),
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "bright_fraction": float((patch >= max(180.0, p90)).mean()),
        "dark_fraction": float((patch <= min(75.0, p10)).mean()),
        "width": int(patch.shape[1]),
        "height": int(patch.shape[0]),
    }


def expand_bbox(bbox, fraction: float = 0.2):
    x1, y1, x2, y2 = map(float, bbox)
    dx = (x2 - x1) * fraction; dy = (y2 - y1) * fraction
    return [x1 - dx, y1 - dy, x2 + dx, y2 + dy]


def tooth_root_bbox(tooth: dict):
    bbox = tooth.get("bbox") or []
    if len(bbox) != 4:
        return None
    x1, y1, x2, y2 = map(float, bbox)
    fdi = str(tooth.get("fdi") or "")
    if fdi[:1] in {"1", "2"}:  # maxilla: roots are superior on panorama
        return [x1, y1, x2, y1 + (y2 - y1) * 0.68]
    return [x1, y1 + (y2 - y1) * 0.32, x2, y2]


def tooth_crown_bbox(tooth: dict):
    bbox = tooth.get("bbox") or []
    if len(bbox) != 4:
        return None
    x1, y1, x2, y2 = map(float, bbox)
    fdi = str(tooth.get("fdi") or "")
    if fdi[:1] in {"1", "2"}:
        return [x1, y1 + (y2 - y1) * 0.58, x2, y2]
    return [x1, y1, x2, y1 + (y2 - y1) * 0.42]


def apical_bbox(tooth: dict):
    root = tooth_root_bbox(tooth)
    if not root:
        return None
    x1, y1, x2, y2 = root
    fdi = str(tooth.get("fdi") or "")
    margin = (y2 - y1) * 0.38
    if fdi[:1] in {"1", "2"}:
        return [x1 - (x2-x1)*0.15, y1 - margin*0.55, x2 + (x2-x1)*0.15, y1 + margin]
    return [x1 - (x2-x1)*0.15, y2 - margin, x2 + (x2-x1)*0.15, y2 + margin*0.55]


def line_score(gray, bbox) -> float:
    cv2, np = _cv2()
    if gray is None or cv2 is None or np is None:
        return 0.0
    h, w = gray.shape[:2]; clipped = clip_bbox(bbox, w, h)
    if not clipped:
        return 0.0
    x1, y1, x2, y2 = clipped; patch = gray[y1:y2, x1:x2]
    if min(patch.shape[:2]) < 8:
        return 0.0
    edges = cv2.Canny(patch, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=max(8, int(min(patch.shape) * 0.18)), minLineLength=max(6, int(min(patch.shape) * 0.20)), maxLineGap=3)
    if lines is None:
        return 0.0
    total = sum(math.hypot(xb-xa, yb-ya) for xa, ya, xb, yb in lines[:, 0])
    diag = max(1.0, math.hypot(patch.shape[1], patch.shape[0]))
    return min(1.0, float(total / (diag * 4.0)))


def root_curvature_score(gray, tooth: dict) -> float:
    cv2, np = _cv2(); root = tooth_root_bbox(tooth)
    if gray is None or cv2 is None or np is None or not root:
        return 0.0
    h, w = gray.shape[:2]; clipped = clip_bbox(root, w, h)
    if not clipped:
        return 0.0
    x1, y1, x2, y2 = clipped; patch = gray[y1:y2, x1:x2]
    if min(patch.shape[:2]) < 10:
        return 0.0
    edges = cv2.Canny(patch, 45, 140)
    ys, xs = np.nonzero(edges)
    if len(xs) < 20:
        return 0.0
    bins = np.linspace(ys.min(), ys.max() + 1, 7)
    centers = []
    for a, b in zip(bins[:-1], bins[1:]):
        sel = xs[(ys >= a) & (ys < b)]
        if len(sel) >= 3:
            centers.append(float(np.median(sel)))
    if len(centers) < 4:
        return 0.0
    first = centers[0]; last = centers[-1]
    linear = [first + (last-first)*i/(len(centers)-1) for i in range(len(centers))]
    deviation = max(abs(a-b) for a, b in zip(centers, linear)) / max(1.0, patch.shape[1])
    return min(1.0, deviation * 4.0)


def condyle_signals(gray) -> dict:
    cv2, np = _cv2()
    if gray is None or cv2 is None or np is None:
        return {}
    h, w = gray.shape[:2]
    rois = {
        "left": [0, 0, int(w * 0.23), int(h * 0.34)],
        "right": [int(w * 0.77), 0, w, int(h * 0.34)],
    }
    result = {}
    for side, bbox in rois.items():
        x1, y1, x2, y2 = bbox; patch = gray[y1:y2, x1:x2]
        blur = cv2.GaussianBlur(patch, (5, 5), 0)
        edges = cv2.Canny(blur, 40, 120)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contours = [c for c in contours if cv2.contourArea(c) >= patch.size * 0.003]
        if not contours:
            result[side] = {"bbox": bbox, "area": 0.0, "flatness": 0.0, "roughness": 0.0}
            continue
        c = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(c)); peri = float(cv2.arcLength(c, True))
        x, y, cw, ch = cv2.boundingRect(c)
        circularity = (4.0 * math.pi * area / (peri * peri)) if peri > 0 else 0.0
        flatness = max(0.0, min(1.0, (cw / max(1.0, ch) - 1.0) / 2.0))
        roughness = max(0.0, min(1.0, 1.0 - circularity))
        result[side] = {"bbox": bbox, "area": area, "width": cw, "height": ch, "flatness": flatness, "roughness": roughness}
    if result.get("left") and result.get("right"):
        la = result["left"].get("area", 0.0); ra = result["right"].get("area", 0.0)
        lh = result["left"].get("height", 0.0); rh = result["right"].get("height", 0.0)
        area_asym = abs(la-ra) / max(1.0, max(la, ra)); height_asym = abs(lh-rh) / max(1.0, max(lh, rh))
        result["asymmetry"] = max(area_asym, height_asym)
    return result
