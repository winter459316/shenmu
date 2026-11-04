"""Widen the v5 worker address-space cap; model and inference logic are unchanged."""
import resource
from usable_v5_quad_infer_runtime_pl3_v5_quad import *

resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
