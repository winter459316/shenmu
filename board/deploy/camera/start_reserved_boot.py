"""Boot the accepted USB runtime's RAM-only device tree after a factory boot.

This reuses the reviewed U-Boot sequence without changing the preserved
usb_full source. No boot files, persistent environment or flash are written.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT.parent / 'usb_full' / 'boot_reserved.py').read_text(encoding='utf8')
source = source.replace("HERE=Path(__file__).resolve().parent", "HERE=Path(__file__).resolve().parent")
source = source.replace("HERE/'reserved_boot.log'", "HERE/'startup_reserved_boot.log'")
old = 'send("kill $(cat /tmp/usb_stereo_probe/camera.pid); sync; reboot\\n")'
assert old in source
source = source.replace(old, 'send("sync; reboot\\n")')
assert sys.argv[1:] in (['--reboot'], ['--uboot'])
exec(compile(source, str(ROOT / 'start_reserved_boot.py'), 'exec'))
