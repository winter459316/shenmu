"""Access only caller-supplied, source-qualified mappings under a held lease.

This module cannot open /dev/mem, configure PL, reset, close a mapping or unlock
ownership. Image/reservation/AXI-drain verification belongs to the caller.
"""
import ctypes as C
from native_runtime_20261027 import IO


class OwnedMemory:
    def __init__(self,library,registers,memory,physical_base,*,assert_owned,assert_image_loaded):
        if (len(registers)<4096 or not len(memory) or len(memory)%4
                or type(physical_base) is not int or physical_base%4096
                or not 0x60000000<=physical_base<physical_base+len(memory)<=0x67000000):
            raise ValueError('Invalid caller-owned FPC1 register or reserved-data mapping')
        self.assert_owned=assert_owned
        self.assert_image_loaded=assert_image_loaded
        self.base=physical_base
        self.size=len(memory)
        self.lib=C.CDLL(str(library))
        self.reg_view=(C.c_ubyte*len(registers)).from_buffer(registers)
        self.mem_view=(C.c_ubyte*len(memory)).from_buffer(memory)
        self.reg_address=C.addressof(self.reg_view)
        self.mem_address=C.addressof(self.mem_view)
        if (self.reg_address|self.mem_address)&3:
            raise ValueError('Mappings require naturally aligned word addresses')
        self.keepalive=(registers,memory,self.reg_view,self.mem_view)
        self.lib.fpc1_bind_mapped.argtypes=[C.POINTER(IO),C.c_void_p]
        self.lib.fpc1_bind_mapped.restype=None
        for name in ('fpc1_copy_to_owned','fpc1_copy_from_owned'):
            f=getattr(self.lib,name);f.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];f.restype=C.c_int
        self.lib.fpc1_owned_fence.argtypes=[];self.lib.fpc1_owned_fence.restype=None
        self.io=IO()
        self.check()
        # Binding fills function pointers; it does not read any register.
        self.lib.fpc1_bind_mapped(C.byref(self.io),self.reg_address)

    def check(self):
        self.assert_owned()
        self.assert_image_loaded()

    def _pointer(self,address,size):
        if (type(address) is not int or type(size) is not int or size<=0 or (address|size)&3
                or address<self.base or size>self.size or address-self.base>self.size-size):
            raise ValueError('Transfer escaped the caller-owned mapping')
        return self.mem_address+address-self.base

    def upload(self,address,data):
        pointer=self._pointer(address,len(data))
        buffer=(C.c_uint32*(len(data)//4)).from_buffer_copy(data)
        self.check()
        rc=self.lib.fpc1_copy_to_owned(pointer,C.addressof(buffer),len(data))
        if rc:raise RuntimeError('Aligned upload failed: '+str(rc))
        self.check()

    def download(self,address,size):
        pointer=self._pointer(address,size)
        buffer=(C.c_uint32*(size//4))()
        self.check()
        rc=self.lib.fpc1_copy_from_owned(C.addressof(buffer),pointer,size)
        if rc:raise RuntimeError('Aligned download failed: '+str(rc))
        self.check()
        return bytes(buffer)

    def barrier(self):
        self.check()
        self.lib.fpc1_owned_fence()
        self.check()
