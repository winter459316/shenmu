"""Fresh reserved-boot payload; warm updates use switch_viewmodes_board instead."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
names='''usb_full_engine.py board_dma.py board_geometry.py board_completion.py
full_runtime.py full_camera.py result_archive.py restore_held.py
surface_cleanup.py surface_detail.py surface_holes.py surface_projection.py
surface_native.py surface_mesh_native.py board_surface.py
hdmi_output.py physical_keys.py hardware_catalog.py switch_320_board.py
dma_barrier.so hdmi_mmio.so usb_completion.so libsurface_native.so libsurface_mesh.so
stereo_parameters.json rectification_maps.npz
dense_fill.py dense_geometry.py board_plane.py plane_guard.py mesh_limits.py
shared_preview.py preview_modes.py preview_rectify.py preview_native.so auto_exposure.py tone_map.py
usb320.bit.bin hardware_320_verified.json cold_start_board.py
held_restore.json held_restore.npz'''.split()
files=[ROOT/name for name in names];assert all(p.is_file() for p in files)
for p in files:
    if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
(ROOT/'startup_payload_sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
subprocess.run([sys.executable,'-X','utf8',str(ROOT/'deploy.py'),*map(str,files),str(ROOT/'startup_payload_sha256.json')],check=True)

