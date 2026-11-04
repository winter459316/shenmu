"""Optional native pause callback. Never reads/writes a register or native State."""
import ctypes as C

class SpinPause:
    def __init__(self,io,library):
        self.io=io;self.library=C.CDLL(str(library))
        self.library.fpc1_spin_abi.argtypes=[];self.library.fpc1_spin_abi.restype=C.c_uint32
        if self.library.fpc1_spin_abi()!=0x314e5053:raise ValueError('Incorrect spin callback ABI')
        f=self.library.fpc1_spin_pause;f.argtypes=[C.c_void_p];f.restype=None
        self.pointer=C.cast(f,C.c_void_p).value;self.previous=io.pause
        if not self.pointer or not self.previous or not io.opaque:raise ValueError('Unbound callback transport')
        io.pause=self.pointer
    def restore_callback(self):
        if self.io.pause!=self.pointer:raise RuntimeError('Pause callback owner changed')
        self.io.pause=self.previous
