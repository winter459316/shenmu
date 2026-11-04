"""Clone current RAM modules, then replace only the explicit preview update."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
p=ROOT/'deploy.py';text=p.read_text();text=text.replace('/usb320_exposure','/usb320_tonemap');p.write_text(text)
code="from pathlib import Path;import shutil;s=Path('/tmp/usb_stereo_probe/usb320_exposure');d=s.parent/'usb320_tonemap';d.mkdir(exist_ok=False);files=[p for p in s.iterdir() if p.is_file() and p.suffix in ('.py','.so','.npz','.bin','.json') and 'private' not in p.name];[shutil.copy2(p,d/p.name) for p in files];print('CLONED',len(files))"
print(command('python3 -c "'+code+'"',10))
names=['tone_map.py','full_camera.py','shared_preview.py','switch_tone_board.py','switch_direct3d_board.py','test_tone.py','tone_input.png']
for name in names:
    p=ROOT/name
    if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
subprocess.run([sys.executable,'-X','utf8',str(ROOT/'deploy.py'),*[str(ROOT/n) for n in names]],check=True)
