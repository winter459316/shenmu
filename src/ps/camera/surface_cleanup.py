"""A separate display surface: bounded edge-aware inverse-depth regularization.

Never overwrite measured disparity/geometry. Filter in disparity space, then
reproject through the same Q so every vertex remains on its original camera ray.
Unsupported completion and severely foreshortened triangles are excluded only
from this derived layer; they remain available in the unprocessed comparison.
"""
from dataclasses import dataclass, asdict
import os
from surface_projection import np, cv, reproject, check_cancel


@dataclass(frozen=True)
class SurfaceConfig:
    radius: int = 3
    spatial_sigma: float = 2.0
    disparity_sigma_px: float = .35
    color_sigma: float = 35.0
    passes: int = 3
    max_disparity_change_px: float = .75
    max_inferred_distance_px: float = 16.
    max_triangle_stretch: float = 4.0


def plane_filter_reference(disparity, valid, confidence, rgb, config, cancel=None):
    """Bilateral weighted local plane. A slanted plane is preserved exactly."""
    h, w = disparity.shape;r = config.radius
    pad = ((r, r), (r, r))
    d = np.pad(disparity, pad, mode='edge')
    weights = np.pad(confidence*valid, pad)
    image = np.pad(rgb.astype(np.float32), (*pad, (0, 0)), mode='edge')
    sums = np.zeros((9, h, w), np.float64)
    for dy in range(-r, r+1):
        check_cancel(cancel)
        for dx in range(-r, r+1):
            region = (slice(r+dy, r+dy+h), slice(r+dx, r+dx+w))
            other = d[region]
            delta = other-disparity
            color_delta = np.mean((image[region]-rgb)**2, axis=-1)
            weight = (np.exp(-(dx*dx+dy*dy)/(2*config.spatial_sigma**2)) *
                      np.exp(-delta**2/(2*config.disparity_sigma_px**2)) *
                      (.25+.75*np.exp(-color_delta/(2*config.color_sigma**2))) * weights[region])
            weight *= np.abs(delta) <= 3*config.disparity_sigma_px
            for accumulator, value in zip(sums, (1., dx, dy, dx*dx, dx*dy, dy*dy, other, other*dx, other*dy)):
                accumulator += weight*value
    sw, sx, sy, sxx, sxy, syy, sd, sxd, syd = sums/np.maximum(sums[0], 1e-12)
    xx, xy, yy = sxx-sx*sx, sxy-sx*sy, syy-sy*sy
    xd, yd = sxd-sx*sd, syd-sy*sd
    determinant = xx*yy-xy*xy
    a = (xd*yy-yd*xy)/np.maximum(determinant, 1e-12)
    b = (yd*xx-xd*xy)/np.maximum(determinant, 1e-12)
    fitted = np.where(determinant > 1e-6, sd-a*sx-b*sy, disparity)
    return np.where(valid, fitted, disparity).astype(np.float32)


def plane_filter(disparity, valid, confidence, rgb, config, cancel=None):
    if os.environ.get('USB_SURFACE_NATIVE','0')=='1':
        from surface_native import plane_filter_native
        return plane_filter_native(disparity,valid,confidence,rgb,config,cancel,threads=3)
    return plane_filter_reference(disparity,valid,confidence,rgb,config,cancel)


def refine_surface(disparity, xyz_mm, preview, measured, rgb, q, config=SurfaceConfig(), cancel=None):
    original = np.asarray(disparity, np.float32)
    valid = np.asarray(preview, bool).copy() & np.isfinite(original) & np.isfinite(xyz_mm).all(axis=-1)
    d = np.where(valid, original, 0).astype(np.float32)
    median = cv.medianBlur(d, 3)
    interior = cv.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8), borderType=cv.BORDER_CONSTANT) != 0
    # Reject isolated disparity spikes only; coherent small protrusions have neighbours.
    count = np.zeros(d.shape, np.uint8)
    p = np.pad(d, 1, mode='edge');pv = np.pad(valid, 1)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if not (dx or dy):continue
            region = (slice(1+dy, 1+dy+d.shape[0]), slice(1+dx, 1+dx+d.shape[1]))
            count += (np.abs(p[region]-d) <= .5) & pv[region]
    isolated = valid & interior & (np.abs(d-median) > 1.) & (count <= 1)
    seeds = valid & measured & ~isolated
    distance = (cv.distanceTransform((~seeds).astype(np.uint8), cv.DIST_L2, 5)
                if seeds.any() else np.full(d.shape, np.inf, np.float32))
    unsupported = valid & ~measured & (distance > config.max_inferred_distance_px)
    valid &= ~(isolated | unsupported)
    confidence = np.where(seeds, 1., .30*np.exp(-distance/12.)).astype(np.float32)
    for _ in range(config.passes):
        filtered = plane_filter(d, valid, confidence, rgb.astype(np.float32), config, cancel)
        d = np.clip(filtered, original-config.max_disparity_change_px,
                    original+config.max_disparity_change_px)
        d = np.where(valid, d, 0).astype(np.float32)
    xyz, _, valid = reproject(d, valid, q)
    delta = xyz[..., 2]-xyz_mm[..., 2]
    adjusted = valid & (np.abs(delta) > .01)
    report = {'algorithm':'bilateral_local_disparity_plane', 'version':'surface-cleanup-v1',
              'parameters':asdict(config), 'input_points':int(preview.sum()),
              'isolated_excluded':int(isolated.sum()), 'unsupported_inference_excluded':int(unsupported.sum()),
              'processed_points':int(valid.sum()), 'adjusted_points':int(adjusted.sum()),
              'abs_depth_change_mm_p50_p90_p99_max':np.percentile(np.abs(delta[valid]), [50,90,99,100]).tolist() if valid.any() else [],
              'original_coordinates_preserved_separately':True, 'measurement_accuracy_verified':False,
              'note':'Derived display coordinates, not new measured depth; steep real surfaces may also be disconnected.'}
    return {'xyz_mm':xyz, 'valid':valid, 'disparity_px':np.where(valid,d,np.nan), 'adjusted':adjusted,
            'isolated_excluded':isolated, 'unsupported_excluded':unsupported, 'support_distance_px':distance,
            'report':report}


def triangle_stretch(xyz_mm, faces):
    if not len(faces):return np.empty(0)
    if os.environ.get('USB_MESH_NATIVE','0')=='1':
        from surface_mesh_native import triangle_stretch_native
        return triangle_stretch_native(xyz_mm,faces)
    corners = xyz_mm.reshape(-1,3)[faces]
    other = np.roll(corners, 1, axis=1)
    # Expected in-plane separation at the mean depth, including non-square image sampling.
    rays = corners/corners[...,2:3];other_rays = other/other[...,2:3]
    footprint = np.linalg.norm(rays-other_rays, axis=2)*(corners[...,2]+other[...,2])/2
    return np.max(np.linalg.norm(corners-other, axis=2)/np.maximum(footprint, 1e-9), axis=1)


def limit_triangle_stretch(xyz_mm, faces, limit=4.):
    return faces[triangle_stretch(xyz_mm, faces) <= limit]
