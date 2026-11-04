import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
code="from pathlib import Path;import shutil;s=Path('/tmp/usb_stereo_probe/usb320_rawhdmi');d=s.parent/'usb320_lowlatency';d.mkdir(exist_ok=False);files=[p for p in s.iterdir() if p.is_file() and p.suffix in ('.py','.so','.npz','.bin','.json','.png') and 'private' not in p.name];[shutil.copy2(p,d/p.name) for p in files];print('CLONED',len(files))"
print(command('python3 -c "'+code+'"',10))
names=['full_camera.py','shared_preview.py','hdmi_output.py','switch_lowlatency_board.py','test_lowlatency.py','test_rawhdmi.py']
subprocess.run([sys.executable,'-X','utf8',str(ROOT/'deploy.py'),*[str(ROOT/n) for n in names]],check=True)
