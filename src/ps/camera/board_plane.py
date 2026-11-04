"""A53 display-plane correction after completion and before PL projection."""
import time
import numpy as np
from plane_guard import improve
VERSION='edge-supported-dominant-plane-v1'

def apply(a,cancel=None):
    started=time.monotonic()
    if cancel and cancel():raise InterruptedError('Plane correction cancelled')
    q,changed,regions,report=improve(a['rectified_left'],a['completed_disparity_q4'],a['completion_origin'],a['domain'])
    if cancel and cancel():raise InterruptedError('Plane correction cancelled')
    # Original matching/completion and section coordinates remain immutable.
    a['dense_disparity_px']=q.astype(np.float32)/16
    a['dense_origin']=a['dense_origin'].copy();a['dense_origin'][changed]=5
    report.update(version=VERSION,engine='A53 robust low-texture plane correction',
                  seconds=time.monotonic()-started,changed_retained_matches=int((changed&(a['completion_origin']==0)).sum()),
                  original_geometry_preserved=True,physical_accuracy_verified=False,
                  downstream='Corrected Q4 to PL XYZ; A53 full-grid mesh',origin_label_5='plane estimate')
    return report
