"""Project-specific boundary between rectified USB frames and stereo inference.

Fast-FoundationStereo remains the external network/weight source. This module
owns the project's BGR frame layout, symmetric row padding, ordered FP32 input
arithmetic and geometry handoff. It performs no inference or image enhancement.
"""
from dataclasses import dataclass
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class StereoContract:
    """Dimensions describe the calibrated grid, not a request to resize it."""

    width: int = 320
    height: int = 360
    row_alignment: int = 32

    def __post_init__(self):
        if (type(self.width) is not int or type(self.height) is not int
                or type(self.row_alignment) is not int
                or min(self.width, self.height, self.row_alignment) <= 0
                or self.width % self.row_alignment):
            raise ValueError("Expected positive dimensions and an aligned width")

    @property
    def network_height(self):
        return ((self.height + self.row_alignment - 1)
                // self.row_alignment * self.row_alignment)

    @property
    def padding(self):
        extra = self.network_height - self.height
        return extra // 2, extra - extra // 2


DEFAULT_CONTRACT = StereoContract()
_MEAN = np.array((0.485, 0.456, 0.406), dtype=np.float32)[None, :, None, None]
_STD = np.array((0.229, 0.224, 0.225), dtype=np.float32)[None, :, None, None]
_MEAN.setflags(write=False)
_STD.setflags(write=False)


def _frame(value, side, contract):
    image = np.asarray(value)
    if image.dtype != np.uint8:
        raise ValueError(f"{side}: expected uint8 BGR pixels, got {image.dtype}")
    expected = (contract.height, contract.width, 3)
    if image.shape != expected:
        raise ValueError(f"{side}: expected calibrated shape {expected}, got {image.shape}")
    return image


def prepare_inputs(arrays: Mapping, contract=DEFAULT_CONTRACT):
    """Return owned C-contiguous NCHW RGB FP32 tensors, without changing sources.

    Allocate each final tensor once, fill the calibrated interior, then replicate
    the first/last image rows into the padding. Normalization keeps division,
    subtraction and division in that order to match the qualified runtime.
    No resizing, automatic range conversion, filling or normalization fusion.
    """
    frames = {side: _frame(arrays["rectified_" + side], side, contract)
              for side in ("left", "right")}
    top, bottom = contract.padding
    feed = {}
    for side, frame in frames.items():
        tensor = np.empty((1, 3, contract.network_height, contract.width), np.float32)
        interior = tensor[:, :, top:top + contract.height, :]
        np.copyto(interior[0], frame.transpose(2, 0, 1)[::-1])
        if top:
            tensor[:, :, :top, :] = interior[:, :, :1, :]
        if bottom:
            tensor[:, :, top + contract.height:, :] = interior[:, :, -1:, :]
        np.divide(tensor, np.float32(255), out=tensor)
        np.subtract(tensor, _MEAN, out=tensor)
        np.divide(tensor, _STD, out=tensor)
        feed[side + "_image"] = tensor
    return feed


def validate_prediction(disparity, contract=DEFAULT_CONTRACT):
    """Check a completed network result without replacing or casting its array."""
    if not isinstance(disparity, np.ndarray):
        raise ValueError("Expected an ndarray disparity result")
    if disparity.shape != (contract.height, contract.width):
        raise ValueError("Disparity does not match the calibrated image grid")
    if disparity.dtype != np.float32 or not np.isfinite(disparity).all():
        raise ValueError("Expected finite FP32 disparity")
    return disparity


def validate_geometry(disparity, q, domain, contract=DEFAULT_CONTRACT):
    """Validate the PL projection handoff, preserving Q and the original domain."""
    validate_prediction(disparity, contract)
    matrix, mask = np.asarray(q), np.asarray(domain)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("Expected a finite 4x4 calibration Q matrix")
    if mask.shape != disparity.shape or mask.dtype.kind not in "buif":
        raise ValueError("Domain does not match the calibrated image grid")
    if not np.isfinite(mask).all():
        raise ValueError("Domain contains non-finite values")
    return disparity, q, domain
