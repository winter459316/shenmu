"""Parallel aligned reads under the existing OwnedMemory capability checks."""
import ctypes as C


class CopyOut4:
    def __init__(self, library):
        self.lib = C.CDLL(str(library))
        self.lib.fpc1_copyout4_abi.argtypes = []
        self.lib.fpc1_copyout4_abi.restype = C.c_uint32
        assert self.lib.fpc1_copyout4_abi() == 0x344f5043
        self.lib.fpc1_copyout4.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t]
        self.lib.fpc1_copyout4.restype = C.c_int

    def download(self, transport, address, size):
        pointer = transport._pointer(address, size)
        buffer = (C.c_uint32 * (size // 4))()
        transport.check()
        rc = self.lib.fpc1_copyout4(C.addressof(buffer), pointer, size)
        if rc:
            raise RuntimeError('Aligned parallel download failed: ' + str(rc))
        transport.check()
        return bytes(buffer)
