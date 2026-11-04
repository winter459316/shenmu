/* Display-only local repair and ray-extruded backing; input XYZ stays immutable. */
function buildDisplayCompletion(input,source,width,height){
  const n=input.length/3,patches=[],present=new Uint8Array(width*height*2),usable=new Uint8Array(n);
  const triangleKey=(a,b,c)=>{const v=Math.min(a,b,c);return (a+b+c===3*v+width+1)?2*v:(a+b+c===3*v+2*width-1)?2*(v-1)+1:-1;};
  for(let i=0;i<source.length;i+=3){const k=triangleKey(source[i],source[i+1],source[i+2]);if(k>=0&&k<present.length)present[k]=1;usable[source[i]]=usable[source[i+1]]=usable[source[i+2]]=1;}
  function acceptable(a,b,c){
    const ids=[a,b,c];if(ids.some(i=>!usable[i]))return false;const zs=ids.map(i=>input[3*i+2]);if(zs.some(z=>!Number.isFinite(z)||z<=0))return false;
    const near=Math.min(...zs);if(Math.max(...zs)-near>Math.max(.035,.10*near))return false;
    const lengths=[];for(let j=0;j<3;j++){const u=3*ids[j],v=3*ids[(j+1)%3];lengths.push(Math.hypot(input[u]-input[v],input[u+1]-input[v+1],input[u+2]-input[v+2]));}
    return Math.max(...lengths)<=Math.max(.04,.12*near)&&Math.max(...lengths)<=12*Math.max(1.e-7,Math.min(...lengths));
  }
  for(let y=0;y<height-1;y++)for(let x=0;x<width-1;x++){
    const v=y*width+x;for(const [slot,a,b,c] of [[2*v,v,v+width,v+1],[2*v+1,v+1,v+width,v+width+1]])if(!present[slot]&&acceptable(a,b,c))patches.push(a,b,c);
  }
  const front=Array.from(source);front.push(...patches);
  function boundaries(faces){
    const edges=new Map();
    for(let i=0;i<faces.length;i+=3)for(let j=0;j<3;j++){
      const a=faces[i+j],b=faces[i+(j+1)%3],key=Math.min(a,b)*n+Math.max(a,b),edge=edges.get(key);
      if(edge)edge.count++;else edges.set(key,{a,b,count:1,face:i/3});
    }
    return [...edges.values()].filter(e=>e.count===1);
  }
  const boundary=boundaries(front),outgoing=new Map();for(const e of boundary){if(outgoing.has(e.a))outgoing.set(e.a,null);else outgoing.set(e.a,e.b);}
  const visited=new Set();let filledHoles=0;
  const xy=i=>[i%width,Math.floor(i/width)];
  const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  for(const seed of outgoing.keys()){
    if(visited.has(seed))continue;const loop=[];let v=seed;
    while(v!==null&&v!==undefined&&!visited.has(v)&&loop.length<=512){visited.add(v);loop.push(v);v=outgoing.get(v);}
    if(v!==seed||loop.length<3||loop.length>512)continue;
    let area=0;for(let i=0;i<loop.length;i++){const a=xy(loop[i]),b=xy(loop[(i+1)%loop.length]);area+=a[0]*b[1]-a[1]*b[0];}
    // Positive winding is a hole, negative winding is an external object boundary.
    if(area<=0||area>2*width*height*.08)continue;
    const values=loop.map(i=>[input[3*i],input[3*i+1],input[3*i+2]]),z=values.map(p=>p[2]).sort((a,b)=>a-b),mid=z[z.length>>1];
    const extent=[0,1,2].map(c=>Math.max(...values.map(p=>p[c]))-Math.min(...values.map(p=>p[c])));
    if(z[z.length-1]-z[0]>Math.max(.08,.35*mid)||Math.hypot(...extent)>Math.min(.30,Math.max(.08,.55*mid)))continue;
    const remaining=loop.slice(),fill=[];let failed=false;
    while(remaining.length>3){
      let clipped=false;
      for(let j=0;j<remaining.length;j++){
        const a=remaining[(j+remaining.length-1)%remaining.length],b=remaining[j],c=remaining[(j+1)%remaining.length],pa=xy(a),pb=xy(b),pc=xy(c);
        if(cross(pa,pb,pc)<=1.e-8)continue;
        const contains=remaining.some(k=>k!==a&&k!==b&&k!==c&&cross(pa,pb,xy(k))>=0&&cross(pb,pc,xy(k))>=0&&cross(pc,pa,xy(k))>=0);
        if(contains)continue;
        fill.push(c,b,a);remaining.splice(j,1);clipped=true;break;
      }
      if(!clipped){failed=true;break;}
    }
    if(!failed&&remaining.length===3){fill.push(remaining[2],remaining[1],remaining[0]);front.push(...fill);patches.push(...fill);filledHoles++;}
  }
  const edges=boundaries(front),degree=new Map();for(const {a,b} of edges){degree.set(a,(degree.get(a)||0)+1);degree.set(b,(degree.get(b)||0)+1);}
  const incident=new Map([...degree].filter(([v,d])=>d>2).map(([v])=>[v,[]]));
  for(let i=0;i<front.length;i+=3)for(let j=0;j<3;j++)if(incident.has(front[i+j]))incident.get(front[i+j]).push(i/3);
  const backMaps=new Map(),duplicates=[];
  for(const [vertex,faces] of incident){
    const adjacent=new Map(faces.map(f=>[f,new Set()])),byNeighbor=new Map();
    for(const face of faces)for(let j=0;j<3;j++){const other=front[face*3+j];if(other===vertex)continue;const prior=byNeighbor.get(other);if(prior!==undefined){adjacent.get(face).add(prior);adjacent.get(prior).add(face);}else byNeighbor.set(other,face);}
    const remaining=new Set(faces),mapping=new Map();let group=0;
    while(remaining.size){const seed=remaining.values().next().value;remaining.delete(seed);const todo=[seed],id=group++===0?vertex+n:2*n+duplicates.length;if(id>=2*n)duplicates.push(vertex);
      while(todo.length){const face=todo.pop();mapping.set(face,id);for(const next of adjacent.get(face))if(remaining.delete(next))todo.push(next);}
    }
    backMaps.set(vertex,mapping);
  }
  const back=(vertex,face)=>backMaps.get(vertex)?.get(face)??vertex+n;
  const positions=new Float32Array(input.length*2+duplicates.length*3);positions.set(input);
  for(let i=0;i<n;i++){
    const z=input[3*i+2],scale=Number.isFinite(z)&&z>0?1+Math.max(.01,Math.min(.035,z*.05))/z:1;
    for(let c=0;c<3;c++)positions[(i+n)*3+c]=input[i*3+c]*scale;
  }
  for(let i=0;i<duplicates.length;i++)for(let c=0;c<3;c++)positions[(2*n+i)*3+c]=positions[(duplicates[i]+n)*3+c];
  const extra=patches.slice();
  for(let i=0;i<front.length;i+=3)extra.push(back(front[i+2],i/3),back(front[i+1],i/3),back(front[i],i/3));
  for(const {a,b,face} of edges){const aa=back(a,face),bb=back(b,face);extra.push(b,a,aa,b,aa,bb);}
  return {positions,indices:new Uint32Array(extra),front:new Uint32Array(front),stats:{splitBackVertices:duplicates.length,originalFaces:source.length/3,patchFaces:patches.length/3,filledHoles,boundaryEdges:edges.length,backFaces:front.length/3,wallFaces:edges.length*2}};
}
/* Caps follow the actual closed PL section contour; never extend a convex hull. */
function solidSectionMask(source,width=512,height=512){
  if(source.length!==width*height)throw Error('Invalid section mask size');
  const output=source.slice(),seen=new Uint8Array(source.length),queue=new Int32Array(source.length);
  let head=0,tail=0,rawPixels=0,closedRegions=0;
  for(const value of source)if(value)rawPixels++;
  function add(i){if(!source[i]&&!seen[i]){seen[i]=1;queue[tail++]=i;}}
  for(let x=0;x<width;x++){add(x);add((height-1)*width+x);}
  for(let y=0;y<height;y++){add(y*width);add(y*width+width-1);}
  // Eight-connected exterior also preserves narrow and diagonal openings.
  while(head<tail){const i=queue[head++],x=i%width,y=Math.floor(i/width);
    for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
      const nx=x+dx,ny=y+dy;if(nx>=0&&nx<width&&ny>=0&&ny<height)add(ny*width+nx);
    }
  }
  for(let seed=0;seed<source.length;seed++){
    if(source[seed]||seen[seed])continue;
    closedRegions++;head=0;tail=0;add(seed);
    while(head<tail){const i=queue[head++],x=i%width,y=Math.floor(i/width);output[i]=255;
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
        const nx=x+dx,ny=y+dy;if(nx>=0&&nx<width&&ny>=0&&ny<height)add(ny*width+nx);
      }
    }
  }
  let pixels=0;for(const value of output)if(value)pixels++;
  return {bytes:output,closedRegions,rawPixels,pixels};
}
(()=>{
  const cut=window.sectionView={enabled:false,plane:[1,0,0,0],flip:false,revision:0,ghost:true,opacity:.18,cap:true,guide:false};
  let extra=null,frontGhost=null,planeMesh=null,meta=null,maskReady=false,cutDrag=null,completionMesh=null,completionData=null,completionEnabled=true;
  const frag=`#version 300 es
precision highp float;in vec3 vPosition;in vec3 vNormal;in vec2 vUv;in vec3 vModel;
uniform vec4 plane;uniform bool reverseSide;uniform int material;uniform sampler2D cap;uniform float ghostAlpha;
out vec4 outColor;
void main(){
 if(material==0){float d=dot(vec4(vModel,1.),plane);if(reverseSide?-d>0.:d>0.)discard;
 vec3 norm=normalize(cross(dFdx(vPosition),dFdy(vPosition)));float light=.5+.5*abs(dot(norm,normalize(vec3(.3,.6,1.))));outColor=vec4(vec3(.46,.34,.29)*light,1.);}
 else if(material==3){float d=dot(vec4(vModel,1.),plane)*(reverseSide?-1.:1.);if(d<=0.)discard;
 vec3 raw=cross(dFdx(vPosition),dFdy(vPosition));vec3 norm=length(raw)>1.e-10?normalize(raw):vec3(0.,0.,1.);if(norm.z<0.)norm=-norm;
 vec3 key=normalize(vec3(.3,.6,1.)),fill=normalize(vec3(-key.x,-.15,.8));float diffuse=max(dot(norm,key),0.),bounce=max(dot(norm,fill),0.);
 float highlight=pow(max(dot(norm,normalize(key+vec3(0.,0.,1.))),0.),35.);vec3 gray=vec3(.68,.75,.83)*(.24+.60*diffuse+.15*bounce)+vec3(.10*highlight);outColor=vec4(gray,ghostAlpha);}
 else if(material==4){vec3 raw=cross(dFdx(vPosition),dFdy(vPosition));vec3 norm=length(raw)>1.e-10?normalize(raw):vec3(0.,0.,1.);if(norm.z<0.)norm=-norm;float light=.30+.55*max(dot(norm,normalize(vec3(.3,.6,1.))),0.)+.15*max(dot(norm,normalize(vec3(-.3,-.15,.8))),0.);outColor=vec4(vec3(.68,.75,.83)*light,1.);}
 else if(material==1){if(texture(cap,vUv).r<.5)discard;outColor=vec4(.97,.57,.29,1.);}
 else {float edge=min(min(vUv.x,1.-vUv.x),min(vUv.y,1.-vUv.y));outColor=vec4(.25,.83,.83,edge<.006?.8:.10);}
}`;
  const cp=gl.createProgram();gl.attachShader(cp,compile(gl.VERTEX_SHADER,vertex));gl.attachShader(cp,compile(gl.FRAGMENT_SHADER,frag));gl.linkProgram(cp);
  if(!gl.getProgramParameter(cp,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(cp));
  const cu={};for(const k of ['rotation','center','pan','extent','clipDepth','pointSize','cameraProjection','cameraIntrinsics','gridSize','imageScale','plane','reverseSide','material','cap','ghostAlpha'])cu[k]=gl.getUniformLocation(cp,k);
  const texture=gl.createTexture();
  function mesh(vertices,uv,indices){
    const vao=gl.createVertexArray(),buffers=[];gl.bindVertexArray(vao);
    for(const [name,arr,size] of [['position',vertices,3],['imageUv',uv||new Float32Array(vertices.length/3*2),2]]){
      const loc=gl.getAttribLocation(cp,name);if(loc<0)continue;
      const b=gl.createBuffer();buffers.push(b);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,arr,gl.STATIC_DRAW);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,0,0);
    }
    if(indices){const b=gl.createBuffer();buffers.push(b);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);}
    gl.bindVertexArray(null);return {vao,buffers,count:indices?indices.length:vertices.length/3,indexed:!!indices};
  }
  function drop(m){if(m){gl.deleteVertexArray(m.vao);for(const b of m.buffers)gl.deleteBuffer(b);}}
  const emit=data=>{if(parent!==window)parent.postMessage({type:'fast_section_viewer',...data},location.origin);};
  function disable(){cut.enabled=false;cut.revision++;maskReady=false;selection=-1;requestRender();}
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==parent||event.data?.type!=='fast_section_control')return;
    const m=event.data;
    if(m.action==='model'){
      disable();drop(extra);extra=mesh(new Float32Array(m.buffer));drop(frontGhost);frontGhost=mesh(denseXYZ,null,denseFaces);meta=m.meta;cut.center=meta.focus_mm.map(x=>x/1000);
      $('mode').value='mesh';$('color').value='rgb';selection=-1;requestRender();
    }else if(m.action==='result'){
      if(!meta||m.mesh_sha256!==meta.mesh_sha256)return;
      const geom=m.geometry,raw=atob(m.mask),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
      if(bytes.length!==512*512)return;
      const solid=solidSectionMask(bytes);
      document.body.dataset.sectionSolidCap=JSON.stringify({closedRegions:solid.closedRegions,rawPixels:solid.rawPixels,pixels:solid.pixels,policy:"actual_closed_contours"});
      gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,texture);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.R8,512,512,0,gl.RED,gl.UNSIGNED_BYTE,solid.bytes);
      for(const [p,v] of [[gl.TEXTURE_MIN_FILTER,gl.NEAREST],[gl.TEXTURE_MAG_FILTER,gl.NEAREST],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])gl.texParameteri(gl.TEXTURE_2D,p,v);
      gl.activeTexture(gl.TEXTURE0);
      const order=[0,1,2,0,2,3];drop(planeMesh);planeMesh=mesh(new Float32Array(order.flatMap(i=>geom.corners_m[i])),new Float32Array([0,0,1,0,1,1,0,0,1,1,0,1]));
      cut.plane=geom.plane_m;cut.flip=geom.flip;cut.enabled=true;cut.revision++;maskReady=true;selection=-1;
      document.body.dataset.sectionBackend=m.backend;document.body.dataset.sectionSequence=String(m.seq);document.body.dataset.sectionPixels=String(m.pixels);requestRender();emit({kind:'applied',seq:m.seq});
    }else if(m.action==='disable')disable();
    else if(m.action==='dragmode')cut.dragMode=!!m.enabled;
    else if(m.action==='completion'){completionEnabled=!!m.enabled;cut.revision++;requestRender();}
    else if(m.action==='appearance'){
      cut.ghost=!!m.ghost;cut.opacity=Math.max(.05,Math.min(.45,Number(m.opacity)||.18));cut.cap=m.cap!==false;cut.guide=!!m.guide;cut.revision++;
      document.body.dataset.sectionAppearance=JSON.stringify({ghost:cut.ghost,opacity:cut.opacity,cap:cut.cap,guide:cut.guide});requestRender();
    }
  });
  window.sectionKeep=i=>!cut.enabled||((xyz[3*i]*cut.plane[0]+xyz[3*i+1]*cut.plane[1]+xyz[3*i+2]*cut.plane[2]+cut.plane[3])*(cut.flip?-1:1)<=0);
  window.sectionRender=()=>{
    const completing=!cut.enabled&&completionEnabled&&$('mode').value!=='points';
    if(!cut.enabled&&!completing)return;
    if(cut.enabled&&(!extra||!planeMesh||!maskReady))return;
    if(completing&&!completionMesh){
      const start=performance.now();completionData=buildDisplayCompletion(denseXYZ,denseFaces,gridWidth,gridHeight);completionMesh=mesh(completionData.positions,null,completionData.indices);
      document.body.dataset.displayCompletion=JSON.stringify({...completionData.stats,buildMs:performance.now()-start});
    }
    gl.useProgram(cp);gl.uniformMatrix3fv(cu.rotation,false,rotation);gl.uniform3fv(cu.center,center);gl.uniform2fv(cu.pan,pan);gl.uniform2fv(cu.extent,extent);
    gl.uniform1f(cu.clipDepth,Math.max(5,baseExtent*30));gl.uniform1f(cu.pointSize,2);gl.uniform1i(cu.cameraProjection,usingCamera());gl.uniform4fv(cu.cameraIntrinsics,data.camera_intrinsics||[1,1,0,0]);gl.uniform2f(cu.gridSize,gridWidth,gridHeight);gl.uniform2fv(cu.imageScale,imageScale);
    if(completing){
      gl.uniform1i(cu.material,4);gl.bindVertexArray(completionMesh.vao);gl.drawElements(gl.TRIANGLES,completionMesh.count,gl.UNSIGNED_INT,0);
      gl.bindVertexArray(null);gl.activeTexture(gl.TEXTURE0);gl.useProgram(program);return;
    }
    gl.uniform4fv(cu.plane,cut.plane);gl.uniform1i(cu.reverseSide,cut.flip);
    gl.uniform1i(cu.material,0);gl.bindVertexArray(extra.vao);gl.drawArrays(gl.TRIANGLES,0,extra.count);
    gl.bindVertexArray(planeMesh.vao);gl.uniform1i(cu.material,1);gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,texture);gl.uniform1i(cu.cap,1);
    if(cut.cap){gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(-1,-1);gl.drawArrays(gl.TRIANGLES,0,6);gl.disable(gl.POLYGON_OFFSET_FILL);}
    gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
    if(cut.guide){gl.uniform1i(cu.material,2);gl.drawArrays(gl.TRIANGLES,0,6);}
    if(cut.ghost&&frontGhost){
      gl.uniform1i(cu.material,3);gl.uniform1f(cu.ghostAlpha,cut.opacity);
      gl.bindVertexArray(extra.vao);gl.drawArrays(gl.TRIANGLES,0,extra.count);
      gl.bindVertexArray(frontGhost.vao);gl.drawElements(gl.TRIANGLES,frontGhost.count,gl.UNSIGNED_INT,0);
    }
    gl.depthMask(true);gl.disable(gl.BLEND);
    gl.bindVertexArray(null);gl.activeTexture(gl.TEXTURE0);gl.useProgram(program);
  };
  // Capture phase prevents the ordinary orbit/pan handler from also moving.
  canvas.addEventListener('pointerdown',e=>{if(!cut.enabled||(!e.shiftKey&&!cut.dragMode)||e.button!==0)return;e.stopImmediatePropagation();e.preventDefault();cutDrag={id:e.pointerId,x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);},true);
  canvas.addEventListener('pointermove',e=>{if(!cutDrag)return;e.stopImmediatePropagation();const dx=e.clientX-cutDrag.x,dy=e.clientY-cutDrag.y;cutDrag.x=e.clientX;cutDrag.y=e.clientY;
    const n=[cut.plane[0],-cut.plane[1],-cut.plane[2]],sx=rotation[0]*n[0]+rotation[3]*n[1]+rotation[6]*n[2],sy=-(rotation[1]*n[0]+rotation[4]*n[1]+rotation[7]*n[2]),len=Math.hypot(sx,sy);
    emit({kind:'drag',delta:(len>.1?(dx*sx+dy*sy)/len:-dy)/canvas.clientHeight*100});},true);
  for(const name of ['pointerup','pointercancel'])canvas.addEventListener(name,e=>{if(!cutDrag)return;e.stopImmediatePropagation();cutDrag=null;emit({kind:'drag_end'});},true);
  requestRender();
})();
