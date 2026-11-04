"""Project interface between the web cutting plane and the SEC1 PL mask.

Coordinates enter in millimetres. One FP32 packet drives both the PL request
and the browser geometry, avoiding two independently rounded cutting planes.
This is display geometry, not reconstruction of unobserved internal anatomy.
"""
import numpy as np

MASK_SIZE = 512
PARAMETER_WORDS = 16


def _bounds_corners(metadata):
    bounds = np.asarray(metadata['bounds_mm'], dtype=float)
    if bounds.shape != (2, 3) or not np.isfinite(bounds).all():
        raise ValueError('Expected finite 2x3 millimetre bounds')
    if (bounds[1] < bounds[0]).any():
        raise ValueError('Bounds must be ordered')
    # Binary order: Z changes fastest, matching the established packet contract.
    choices = ((np.arange(8)[:, None] >> np.array([2, 1, 0])) & 1)
    return bounds[choices, np.arange(3)]


def plane(metadata, normal, position, flip=False):
    """Map UI position [0,100] to the bounds' projected extent, without mutation.

    Packet words: normal+d [0:4], in-plane U [4:7], V [7:10],
    square viewport origin [10:12], pixels/mm [12], reserved zeros [13:16].
    Flip is a display-side selection; it does not change the PL plane equation.
    """
    direction = np.array(normal, dtype=float, copy=True)
    if (direction.shape != (3,) or not np.isfinite(direction).all()
            or np.linalg.norm(direction) < .5):
        raise ValueError('Invalid plane normal')
    direction /= np.linalg.norm(direction)
    position = float(position)
    if not np.isfinite(position) or not 0 <= position <= 100:
        raise ValueError('Invalid plane position')
    corners = _bounds_corners(metadata)
    projected = corners @ direction
    offset = float(projected.min() + (projected.max() - projected.min()) * position / 100)

    # Use the least-aligned coordinate axis to avoid a near-zero cross product.
    reference = np.eye(3)[np.argmin(abs(direction))]
    u = np.cross(direction, reference)
    u /= np.linalg.norm(u)
    v = np.cross(direction, u)
    uv = corners @ np.stack([u, v], axis=1)
    span = max(1, float(np.ptp(uv, axis=0).max()) * 1.02)
    lower = (uv.min(0) + uv.max(0)) / 2 - span / 2
    packet = np.zeros(PARAMETER_WORDS, dtype='<f4')
    packet[:4] = [*direction, -offset]
    packet[4:7], packet[7:10] = u, v
    packet[10:12], packet[12] = lower, MASK_SIZE / span
    return packet, render_geometry(packet, position, flip)


def render_geometry(params, position, flip):
    """Derive browser coordinates from the *returned* PL packet in metres."""
    packet = np.asarray(params, dtype='<f4')
    if (packet.shape != (PARAMETER_WORDS,) or not np.isfinite(packet).all()
            or packet[12] <= 0 or not np.any(packet[:3])):
        raise ValueError('Invalid SEC1 projection packet')
    normal, u, v = (packet[a:b].astype(float) for a, b in ((0, 3), (4, 7), (7, 10)))
    origin = -float(packet[3]) * normal / (normal @ normal)
    left, bottom = packet[10:12]
    right, top = left + MASK_SIZE / packet[12], bottom + MASK_SIZE / packet[12]
    corners = np.array([origin + u*x + v*y
                        for x, y in ((left, bottom), (right, bottom),
                                     (right, top), (left, top))]) / 1000
    return dict(plane_m=(packet[:4] * np.array([1, 1, 1, .001], np.float32)).tolist(),
                corners_m=corners.tolist(), pixel_mm=float(1 / packet[12]),
                position=position, flip=bool(flip))
