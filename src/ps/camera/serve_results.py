"""Bounded evidence transfer to the connected PC; explicit result filenames only."""
from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import time,sys
ROOT=Path(__file__).resolve().parent
DEFAULT={'hardware_verified.json','hardware_result.npz','loaded.json','core_identities_verified.json','dma_reservation_verified.json','hardware_test.log'}
ALLOWED=DEFAULT|{'completion_verified.json','completion_result.npz','completion_test.log','full_pipeline_result.npz','full_pipeline_verified.json','full_pipeline_test.log','completion_cancel_verified.json'}
NAMES=set(sys.argv[1:]) if len(sys.argv)>1 else DEFAULT
ALLOWED|={'surface_result.npz','surface_verified.json','surface_test.log','packing_low_verified.json','packing_test.log'}
ALLOWED|={'surface_native_result.npz','surface_native_verified.json','surface_native_full_verified.json','native_surface_test.log','native_surface_full.log'}
ALLOWED|={'surface_holes_profile.json','surface_holes_profile.log'}
ALLOWED|={'small_holes_result.npz','small_holes_verified.json'}
ALLOWED|={'small_holes_reference_result.npz','small_holes_reference_verified.json'}
ALLOWED|={'sgm_v4_result.npz','sgm_v4_verified.json','sgm_v4_test.log'}
ALLOWED|={'sgm_v4_full_result.npz','sgm_v4_full_verified.json','sgm_v4_full_test.log','sgm_v4_full_compat_failure.json'}
ALLOWED|={'hdmi_full_result.npz','hdmi_full_verified.json','hdmi_full_test.log'}
ALLOWED|={'hdmi_before_activation.zip','hdmi_activation.json','hdmi_service_active.json','physical_keys_status.json','physical_keys_hdmi.log'}
ALLOWED|={'preview_before_update.zip','preview_service_active.json'}
ALLOWED|={'photo_speed_mesh_verified.json','photo_speed_full_verified.json','photo_speed_update_verified.json','photo_archive_verified.json','photo_stored_result.npz','photo_speed_before_update.zip','photo_speed_service_active.json'}
ALLOWED|={'pipeline_320_result.npz','pipeline_320_verified.json','pipeline_320.log','activation_320.json','completion_320_reference.json'}
ALLOWED|={'dense_replay.npz','dense_replay_status.json','dense_replay_verified.json','test_dense.log','autofill_activation.json'}
ALLOWED|={'geometry_replay.npz','geometry_replay_status.json','dense_geometry_replay_verified.json','replay.log','dense3d_activation.json'}
ALLOWED|={'fast3d_activation.json'}
ALLOWED|={'direct3d_activation.json'}
ALLOWED|={'preview_activation.json','rectified_preview_verified.json','preview_live_verified.json','hdmi_rectified.png'}
ALLOWED|={'shared_activation.json','shared_preview_verified.json','preview_native_verified.json','preview_speed_before.json','preview_speed_shared_only.json','preview_speed_after.json'}
assert NAMES and NAMES<=ALLOWED
pending=set(NAMES)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        name=self.path.lstrip('/')
        if self.client_address[0]!='192.168.137.1' or name not in NAMES:self.send_error(403);return
        data=(ROOT/name).read_bytes();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);pending.discard(name)
s=HTTPServer(('192.168.137.2',8769),H);s.timeout=1;deadline=time.monotonic()+45
while pending and time.monotonic()<deadline:s.handle_request()
s.server_close()
