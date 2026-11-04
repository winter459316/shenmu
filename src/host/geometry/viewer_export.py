"""Data-only PLY packaging; preserved old viewer file format."""
from pathlib import Path
import numpy as np

def viewer_intrinsics(q):
    """Intrinsics for this exact rectified grid, including area-average centres."""
    q=np.asarray(q,float)
    return [float(q[2,3]/q[0,0]),float(q[2,3]/q[1,1]),
            float(-q[0,3]/q[0,0]),float(-q[1,3]/q[1,1])]

VERTEX_DTYPE = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
                         ('red', 'u1'), ('green', 'u1'), ('blue', 'u1'),
                         ('provenance', 'u1'), ('image_u', '<u2'), ('image_v', '<u2')])

FACE_DTYPE = np.dtype([('count', 'u1'), ('indices', '<i4', (3,)), ('estimated', 'u1')])

def save_ply(path, xyz_mm, rgb, provenance, valid, grid_faces=None, comments=()):
    flat = np.flatnonzero(valid)
    points = xyz_mm.reshape(-1, 3)[flat]/1000.
    vertices = np.empty(len(flat), VERTEX_DTYPE)
    for i, name in enumerate(('x', 'y', 'z')):
        vertices[name] = points[:, i]
    for i, name in enumerate(('red', 'green', 'blue')):
        vertices[name] = rgb.reshape(-1, 3)[flat, i]
    vertices['provenance'] = provenance.ravel()[flat]
    vertices['image_u'], vertices['image_v'] = flat % valid.shape[1], flat // valid.shape[1]
    faces = np.empty(0, FACE_DTYPE)
    if grid_faces is not None:
        mapping = np.full(valid.size, -1, np.int32);mapping[flat] = np.arange(len(flat))
        indices = mapping[grid_faces]
        if np.any(indices < 0):
            raise ValueError('Mesh refers to an excluded vertex')
        faces = np.empty(len(indices), FACE_DTYPE)
        faces['count'] = 3;faces['indices'] = indices
        faces['estimated'] = np.any(provenance.ravel()[grid_faces] != 0, axis=1)
    header = ['ply', 'format binary_little_endian 1.0',
              'comment units metres; rectified CAM0 +X right +Y down +Z forward',
              'comment provenance 0=retained_match 1=local_plane_estimate 2=guided_estimate 4=rejected_candidate_estimate 5=display_plane_estimate 6=neural_network_estimate',
              f'element vertex {len(vertices)}', 'property float x', 'property float y', 'property float z',
              'property uchar red', 'property uchar green', 'property uchar blue', 'property uchar provenance',
              'property ushort image_u', 'property ushort image_v']
    if grid_faces is not None:
        header += [f'element face {len(faces)}', 'property list uchar int vertex_indices', 'property uchar estimated']
    header += ['comment '+line for line in comments]
    header += ['end_header', '']
    with Path(path).open('wb') as f:
        f.write('\n'.join(header).encode('ascii'));f.write(vertices.tobytes());f.write(faces.tobytes())
    return vertices, faces
