"""PS-owned FP32 fallback using the existing Python ORT environment."""
from pathlib import Path
import ctypes,traceback
import numpy as np
import onnxruntime as ort
FLOAT=ctypes.POINTER(ctypes.c_float)
SHAPE=ctypes.POINTER(ctypes.c_int64)
CALLBACK=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_char_p,FLOAT,FLOAT,SHAPE,SHAPE)

def install(lib,root):
    allowed={(root/'micro'/(str(i)+'_cpu.onnx')).resolve() for i in (0,1)}
    sessions={}
    @CALLBACK
    def fallback(raw_path,input_pointer,output_pointer,input_shape,output_shape):
        try:
            path=Path(raw_path.decode('utf8')).resolve()
            assert path in allowed
            xs=tuple(int(input_shape[i]) for i in range(5))
            ys=tuple(int(output_shape[i]) for i in range(5))
            assert xs[0]==ys[0]==1 and xs[2:]==ys[2:] and all(0<n<=96 for n in xs[1:])
            assert 0<xs[1]<=32 and 0<ys[1]<=32
            if path not in sessions:
                so=ort.SessionOptions();so.intra_op_num_threads=4;so.inter_op_num_threads=1
                so.enable_cpu_mem_arena=False;so.enable_mem_pattern=False
                so.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
                sessions[path]=ort.InferenceSession(str(path),so,providers=['CPUExecutionProvider'])
            x=np.ctypeslib.as_array(input_pointer,shape=(int(np.prod(xs)),)).reshape(xs)
            y=np.ctypeslib.as_array(output_pointer,shape=(int(np.prod(ys)),)).reshape(ys)
            result=sessions[path].run(None,{'x':x})[0]
            assert result.shape==ys and np.isfinite(result).all()
            np.copyto(y,result)
            return 0
        except BaseException:
            traceback.print_exc()
            return 1
    lib.mixed_set_fallback.argtypes=[CALLBACK]
    lib.mixed_set_fallback.restype=None
    lib.mixed_set_fallback(fallback)
    # The caller must retain the callback until every model session has exited.
    return fallback,sessions
