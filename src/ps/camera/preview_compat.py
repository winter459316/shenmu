"""Only a qualified, bound section image may reuse the preview engines."""
import json
from pathlib import Path
def preview_compatible(digest,base):
    if digest==base:return True
    try:
        p=json.loads((Path(__file__).resolve().parent/'section_preview_compat.json').read_text())
        return bool(p['qualified'] and p['preview_base_sha256']==base and p['sha256']==digest)
    except (OSError,ValueError,KeyError):return False
