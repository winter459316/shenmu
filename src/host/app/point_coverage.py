"""Serve old/new viewers with consistent point footprints at both HDMI sizes."""
def augment(html):
    before='const ratio=external?1:Math.min(devicePixelRatio||1,2)'
    after='const ratio=external?outputHeight/360:Math.min(devicePixelRatio||1,2)'
    if html.count(before)!=1:raise ValueError('Unsupported HDMI point-size integration')
    return html.replace(before,after,1)
