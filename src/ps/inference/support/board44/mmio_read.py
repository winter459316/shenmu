"""Call the native read32 ABI; mapping/ownership validation belongs to caller."""
import ctypes as C
_Read32=C.CFUNCTYPE(C.c_uint32,C.c_void_p,C.c_uint32)
def read_register(io,offset):
    if type(offset) is not int or not 0<=offset<4096 or offset&3:
        raise ValueError('Register read must be aligned within the qualified page')
    if not io.opaque or not io.read32:raise ValueError('Missing caller-owned native mapping')
    return int(_Read32(io.read32)(io.opaque,offset))
