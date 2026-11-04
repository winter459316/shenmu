"""Fresh reserved-boot payload; warm updates use switch_hdmifps_board instead."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
names='''usb_full_engine.py board_dma.py board_geometry.py board_completion.py
full_runtime.py full_camera.py result_archive.py restore_held.py
surface_cleanup.py surface_detail.py surface_holes.py surface_projection.py
surface_native.py surface_mesh_native.py board_surface.py
hdmi_output.py preview_zoom.py fast_console.py photo_views.py hdmi_fps.py raw_disparity_hdmi.py physical_keys.py hardware_catalog.py preview_hardware.py switch_320_board.py
dma_barrier.so hdmi_mmio.so usb_completion.so libsurface_native.so libsurface_mesh.so
stereo_parameters.json rectification_maps.npz
dense_fill.py dense_geometry.py board_plane.py plane_guard.py mesh_limits.py
preview_compat.py section_preview_compat.json shared_preview.py vessel_enhance.py pl_filters.py filter_dma.so filters_config.json filters_verified.json pl_preview.py preview_dma.so preview_config.json preview_verified.json preview_modes.py preview_rectify.py preview_native.so auto_exposure.py tone_map.py
usb320.bit.bin hardware_320_verified.json cold_start_board.py
held_restore.json held_restore.npz'''.split()
files=[ROOT/name for name in names];assert all(p.is_file() for p in files)
for p in files:
    if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
(ROOT/'startup_payload_sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
subprocess.run([sys.executable,'-X','utf8',str(ROOT/'deploy.py'),*map(str,files),str(ROOT/'startup_payload_sha256.json')],check=True)

