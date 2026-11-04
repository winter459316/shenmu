"""Display-only multiscale dark-ridge contrast; no segmentation or new detail.

Integer CPU reference for PL PXP1 command 5. Each stereo eye is independent.
Support radii 1/2/4 pixels, four directions, continuity rejection for isolated
dark pixels, bounded gain, and shadow/highlight protection. Original pixels,
geometry, capture and inference never consume the enhanced display image.
"""
import numpy as np

def apply(frame):
    assert frame.dtype==np.uint8 and frame.ndim==3 and frame.shape[2]==3
    h,w=frame.shape[:2];assert w%2==0 and w>=32 and h>=9
    out=frame.copy();ew=w//2
    for eye in range(2):
        image=frame[:,eye*ew:(eye+1)*ew].astype(np.int16)
        signal=(3*image[:,:,1]+image[:,:,0]+2)>>2
        def at(dy,dx):return signal[4+dy:h-4+dy,4+dx:ew-4+dx]
        center=at(0,0);response=np.zeros_like(center)
        for dy,dx in ((0,1),(1,0),(1,1),(1,-1)):
            # Along-line neighbors must support the dark center. This rejects
            # isolated pixel noise without blurring the displayed morphology.
            along=(at(dx,-dy)+at(-dx,dy)+1)>>1
            supported=np.maximum(center,along)
            for radius in (1,2,4):
                flanks=np.minimum(at(radius*dy,radius*dx),at(-radius*dy,-radius*dx))
                response=np.maximum(response,flanks-supported-3)
        response=np.clip(response,0,24)
        gate=np.minimum(np.clip((center-12)*4,0,64),np.clip((244-center)*4,0,64))
        delta=(((response*9+2)>>2)*gate+32)>>6
        pixels=image[4:h-4,4:ew-4]
        # Near-white specular pixels are never darkened.
        delta=np.where(pixels.min(axis=2)>220,0,delta)
        out[4:h-4,eye*ew+4:(eye+1)*ew-4]=np.clip(pixels-delta[:,:,None],0,255).astype(np.uint8)
    return out
