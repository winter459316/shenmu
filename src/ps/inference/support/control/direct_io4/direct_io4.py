"""Direct contiguous tensor copies inside an existing OwnedMemory capability."""
import ctypes as C


class DirectIO4:
    def __init__(self,library):
        self.lib=C.CDLL(str(library))
        self.lib.fpc1_direct_io4_abi.argtypes=[]
        self.lib.fpc1_direct_io4_abi.restype=C.c_uint32
        assert self.lib.fpc1_direct_io4_abi()==0x344f4944
        self.lib.fpc1_direct_io4.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_uint]
        self.lib.fpc1_direct_io4.restype=C.c_int

    def copy(self,transport,address,array,*,upload):
        if not array.flags.c_contiguous or array.dtype.kind!='f' or array.dtype.itemsize!=4 or not array.dtype.isnative:
            raise ValueError('Expected a contiguous native FP32 tensor')
        if not upload and not array.flags.writeable:
            raise ValueError('Readback destination must be writable')
        size=int(array.nbytes);host=int(array.ctypes.data)
        if not size or (size|host)&3:raise ValueError('Expected a nonempty word-aligned tensor')
        device=transport._pointer(address,size)
        transport.check()
        destination,source=(device,host) if upload else (host,device)
        rc=self.lib.fpc1_direct_io4(destination,source,size,int(upload))
        if rc:raise RuntimeError('Direct tensor copy failed: '+str(rc))
        transport.check()

    def upload_from(self,transport,address,array):
        self.copy(transport,address,array,upload=True)

    def download_into(self,transport,address,array):
        self.copy(transport,address,array,upload=False)
