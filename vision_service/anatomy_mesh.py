from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from urllib.request import Request, urlopen

import numpy as np

VALID_FDI = {
    11,12,13,14,15,16,17,18,
    21,22,23,24,25,26,27,28,
    31,32,33,34,35,36,37,38,
    41,42,43,44,45,46,47,48,
}

TEETHNET_BINVOX = (
    "https://raw.githubusercontent.com/waleedmm/TeethNet-Dataset/main/"
    "SingleObject-SingleTooth/TeethNet-Images-Normal-without-texture-v-400/"
    "{fdi}/viewpoints/rendering/Voxel/model.binvox"
)

class AnatomyMeshError(RuntimeError):
    pass


def _download_binvox(fdi: int) -> bytes:
    if fdi not in VALID_FDI:
        raise AnatomyMeshError(f"Desteklenmeyen FDI: {fdi}")
    req = Request(TEETHNET_BINVOX.format(fdi=fdi), headers={"User-Agent": "DentalAI/3D"})
    try:
        with urlopen(req, timeout=25) as response:
            data = response.read()
    except Exception as exc:
        raise AnatomyMeshError(f"Anatomik diş modeli indirilemedi: {fdi}") from exc
    if not data.startswith(b"#binvox"):
        raise AnatomyMeshError(f"Geçersiz binvox modeli: {fdi}")
    return data


def _parse_binvox(data: bytes) -> np.ndarray:
    stream = BytesIO(data)
    magic = stream.readline().strip()
    if not magic.startswith(b"#binvox"):
        raise AnatomyMeshError("Geçersiz binvox başlığı")

    dims = None
    while True:
        line = stream.readline()
        if not line:
            raise AnatomyMeshError("Eksik binvox data bölümü")
        line = line.strip()
        if line.startswith(b"dim "):
            dims = tuple(int(x) for x in line.split()[1:4])
        elif line == b"data":
            break

    if not dims or len(dims) != 3:
        raise AnatomyMeshError("Binvox boyutları okunamadı")

    raw = np.frombuffer(stream.read(), dtype=np.uint8)
    if raw.size < 2:
        raise AnatomyMeshError("Binvox voxel verisi boş")
    if raw.size % 2:
        raw = raw[:-1]

    values = raw[0::2]
    counts = raw[1::2].astype(np.int64)
    flat = np.repeat(values, counts)
    expected = int(np.prod(dims))
    if flat.size < expected:
        raise AnatomyMeshError("Binvox voxel sayısı eksik")
    flat = flat[:expected]
    volume = flat.reshape(dims).astype(bool)
    volume = np.transpose(volume, (0, 2, 1))
    return volume


def _normalize_vertices(vertices: np.ndarray) -> np.ndarray:
    lo = vertices.min(axis=0)
    hi = vertices.max(axis=0)
    ext = np.maximum(hi - lo, 1e-6)

    long_axis = int(np.argmax(ext))
    remaining = [i for i in range(3) if i != long_axis]
    depth_axis = min(remaining, key=lambda i: ext[i])
    width_axis = next(i for i in remaining if i != depth_axis)

    v = vertices[:, [width_axis, long_axis, depth_axis]].astype(np.float64)
    v -= (v.min(axis=0) + v.max(axis=0)) / 2.0
    y_span = max(float(np.ptp(v[:, 1])), 1e-6)
    v *= 2.25 / y_span

    y = v[:, 1]
    cut_hi = np.quantile(y, 0.82)
    cut_lo = np.quantile(y, 0.18)
    r_hi = np.mean(np.linalg.norm(v[y >= cut_hi][:, [0, 2]], axis=1)) if np.any(y >= cut_hi) else 0.0
    r_lo = np.mean(np.linalg.norm(v[y <= cut_lo][:, [0, 2]], axis=1)) if np.any(y <= cut_lo) else 0.0
    if r_lo > r_hi:
        v[:, 1] *= -1.0

    return v.astype(np.float32)


def _marching_cubes(volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    try:
        from skimage.measure import marching_cubes
        verts, faces, _normals, _values = marching_cubes(
            volume.astype(np.float32), level=0.5, allow_degenerate=False
        )
        return verts.astype(np.float32), faces.astype(np.int32)
    except Exception:
        occupied = np.argwhere(volume)
        vertex_map: dict[tuple[int, int, int], int] = {}
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        dirs = [
            ((-1,0,0), [(0,0,0),(0,0,1),(0,1,1),(0,1,0)]),
            ((1,0,0),  [(1,0,0),(1,1,0),(1,1,1),(1,0,1)]),
            ((0,-1,0), [(0,0,0),(1,0,0),(1,0,1),(0,0,1)]),
            ((0,1,0),  [(0,1,0),(0,1,1),(1,1,1),(1,1,0)]),
            ((0,0,-1), [(0,0,0),(0,1,0),(1,1,0),(1,0,0)]),
            ((0,0,1),  [(0,0,1),(1,0,1),(1,1,1),(0,1,1)]),
        ]
        sx, sy, sz = volume.shape
        for x, y, z in occupied:
            for (dx, dy, dz), corners in dirs:
                nx, ny, nz = x + dx, y + dy, z + dz
                if 0 <= nx < sx and 0 <= ny < sy and 0 <= nz < sz and volume[nx, ny, nz]:
                    continue
                idx = []
                for cx, cy, cz in corners:
                    key = (int(x+cx), int(y+cy), int(z+cz))
                    if key not in vertex_map:
                        vertex_map[key] = len(vertices)
                        vertices.append(tuple(float(v) for v in key))
                    idx.append(vertex_map[key])
                faces.append((idx[0], idx[1], idx[2]))
                faces.append((idx[0], idx[2], idx[3]))
        return np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def _obj_text(vertices: np.ndarray, faces: np.ndarray) -> str:
    lines = ["# DentalAI anatomy mesh from TeethNet binvox"]
    lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vertices)
    lines.extend(f"f {a+1} {b+1} {c+1}" for a, b, c in faces)
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=32)
def anatomy_obj(fdi: int) -> str:
    data = _download_binvox(int(fdi))
    volume = _parse_binvox(data)
    vertices, faces = _marching_cubes(volume)
    if len(vertices) < 50 or len(faces) < 50:
        raise AnatomyMeshError(f"Anatomik mesh üretilemedi: {fdi}")
    vertices = _normalize_vertices(vertices)
    return _obj_text(vertices, faces)
