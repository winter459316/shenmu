"""Explicit, verified USB compute ABI versions; never infer a bitstream identity.

The original image remains supported for replay and rollback. Registering an
image here does not reconfigure PL or promote a running service.
"""
STABLE_SHA='8183863c879beb5bec68fc1e6a42e8b20df0a8ba4149af0e35871e9a0d0d854d'
WINDOW_V4_SHA='1b357aa3fe695f5f77239e8aedb85b4bb51accd4d3ab33867951d69750e99db1'
HDMI_V1_SHA='1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4'
HDMI_FILTER_SHA='6b0152644538c2490f287006c0f84de62361c83a3e7e1de1e2fd1099e082a313'
HDMI_PREVIEW_SHA='27883d7f7a4a0b4bb5ca13bf7a2df542c99ced3a47db03ccf9a378448c2ff302'
HDMI_TRIM_SHA='a2aa96c1d04ed5d035ec09ac8ef4371867fe8fc3b8639c3ed03c1cd0e30d1052'
HDMI_VESSEL_SHA='65501f0896032a4d55a2158dd5379869cf8d2e38058ddd0cee6812ab7fffc77a'
HDMI_SECTION_SHA = '3d166a23a3dd3d60a2cc3a34d43b3b5dc76878edd6522f4f3de620688ac758fe'
HDMI_VESSEL_STRONG_SHA='4fbf1037deb94ebcefdb2636f2322f3a8644dc02dbbcc3f7b61e36461db48916'
VARIANTS={
    HDMI_VESSEL_STRONG_SHA:{'name':'usb_320_vessel_preview_gain225_v2','sgm_revision':None,'hdmi':True,'pl_keys':True,'filters':True,'preview':True,'legacy_compute':False},
    HDMI_VESSEL_SHA:{'name':'usb_320_vessel_preview_v1','sgm_revision':None,'hdmi':True,'pl_keys':True,'filters':True,'preview':True,'legacy_compute':False},
    HDMI_TRIM_SHA:{'name':'usb_320_preview_trim_v1','sgm_revision':None,'hdmi':True,'pl_keys':True,'filters':True,'preview':True,'legacy_compute':False},
    HDMI_PREVIEW_SHA:{'name':'usb_320_hdmi_preview_v1','sgm_revision':0x53574E34,'hdmi':True,'pl_keys':True,'filters':True,'preview':True},
    HDMI_FILTER_SHA:{'name':'usb_320_hdmi_filters_v1','sgm_revision':0x53574E34,'hdmi':True,'pl_keys':True,'filters':True},
    HDMI_V1_SHA:{'name':'usb_320_hdmi_v1','sgm_revision':0x53574E34,'hdmi':True,'pl_keys':True},
}
def variant(digest):
    from preview_compat import preview_compatible
    if digest not in VARIANTS and preview_compatible(digest,HDMI_VESSEL_STRONG_SHA):
        return dict(VARIANTS[HDMI_VESSEL_STRONG_SHA],name='usb_320_section_v1',section=True)
    if not isinstance(digest,str) or digest not in VARIANTS:raise ValueError('Unverified USB bitstream')
    return dict(VARIANTS[digest])
def loaded_variant(record):
    if record.get('version')!='usb_full_v2' or record.get('state')!='operating':raise ValueError('USB hardware is not operating')
    return variant(record.get('sha256'))
def result_variant(metadata):
    item=variant(metadata.get('bitstream_sha256'))
    if metadata.get('hardware_variant',item['name'])!=item['name']:raise ValueError('Hardware variant label mismatch')
    revision=item['sgm_revision']
    if revision is not None and metadata.get('sgm_revision')!=revision:raise ValueError('Missing or wrong SGM hardware revision')
    return item

# Preserved preview ABI: retain old saved photos and register the 2026 image.
for _digest in (HDMI_SECTION_SHA, '96802d44051c4bac8ce75704894771543e5dca4e94a77c4f6b460a6beb327af4'):
    VARIANTS[_digest]={'name':'usb_320_section_v1','sgm_revision':None,'hdmi':True,'pl_keys':True,'filters':True,'preview':True,'legacy_compute':False,'section':True}

# Selected 2026.1 preview, with historical saved-photo variants retained.
HDMI_SECTION_SHA = '96802d44051c4bac8ce75704894771543e5dca4e94a77c4f6b460a6beb327af4'
