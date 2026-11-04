"""Load only the timing-verified USB full candidate into volatile PL memory."""
import hashlib,json,mmap,os,re,struct,time
from pathlib import Path
from board_dma import reservation
ROOT=Path(__file__).resolve().parent
EXPECTED='8183863c879beb5bec68fc1e6a42e8b20df0a8ba4149af0e35871e9a0d0d854d'
reservation()
assert not list(Path('/sys/bus/platform/devices').glob('a0*/driver'))
pid_file=ROOT.parent/'camera.pid'
if pid_file.exists():
    proc=Path('/proc')/pid_file.read_text().strip()/'environ'
    if proc.exists():assert b'USB_USE_PL=1' not in proc.read_bytes(),'Stop the v1 PL camera service before reconfiguring'
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
def reg(address):
    with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=address&~4095) as m:return struct.unpack_from('<I',m,address&4095)[0]
widths={'hpm0':reg(0xFD615000),'hp2_read':reg(0xFD3A0000),'hp2_write':reg(0xFD3A0014)};os.close(fd)
assert widths['hpm0']&0x300==0x200,widths
assert widths['hp2_read']&3==0 and widths['hp2_write']&3==0,widths
clock=Path('/sys/kernel/debug/clk/clk_summary').read_text()
row=next(s.split() for s in clock.splitlines() if s.split() and s.split()[0]=='pl0_ref')
rate=int(row[4]);assert 99000000<=rate<=100000000,rate
bit=ROOT/'usb_full.bit.bin';assert hashlib.sha256(bit.read_bytes()).hexdigest()==EXPECTED
path=Path('/sys/module/firmware_class/parameters/path');previous=path.read_text().strip()
try:
    path.write_text(str(ROOT));Path('/sys/class/fpga_manager/fpga0/flags').write_text('0')
    start=time.monotonic();Path('/sys/class/fpga_manager/fpga0/firmware').write_text(bit.name)
    state=Path('/sys/class/fpga_manager/fpga0/state').read_text().strip();assert state=='operating'
    result={'version':'usb_full_v2','state':state,'sha256':EXPECTED,'load_seconds':time.monotonic()-start,'clock_hz':rate,'width_registers':widths,'volatile':True,'dma_reservation':reservation()}
    (ROOT/'loaded.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    fault=ROOT/'dma.fault'
    if fault.exists():fault.unlink()
finally:path.write_text(previous)
