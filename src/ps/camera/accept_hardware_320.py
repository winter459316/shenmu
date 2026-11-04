"""Record reviewed implemented hardware, bound to exact reports and calibration."""
import datetime,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent;H=ROOT/'hdmi_v1';OLD=ROOT.parent/'usb_full/hdmi_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('timing_100mhz.rpt','cdc.rpt','cdc_details.rpt','bus_skew_review.rpt','drc_review.rpt','key_synchronizers.txt','exceptions_review.rpt','usb_full.bit','usb_full.bit.bin'):
    assert (H/name).stat().st_mtime>(ROOT/'completion_verified.txt').stat().st_mtime,'Stale report or bitstream: '+name
assert 'codex.local:stereo:completion_cg:1.1' in (H/'hardware_bd.tcl').read_text()
timing=(H/'timing_100mhz.rpt').read_text()
assert 'All user specified timing constraints are met.' in timing
assert 'There are 0 pins that are not constrained for maximum delay.' in timing
assert 'There are 0 register/latch pins with no clock.' in timing
row=re.search(r'^\s+(\d+\.\d+)\s+0\.000\s+0\s+\d+\s+(\d+\.\d+)\s+0\.000\s+0\s+\d+\s+(\d+\.\d+)\s+0\.000\s+0\s+\d+',timing,re.M)
assert row;wns,whs,wpws=map(float,row.groups());assert min(wns,whs,wpws)>0
cdc=(H/'cdc.rpt').read_text();details=(H/'cdc_details.rpt').read_text()
rows=[s for s in cdc.splitlines() if s.startswith(('Warning ','Info '))]
assert len(rows)==4 and all(s.split()[-3:]==['0','0','0'] for s in rows)
assert re.findall(r'^CDC-\d+\s+(\w+)\s+(\d+)',details,re.M)==[('Info','48'),('Warning','4')]
warnings=[s for s in details.splitlines() if re.match(r'\s+\d+\s+CDC-6',s)]
assert len(warnings)==4 and all('gen_cdc_pntr.' in s or 'AXI4_LITE_INTERFACE.ipif_RdData_reg' in s for s in warnings)
skew=(H/'bus_skew_review.rpt').read_text();assert 'VIOLATED' not in skew
slacks=list(map(float,re.findall(r'Slack \(MET\)\s*:\s*(\d+\.\d+)ns',skew)))
assert len(slacks)==3 and min(slacks)>0
assert 'KEY_SYNCHRONIZERS_PASS' in (H/'key_synchronizers.txt').read_text()
for n in ('key_debounce.v','usb_pl_keys.v','pins.xdc','clock_distribution.xdc','video_clock_tree.v'):
    assert sha(H/n)==sha(OLD/n),n
assert 'USB_PL_KEYS_RTL_PASS' in (OLD/'keys_simulation.log').read_text()
drc=(H/'drc_review.rpt').read_text();assert not re.search(r'\|\s*(Error|Critical Warning)\s*\|',drc)
for name in ('geometry','images','completion'):assert 'CSIM_COSIM_EXPORT_PASS' in (ROOT/(name+'_verified.txt')).read_text()
shutil.copyfile(H/'usb_full.bit.bin',ROOT/'usb320.bit.bin');digest=sha(ROOT/'usb320.bit.bin')
report={'time':datetime.datetime.now().astimezone().isoformat(),'sha256':digest,'bit_sha256':sha(H/'usb_full.bit'),
 'timing_passed':True,'wns_ns':wns,'whs_ns':whs,'wpws_ns':wpws,'cdc_review_passed':True,'bus_skew_slacks_ns':slacks,
 'keys_passed':True,'hls_passed':True,'eye_size':[320,360],'calibration_sha256':sha(ROOT/'stereo_parameters.json'),
 'cdc_review':'Same four vendor CDC groups as 640: three Gray-pointer groups with positive max-delay/bus-skew constraints and one VTC registered data/ack group. All endpoints safe; two-stage key synchronizers verified.',
 'drc_review':'No errors. DSP pipeline advisories, unused VTC IRQ gated-net warning and unused FIFO status nets. Four serialized TMDS outputs retain prior board constraints.',
 'key_rtl_simulation':'Unchanged RTL and pin/clock constraints; prior bounce/press/hold/release/reset simulation pass plus new implemented synchronizer check.',
 'reports':{n:sha(H/n) for n in ('timing_100mhz.rpt','cdc.rpt','cdc_details.rpt','bus_skew_review.rpt','drc_review.rpt','key_synchronizers.txt','exceptions_review.rpt')}}
(ROOT/'hardware_320_verified.json').write_text(json.dumps(report,indent=2))
catalog=ROOT/'hardware_catalog.py';s=catalog.read_text();s=re.sub(r'HDMI_V1_SHA=\x27[0-9a-f]+\x27',"HDMI_V1_SHA='"+digest+"'",s)
s=s.replace("'name':'usb_full_hdmi_v1'","'name':'usb_320_hdmi_v1'")
s='\n'.join(line for line in s.split('\n') if not line.strip().startswith(('STABLE_SHA:{','WINDOW_V4_SHA:{')))
catalog.write_text(s)
print(json.dumps(report))
