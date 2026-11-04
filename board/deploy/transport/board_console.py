"""Bounded serial access to the existing Linux console; no boot/flash operations."""
import base64
import hashlib
import pathlib
import re
import sys
import time
import uuid
import zlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'deps'))
import serial


def command(command, timeout=15):
    token = 'END_' + uuid.uuid4().hex
    with serial.Serial('COM3', 115200, timeout=0.1, dsrdtr=False, rtscts=False) as port:
        port.reset_input_buffer()
        payload = (command + "; printf '\\n" + token + "\\n'\n").encode()
        for offset in range(0, len(payload), 8):
            port.write(payload[offset:offset+8])
            time.sleep(0.04)
        data = bytearray()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            data.extend(port.read(65536))
            if re.search(rb'[\r\n]' + token.encode() + rb'[\r\n]', data):
                return data.decode('utf-8', errors='replace')
        port.write(b'\x03')
        time.sleep(0.2)
        data.extend(port.read(65536))
        raise TimeoutError(data.decode('utf-8', errors='replace'))


def upload(local, remote):
    if not re.fullmatch(r'/tmp/usb_stereo_probe/[a-zA-Z0-9_.-]+', remote):
        raise ValueError('Uploads are restricted to the RAM-backed probe directory')
    content = pathlib.Path(local).read_bytes()
    encoded = base64.b64encode(zlib.compress(content)).decode()
    print(command("mkdir -p /tmp/usb_stereo_probe; : > /tmp/usb_stereo_probe/upload.b64"))
    for offset in range(0, len(encoded), 120):
        command("printf '%s' '" + encoded[offset:offset+120] + "' >> /tmp/usb_stereo_probe/upload.b64")
    unpack = "import base64,zlib,pathlib,hashlib; p=pathlib.Path('" + remote + "'); p.write_bytes(zlib.decompress(base64.b64decode(pathlib.Path('/tmp/usb_stereo_probe/upload.b64').read_bytes()))); print(hashlib.sha256(p.read_bytes()).hexdigest())"
    result = command('python3 -c "' + unpack + '"')
    if hashlib.sha256(content).hexdigest() not in result:
        raise RuntimeError('Upload SHA256 mismatch: ' + result)
    print('UPLOAD_SHA256_PASS', remote)


if __name__ == '__main__':
    if sys.argv[1] == 'upload':
        upload(sys.argv[2], sys.argv[3])
    else:
        print(command(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 15))
