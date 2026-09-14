from __future__ import annotations

import math
from pathlib import Path


class Photo3DError(RuntimeError):
    pass


def _deps():
    try:
        import cv2
        import numpy as np
        return cv2, np
    except Exception as exc:
        raise Photo3DError("3D görselleştirme için OpenCV/NumPy yüklenemedi.") from exc


def _read(path: str, max_width: int = 1100):
    cv2, _ = _deps()
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise Photo3DError(f"Görüntü okunamadı: {Path(path).name}")
    h, w = image.shape[:2]
    if w > max_width:
        scale = max_width / float(w)
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return image


def _normalize_points(points, np):
    if points is None or len(points) == 0:
        return points
    points = np.asarray(points, dtype=np.float32)
    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    if len(points) == 0:
        return points
    center = np.median(points, axis=0)
    points = points - center
    radii = np.linalg.norm(points, axis=1)
    scale = float(np.percentile(radii, 90)) if len(radii) else 1.0
    if scale <= 1e-6:
        scale = 1.0
    return points / scale


def _sample(points, colors, np, limit=9000):
    if len(points) <= limit:
        return points, colors
    idx = np.linspace(0, len(points) - 1, limit).astype(int)
    return points[idx], colors[idx]


def _serialize(points, colors, *, mode: str, source_count: int, quality: dict, surface_faces=None):
    _, np = _deps()
    points = _normalize_points(points, np)
    if points is None or len(points) == 0:
        raise Photo3DError("3D nokta bulutu üretilemedi.")
    colors = np.asarray(colors, dtype=np.uint8)

    # Surface meshes keep their original vertex indexing; sparse point clouds can
    # still be sampled to keep the browser payload small.
    if surface_faces is None:
        points, colors = _sample(points, colors, np)

    payload = {
        "mode": mode,
        "source_count": source_count,
        "diagnostic": False,
        "medical_volume": False,
        "label": "AI destekli 3D dental görselleştirme",
        "warning": "Bu görünüm CBCT/medikal hacim değildir; fotoğraflardan oluşturulan hasta iletişimi ve tedavi sunumu amaçlı görselleştirmedir.",
        "point_count": int(len(points)),
        "points": [[round(float(x), 5), round(float(y), 5), round(float(z), 5)] for x, y, z in points],
        "colors": [[int(r), int(g), int(b)] for b, g, r in colors],
        "quality": quality,
        "render_style": "translucent_dental_surface_v1",
    }
    if surface_faces is not None:
        payload["surface_faces"] = [[int(a), int(b), int(c)] for a, b, c in surface_faces]
    return payload


def reconstruct_single(path: str):
    """Create a smooth single-photo pseudo-depth dental presentation surface."""
    cv2, np = _deps()
    image = _read(path, max_width=720)
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 30, 30)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    value = hsv[:, :, 2]
    saturation = hsv[:, :, 1]
    mask = ((value > max(70, int(np.percentile(value, 42)))) & (saturation < 225)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)

    norm = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(norm, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(norm, cv2.CV_32F, 0, 1, ksize=3)
    relief = cv2.GaussianBlur((1.0 - norm) * 0.72 + np.sqrt(gx * gx + gy * gy) * 0.28, (0, 0), 3.0)

    # Use a regular grid so the browser can draw a genuine triangle surface
    # instead of only a cloud of dots. The mask keeps the model focused on the
    # visible oral region and the grid remains small enough for mobile devices.
    stride = max(4, int(max(h, w) / 115))
    yv = np.arange(0, h, stride, dtype=np.int32)
    xv = np.arange(0, w, stride, dtype=np.int32)
    valid_grid = mask[np.ix_(yv, xv)] > 0
    if int(valid_grid.sum()) < 150:
        valid_grid = np.ones((len(yv), len(xv)), dtype=bool)

    index_grid = np.full(valid_grid.shape, -1, dtype=np.int32)
    points = []
    colors = []
    for gy_i, yy in enumerate(yv):
        for gx_i, xx in enumerate(xv):
            if not valid_grid[gy_i, gx_i]:
                continue
            z0 = float(relief[yy, xx])
            px = (float(xx) - w / 2.0) / max(1.0, float(w))
            py = -(float(yy) - h / 2.0) / max(1.0, float(w))
            points.append((px, py, z0))
            colors.append(image[yy, xx])
            index_grid[gy_i, gx_i] = len(points) - 1

    points = np.asarray(points, dtype=np.float32)
    colors = np.asarray(colors, dtype=np.uint8)
    if len(points) < 3:
        raise Photo3DError("3D yüzey üretilemedi.")

    z = points[:, 2]
    points[:, 2] = (z - float(np.median(z))) * 0.62

    faces = []
    rows, cols = index_grid.shape
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = int(index_grid[r, c])
            b = int(index_grid[r, c + 1])
            d = int(index_grid[r + 1, c])
            e = int(index_grid[r + 1, c + 1])
            if a >= 0 and b >= 0 and d >= 0:
                faces.append((a, d, b))
            if b >= 0 and d >= 0 and e >= 0:
                faces.append((b, d, e))

    coverage = float(mask.mean())
    return _serialize(
        points,
        colors,
        mode="single_view_photo_surface",
        source_count=1,
        quality={"mask_coverage": round(coverage, 3), "metric_scale": False, "surface_mesh": bool(faces)},
        surface_faces=faces if faces else None,
    )


def _pair_reconstruction(img1, img2):
    cv2, np = _deps()
    g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY); g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=6000, scaleFactor=1.15, nlevels=10, fastThreshold=7)
    k1, d1 = orb.detectAndCompute(g1, None); k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(k1) < 80 or len(k2) < 80:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(d1, d2, k=2)
    good = [m for m, n in pairs if m.distance < 0.72 * n.distance]
    if len(good) < 45:
        return None
    p1 = np.float32([k1[m.queryIdx].pt for m in good]); p2 = np.float32([k2[m.trainIdx].pt for m in good])
    h, w = g1.shape[:2]
    focal = 1.15 * max(w, h); K = np.array([[focal, 0, w / 2.0], [0, focal, h / 2.0], [0, 0, 1]], dtype=np.float64)
    E, inliers = cv2.findEssentialMat(p1, p2, K, method=cv2.RANSAC, prob=0.999, threshold=1.4)
    if E is None:
        return None
    _, R, t, pose_mask = cv2.recoverPose(E, p1, p2, K, mask=inliers)
    keep = pose_mask.ravel() > 0
    p1 = p1[keep]; p2 = p2[keep]
    if len(p1) < 30:
        return None
    P1 = K @ np.hstack([np.eye(3), np.zeros((3, 1))]); P2 = K @ np.hstack([R, t])
    hom = cv2.triangulatePoints(P1, P2, p1.T, p2.T); pts = (hom[:3] / hom[3]).T
    positive = np.isfinite(pts).all(axis=1) & (pts[:, 2] > 0) & (pts[:, 2] < np.percentile(pts[:, 2][pts[:, 2] > 0], 97) if np.any(pts[:, 2] > 0) else False)
    pts = pts[positive]; p1 = p1[positive]
    if len(pts) < 25:
        return None
    xi = np.clip(np.round(p1[:, 0]).astype(int), 0, w - 1); yi = np.clip(np.round(p1[:, 1]).astype(int), 0, h - 1)
    colors = img1[yi, xi]
    return pts, colors, len(good), int(keep.sum())


def reconstruct_multiview(paths: list[str]):
    cv2, np = _deps()
    images = [_read(p) for p in paths[:8]]
    if len(images) < 2:
        return reconstruct_single(paths[0])
    base = images[0]
    all_points = []; all_colors = []; matches = 0; inliers = 0
    for other in images[1:]:
        if other.shape[:2] != base.shape[:2]:
            other = cv2.resize(other, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_AREA)
        pair = _pair_reconstruction(base, other)
        if pair is None:
            continue
        pts, colors, m, i = pair
        all_points.append(pts); all_colors.append(colors); matches += m; inliers += i
    if not all_points:
        fallback = reconstruct_single(paths[0])
        fallback["mode"] = "multiview_fallback_single_surface"
        fallback["source_count"] = len(paths)
        fallback["quality"]["sfm_failed"] = True
        return fallback
    points = np.concatenate(all_points, axis=0); colors = np.concatenate(all_colors, axis=0)
    return _serialize(points, colors, mode="multiview_sparse_sfm", source_count=len(paths), quality={"feature_matches": matches, "pose_inliers": inliers, "metric_scale": False})


def reconstruct(paths: list[str]):
    clean = [p for p in paths if p]
    if not clean:
        raise Photo3DError("En az bir ağız içi fotoğraf gerekli.")
    if len(clean) == 1:
        return reconstruct_single(clean[0])
    return reconstruct_multiview(clean)
