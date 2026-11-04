"""One-second count of newly presented content; never HDMI scan frequency."""
class FrameRate:
    def __init__(self):self.source=None;self.started=0;self.count=0;self.value=None;self.last_key=None
    def select(self,source,now):
        if source!=self.source:
            self.source=source;self.started=now;self.count=0;self.value=None;self.last_key=None
    def presented(self,key,now):
        if key is not None and key!=self.last_key:self.count+=1;self.last_key=key
        if now-self.started>=1:
            self.value=self.count/(now-self.started);self.count=0;self.started=now
    def label(self):
        if self.source in ('raw_disparity','standby') or ((self.source or '').startswith('fast_') and not (self.source or '').startswith('fast_live_')):return 'FPS: 0.0 (STILL)'
        return 'FPS: --' if self.value is None else 'FPS: %.1f'%self.value
    def draw(self,canvas):
        # Preserve backend FPS diagnostics without changing HDMI pixels.
        pass
