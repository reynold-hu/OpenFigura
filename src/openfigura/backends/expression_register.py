"""CPU-only registration of the hm08 face-unit base mesh onto a character.

Anchors come from the CC0 targets themselves on the base side (the centroid
of each channel's moved vertices is an anatomical landmark by construction),
and from MediaPipe landmarks back-projected through the render's recorded
orthographic camera on the character side. Umeyama similarity fit, then the
caller verifies: jawOpen vertices must land in the character's jaw band.
"""
from __future__ import annotations
import numpy as np

BASE_ANCHOR_CHANNELS = {
    'eyeL': 'eyeBlinkLeft', 'eyeR': 'eyeBlinkRight',
    'mouthL': 'mouthSmileLeft', 'mouthR': 'mouthSmileRight',
    'jaw': 'jawOpen', 'nose': 'noseSneerLeft',
}
# MediaPipe FaceMesh landmark indices for the matching character anchors.
CHARACTER_LANDMARK_INDICES = {'eyeL': 159, 'eyeR': 386, 'mouthL': 61,
                              'mouthR': 291, 'jaw': 152, 'nose': 1}


def gltf_to_blender_world(positions: np.ndarray) -> np.ndarray:
    """glTF Y-up coordinates -> the Z-up world the render camera lives in."""
    return np.asarray(positions, dtype=float)[:, [0, 2, 1]] * np.array([1.0, -1.0, 1.0])


def anchor_from_target(base_positions: np.ndarray, indices) -> np.ndarray:
    """Centroid of the vertices a channel moves — its anatomical anchor."""
    picked = base_positions[list(indices)]
    if len(picked) < 3:
        raise ValueError('anchor needs at least three moved vertices')
    return picked.mean(axis=0)


def camera_basis(location, center) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Screen-right, screen-up and view axes of the render camera."""
    location = np.asarray(location, dtype=float)
    center = np.asarray(center, dtype=float)
    z = location - center
    z = z / np.linalg.norm(z)
    x = np.cross([0.0, 0.0, 1.0], z)
    if np.linalg.norm(x) < 1e-9:
        raise ValueError('camera axis degenerate')
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    return x, y, z


def project_pixel(u: float, v: float, camera: dict) -> tuple[float, float]:
    """Orthographic pixel -> in-plane (right, up) offsets from view center."""
    width, height = camera['resolution']
    scale = float(camera['ortho_scale'])
    return ((u / width - 0.5) * scale, (0.5 - v / height) * scale * (height / width))


def character_anchor(plane_xy, positions: np.ndarray, camera: dict,
                     head_band: float = 0.75) -> np.ndarray:
    """Nearest head-band character vertex to a back-projected camera-plane point."""
    x_axis, y_axis, _ = camera_basis(camera['camera_location'], camera['center'])
    projected = np.stack([positions @ x_axis, positions @ y_axis], axis=1)
    up = int(np.argmax(positions.max(axis=0) - positions.min(axis=0)))
    lo, hi = positions[:, up].min(), positions[:, up].max()
    band_mask = positions[:, up] > lo + head_band * (hi - lo)
    band = positions[band_mask]
    band_projected = projected[band_mask]
    if len(band) == 0:
        raise ValueError('no character vertices in head band')
    distances = np.linalg.norm(band_projected - np.asarray(plane_xy, dtype=float), axis=1)
    best = int(np.argmin(distances))
    diagonal = float(np.linalg.norm(positions.max(axis=0) - positions.min(axis=0)))
    if distances[best] > 0.05 * diagonal:
        raise ValueError('back-projected landmark found no nearby head vertex')
    return band[best].copy()


def umeyama(source: np.ndarray, destination: np.ndarray) -> dict:
    """Least-squares similarity (scale, rotation, translation) source->destination."""
    source = np.asarray(source, dtype=float)
    destination = np.asarray(destination, dtype=float)
    if source.shape != destination.shape or source.shape[0] != 3 or source.shape[1] < 3:
        raise ValueError('umeyama needs matching (3,N) point sets with N>=3')
    mu_s, mu_d = source.mean(axis=1), destination.mean(axis=1)
    ds, dd = source - mu_s[:, None], destination - mu_d[:, None]
    cov = dd @ ds.T / source.shape[1]
    u_mat, sing, vt = np.linalg.svd(cov)
    reflection = np.sign(np.linalg.det(u_mat @ vt))
    rotation = u_mat @ np.diag([1, 1, reflection]) @ vt
    var_s = float((ds ** 2).sum() / source.shape[1])
    scale = float((sing * np.array([1, 1, reflection])).sum() / var_s) if var_s > 1e-12 else 1.0
    translation = mu_d - scale * rotation @ mu_s
    residual = destination - (scale * (rotation @ source) + translation[:, None])
    return {'scale': scale, 'rotation': rotation.tolist(), 'translation': translation.tolist(),
            'rms_residual': float(np.sqrt((residual ** 2).sum(axis=0).mean()))}


def landmarks_to_pixel(landmarks, pixel_size) -> dict:
    """Pixel coordinates for the anchor landmarks from normalized MediaPipe points."""
    width, height = pixel_size
    return {name: (landmarks[index][0] * width, landmarks[index][1] * height)
            for name, index in CHARACTER_LANDMARK_INDICES.items()}
