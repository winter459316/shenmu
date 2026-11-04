"""Lossless NPY members with low ZIP compression; array contents are unchanged."""
import io,json,re,zipfile,os
import numpy as np
def pack_result(arrays,metadata):
    if 'metadata_json' in arrays:raise ValueError('Reserved metadata member')
    values=dict(arrays,metadata_json=np.frombuffer(json.dumps(metadata).encode(),np.uint8))
    buffer=io.BytesIO()
    compression=zipfile.ZIP_STORED if os.environ.get('USB_ARCHIVE_STORED','0')=='1' else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(buffer,'w',compression=compression,compresslevel=1,allowZip64=True) as archive:
        for name,value in values.items():
            if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name):raise ValueError('Invalid member name')
            value=np.asarray(value)
            if value.dtype.hasobject:raise ValueError('Object arrays are not permitted')
            with archive.open(name+'.npy','w',force_zip64=True) as member:
                np.lib.format.write_array(member,value,allow_pickle=False)
    return buffer.getvalue()
