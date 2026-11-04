"""Conservative detail layer from two existing board matches of the same photo.

Only spatially supported retained matches shared by Detail and Surface may
replace the smooth display layer. Inferred depth and unsupported pixels keep
the old layer exactly. No texture-to-depth, height gain, or extra measurement.
"""
from dataclasses import dataclass, asdict
from surface_cleanup import np, cv, plane_filter, SurfaceConfig, triangle_stretch
from surface_projection import reproject, check_cancel


@dataclass(frozen=True)
class DetailConfig:
    min_disparity_px: float = 1.
    max_disparity_px: float = 127.
    profile_agreement_px: float = .25
    neighbour_agreement_px: float = .5
    min_neighbours: int = 4
    min_coherent_samples: int = 7
    min_coherent_residual_px: float = 1/32
    min_residual_coherence: float = 1.5
    full_residual_coherence: float = 3.
    topology_iterations: int = 12
    max_filter_change_px: float = 1/16
    filter_blend: float = .5


def retain_surface_detail(detail_q4, surface_q4, measured, baseline, rgb, q,
                          config=DetailConfig(), cancel=None):
    detail = np.asarray(detail_q4, np.float32)/16
    surface = np.asarray(surface_q4, np.float32)/16
    valid = np.asarray(baseline['valid'], bool)
    if any(a.shape != valid.shape for a in (detail, surface, measured)):
        raise ValueError('Detail/Surface/mask must share the reconstruction grid')
    supported = (valid & measured & (detail >= config.min_disparity_px) & (detail < config.max_disparity_px) &
                 (surface >= config.min_disparity_px) & (surface < config.max_disparity_px) &
                 (np.abs(detail-surface) <= config.profile_agreement_px))
    p = np.pad(detail, 1);pv = np.pad(supported, 1)
    neighbours = np.zeros(valid.shape, np.uint8)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if not (dx or dy):continue
            region = (slice(1+dy, 1+dy+valid.shape[0]), slice(1+dx, 1+dx+valid.shape[1]))
            neighbours += pv[region] & (np.abs(p[region]-detail) <= config.neighbour_agreement_px)
    spatial_support = supported & (neighbours >= config.min_neighbours)
    previous = np.asarray(baseline['disparity_px'], np.float32)
    residual = np.where(supported, detail-previous, 0).astype(np.float32)
    box = lambda a:cv.boxFilter(a, -1, (3,3), normalize=False, borderType=cv.BORDER_CONSTANT)
    samples = box(supported.astype(np.float32))
    local_mean = box(residual)/np.maximum(samples, 1)
    variance = np.maximum(0, box(residual*residual)/np.maximum(samples, 1)-local_mean**2)
    local_spread = np.sqrt(variance+(1/64)**2)
    coherence = np.abs(local_mean)/local_spread
    # A bump forms a locally consistent residual against the broad smooth
    # surface. Random high-frequency residuals must not be shown as relief.
    qualified = (spatial_support & (samples >= config.min_coherent_samples) &
                 (np.abs(local_mean) >= config.min_coherent_residual_px) &
                 (coherence >= config.min_residual_coherence) &
                 (residual*local_mean > 0))
    # One small bounded pass preserves narrow features. Support is restricted to
    # consensus pixels: completed holes cannot pull measured detail into a plane.
    local_config = SurfaceConfig(radius=1, spatial_sigma=1., disparity_sigma_px=.18, passes=1)
    filtered = plane_filter(np.where(supported, detail, 0), supported,
                            supported.astype(np.float32), rgb.astype(np.float32), local_config, cancel)
    filtered = detail+np.clip(config.filter_blend*(filtered-detail),
                             -config.max_filter_change_px, config.max_filter_change_px)
    # Feather only inside qualified pixels. Outside them the previous surface
    # remains bit-identical, including all inferred/excluded regions.
    weight = np.where(qualified, (neighbours.astype(np.float32)-config.min_neighbours+1)/
                       (9-config.min_neighbours), 0).astype(np.float32)
    weight *= np.clip((coherence-config.min_residual_coherence)/
                      (config.full_residual_coherence-config.min_residual_coherence), 0, 1)
    initial_weight = weight.copy()
    topology_limited = np.zeros(valid.shape, bool)
    def project_weight():
        output = previous.copy()
        output[qualified] += weight[qualified]*(filtered[qualified]-previous[qualified])
        projected, _, projected_valid = reproject(output, valid, q)
        xyz = baseline['xyz_mm'].copy();xyz[qualified] = projected[qualified]
        return output, xyz, projected_valid
    output, xyz, projected_valid = project_weight()
    # Preserve the old mesh's safe connectivity. Abrupt changes at the boundary
    # of a confidence patch must not create new cracks or stretched triangles.
    faces = baseline.get('grid_faces', np.empty((0,3),np.int32))
    # Only triangles incident to a changed vertex can lose baseline validity.
    # Keep the ordered halving, then remove just the affected updates; a local
    # crack must not erase supported detail elsewhere in the photograph.
    active_faces = faces[(initial_weight.ravel()[faces] > 0).any(axis=1)] if len(faces) else faces
    local_fallback = np.zeros(valid.shape, bool)
    passes = 0
    for iteration in range(config.topology_iterations+9):
        check_cancel(cancel)
        if not len(active_faces):break
        passes += 1
        z = xyz[...,2].ravel()[active_faces]
        bad = (triangle_stretch(xyz,active_faces) > 4.) | (np.ptp(z,axis=1) > np.maximum(5.,.02*z.min(axis=1)))
        if not bad.any():break
        affected = np.zeros(valid.size, bool);affected[active_faces[bad].ravel()] = True
        affected = affected.reshape(valid.shape) & (weight > 0)
        topology_limited |= affected
        if iteration == config.topology_iterations+8 or not affected.any():
            # Bounded final fallback for pathological inputs, followed by an
            # explicit check of every triangle before returning this layer.
            weight.fill(0)
        elif iteration >= config.topology_iterations:
            local_fallback |= affected
            weight[affected] = 0
        else:
            weight[affected] *= .5
        output, xyz, projected_valid = project_weight()
    if len(faces):
        z=xyz[...,2].ravel()[faces]
        if np.any((triangle_stretch(xyz,faces)>4.) | (np.ptp(z,axis=1)>np.maximum(5.,.02*z.min(axis=1)))):
            raise ValueError('Detail layer failed final mesh connectivity check')
    if not np.array_equal(valid, projected_valid):
        raise ValueError('Detail update changed validity of the smooth surface')
    qualified = weight > 0
    delta = xyz[..., 2]-baseline['xyz_mm'][..., 2]
    report = {'version':'surface-detail-v1', 'algorithm':'dual_profile_supported_bounded_local_plane',
              'parameters':asdict(config), 'filter_parameters':asdict(local_config),
              'consensus_points':int(supported.sum()), 'detail_supported_points':int(qualified.sum()),
              'full_weight_points':int((weight == 1).sum()),
              'topology_limited_points':int(topology_limited.sum()),
              'topology_local_fallback_points':int(local_fallback.sum()),
              'topology_checked_triangles_per_pass':len(active_faces), 'topology_passes':passes,
              'topology_fallback_all':bool(initial_weight.any() and not weight.any()),
              'fallback_points':int((valid & ~qualified).sum()), 'processed_points':int(valid.sum()),
              'abs_change_vs_smooth_mm_p50_p90_p99_max':np.percentile(np.abs(delta[qualified]),[50,90,99,100]).tolist() if qualified.any() else [],
              'measurement_accuracy_verified':False, 'new_measurements':False,
              'depth_gain':1., 'inferred_coordinates_unchanged':True,
              'note':'Two matching profiles share cameras and can share errors. This retains existing evidence; it does not validate millimetre accuracy or medical use.'}
    return {'xyz_mm':xyz, 'valid':valid.copy(), 'disparity_px':output,
            'detail_supported':qualified, 'detail_weight':weight,
            'residual_coherence':coherence, 'topology_limited':topology_limited, 'report':report}
