"""One-boot RAM device tree: stop factory PL drivers and reserve owned DMA memory.

No saveenv, flash, boot-file or filesystem image writes. Requires a live Linux
console for --reboot; --uboot continues only from an observed U-Boot prompt.
"""
import re,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/'experiments/usb_camera_20261016'
sys.path.insert(0,str(SOURCE/'deps'))
import serial
log=open(HERE/'reserved_boot.log','a',encoding='utf8')
port=serial.Serial('COM3',115200,timeout=.1,dsrdtr=False,rtscts=False)
def collect(seconds,pattern=None):
    data=bytearray();deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        b=port.read(65536)
        if b:
            data.extend(b);s=b.decode('utf8','replace');log.write(s);log.flush()
        if pattern and re.search(pattern,data):return data.decode('utf8','replace')
    if pattern:raise TimeoutError(data.decode('utf8','replace'))
    return data.decode('utf8','replace')
def send(s):
    for i in range(0,len(s),8):port.write(s[i:i+8].encode());time.sleep(.04)
def uboot(cmd,timeout=20):
    port.reset_input_buffer();send(cmd+'\n');out=collect(timeout,rb'\r?\nZynqMP> ')
    if re.search(r'Unknown command|ERROR|FDT_ERR|Bad Linux ARM64 Image|Wrong Image',out):raise RuntimeError(out)
    print(out,flush=True);return out
try:
    port.reset_input_buffer()
    if sys.argv[1]=='--reboot':
        send("printf 'LINUX_READY='; uname -r\n")
        out=collect(5,rb'ALIENTEK-ZU\+:[^\r\n]*# ')
        assert re.search(r'LINUX_READY=5\.4\.0',out),out
        send("kill $(cat /tmp/usb_stereo_probe/camera.pid); sync; reboot\n")
        out=collect(60,rb'Hit any key to stop autoboot:')
        port.write(b' ');collect(10,rb'\r?\nZynqMP> ')
    elif sys.argv[1]=='--uboot':
        send('\n');collect(5,rb'\r?\nZynqMP> ')
    else:raise ValueError('Use --reboot or --uboot')
    uboot('fatload mmc 0:1 0x10000000 image.ub',30)
    uboot('iminfo 0x10000000',20)
    uboot('bootm start 0x10000000#config-4ev')
    uboot('bootm loados',30)
    uboot('bootm fdt')
    uboot('fdt resize 4096')
    uboot('fdt set /amba_pl@0 status disabled')
    uboot('fdt mknode /reserved-memory usb-pl-dma@60000000')
    uboot('fdt set /reserved-memory/usb-pl-dma@60000000 reg <0x0 0x60000000 0x0 0x08000000>')
    uboot('fdt set /reserved-memory/usb-pl-dma@60000000 no-map')
    out=uboot('fdt print /reserved-memory/usb-pl-dma@60000000')
    assert '60000000' in out and '08000000' in out and 'no-map' in out,out
    uboot('bootm prep')
    send('bootm go\n')
    out=collect(60,rb'ALIENTEK-ZU\+:[^\r\n]*# ')
    print('LINUX_RAM_RESERVED_BOOT_READY',flush=True)
finally:
    port.close();log.close()
