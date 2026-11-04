"""Explicit runtime payload, preserving the sibling 640 program."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
NAMES='''usb_full_engine.py board_dma.py board_geometry.py board_completion.py
full_runtime.py full_camera.py board_surface.py result_archive.py restore_held.py
surface_cleanup.py surface_detail.py surface_holes.py surface_projection.py
surface_native.py surface_mesh_native.py
hdmi_output.py physical_keys.py hardware_catalog.py
dma_barrier.so hdmi_mmio.so usb_completion.so libsurface_native.so libsurface_mesh.so
stereo_parameters.json rectification_maps.npz
switch_320_board.py serve_results.py test_pipeline_320_board.py
native_test_frame.npz case_320.json'''.split()
if __name__=='__main__':
    names=NAMES+sys.argv[1:]
    files=[ROOT/n for n in names]
    assert all(p.is_file() for p in files)
    for p in files:
        if p.suffix=='.py':compile(p.read_text(encoding='utf8'),str(p),'exec')
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'deploy.py'),*map(str,files)],check=True)
    (ROOT/'deployed_runtime_manifest.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
