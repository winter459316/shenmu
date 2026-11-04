"""Inject optional section rendering without rewriting saved photo artifacts."""
def augment(html):
    def change(old,new):
        nonlocal html
        if html.count(old)!=1:raise ValueError('Unsupported viewer section integration: '+old[:50])
        html=html.replace(old,new,1)
    change('out vec3 vColor;out vec3 vPosition;out vec3 vNormal;out vec2 vUv;','out vec3 vColor;out vec3 vPosition;out vec3 vNormal;out vec2 vUv;out vec3 vModel;')
    change('void main(){vec3 world=(position-center)','void main(){vModel=position;vec3 world=(position-center)')
    change('uniform sampler2D photoTexture;','in vec3 vModel;uniform bool cutEnabled;uniform bool cutFlip;uniform vec4 cutPlane;uniform sampler2D photoTexture;')
    change('  if(!isMesh && length(gl_PointCoord','  if(cutEnabled){float d=dot(vec4(vModel,1.),cutPlane);if(cutFlip?-d>0.:d>0.)discard;}\n  if(!isMesh && length(gl_PointCoord')
    change("'photoTexture','useTexture','photoMaterial']","'photoTexture','useTexture','photoMaterial','cutEnabled','cutFlip','cutPlane']")
    change('function render(outputWidth,outputHeight){','function render(outputWidth,outputHeight){\ngl.bindVertexArray(null);gl.useProgram(program);const cut=window.sectionView;gl.uniform1i(u.cutEnabled,!!cut?.enabled);gl.uniform1i(u.cutFlip,!!cut?.flip);gl.uniform4fv(u.cutPlane,cut?.plane||[1,0,0,0]);')
    change('if(sectionIndices.length){','if(window.sectionRender)window.sectionRender();\nif(sectionIndices.length){')
    change('center=usingCamera()?cameraCenter:bounds.map(a=>(a[0]+a[1])/2);','center=window.sectionView?.enabled?window.sectionView.center:(usingCamera()?cameraCenter:bounds.map(a=>(a[0]+a[1])/2));')
    change('function pick(event){let rect=',"function pick(event){if(window.sectionView?.enabled){$('picked').textContent='封盖和背面为显示假设；原始深度可在主界面深度图查询。';return;}let rect=")
    change('</body>','<script src="/section_viewer.js"></script><script src="/viewer_bridge.js"></script></body>')
    return html
