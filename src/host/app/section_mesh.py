"""Display-only ray extrusion. Original XYZ and triangle selection are immutable."""
import hashlib,json
from pathlib import Path
import numpy as np
N=512
def shell(folder,thickness):
    thickness=float(thickness)
    if not np.isfinite(thickness) or not 1<=thickness<=100:raise ValueError('假设厚度需在 1–100 mm')
    with np.load(Path(folder)/'geometry.npz',allow_pickle=False) as z:
        xyz=np.asarray(z['xyz_mm'],dtype='<f4').reshape(-1,3);faces=np.asarray(z['faces'],dtype='<u4')
    if not len(faces) or len(faces)>240000:raise ValueError('无有效表面或模型过大')
    used,inverse=np.unique(faces,return_inverse=True);front=xyz[used].copy();f=inverse.reshape(-1,3)
    if not np.isfinite(front).all() or (front[:,2]<=0).any():raise ValueError('模型坐标无效')
    edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
    _,idx,count=np.unique(np.sort(edges,axis=1),axis=0,return_index=True,return_counts=True)
    if (count>2).any():raise ValueError('模型存在非流形边，无法可靠封盖')
    boundary=edges[idx[count==1]]
    # Dropped depth-discontinuity faces can leave disconnected fans touching at
    # one vertex. Split only that topology; every duplicated XYZ stays exact.
    bv,degree=np.unique(boundary,return_counts=True);split_count=0;front_list=list(front)
    for vertex in bv[degree>2]:
        incident=np.where((f==vertex).any(axis=1))[0];groups=[];remaining=set(map(int,incident));neighbors={}
        for face in incident:
            for other in f[face]:
                if other!=vertex:neighbors.setdefault(int(other),[]).append(int(face))
        adjacency={int(face):set() for face in incident}
        for faces_here in neighbors.values():
            for face in faces_here:adjacency[face].update(faces_here)
        while remaining:
            todo=[remaining.pop()];group=[]
            while todo:
                face=todo.pop();group.append(face);next_faces=adjacency[face]&remaining;remaining-=next_faces;todo.extend(next_faces)
            groups.append(group)
        for group in groups[1:]:
            new=len(front_list);front_list.append(front[int(vertex)].copy());split_count+=1
            rows=np.array(group);values=f[rows].copy();values[values==vertex]=new;f[rows]=values
    front=np.asarray(front_list,dtype='<f4')
    back=(front.astype(np.float64)*(1+thickness/front[:,2].astype(np.float64))[:,None]).astype('<f4')
    edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
    _,idx,count=np.unique(np.sort(edges,axis=1),axis=0,return_index=True,return_counts=True)
    boundary=edges[idx[count==1]];n=len(front);a,b=boundary.T
    walls=np.concatenate([np.stack([a,b,b+n],1),np.stack([a,b+n,a+n],1)])
    extra=np.concatenate([f[:,::-1]+n,walls]);vertices=np.concatenate([front,back])
    allfaces=np.concatenate([f,extra]);tri=np.ascontiguousarray(vertices[allfaces],dtype='<f4')
    if len(tri)>500000:raise ValueError('闭合显示网格超过 PL 容量')
    # Independent edge closure check on the actual expanded shell.
    e=np.concatenate([allfaces[:,[0,1]],allfaces[:,[1,2]],allfaces[:,[2,0]]])
    _,counts=np.unique(np.sort(e,axis=1),axis=0,return_counts=True)
    if not (counts==2).all():raise ValueError('显示网格未闭合')
    lo=vertices.min(0).astype(float);hi=vertices.max(0).astype(float)
    meta=dict(mesh_sha256=hashlib.sha256(tri.tobytes()).hexdigest(),triangles=len(tri),original_triangles=len(f),boundary_edges=len(boundary),split_vertices=split_count,thickness_mm=thickness,
              closure='display_only_ray_extrusion',internal_anatomy_measured=False,bounds_mm=[lo.tolist(),hi.tolist()],center_mm=((lo+hi)/2).tolist(),focus_mm=np.median(front,axis=0).astype(float).tolist(),radius_mm=float(np.linalg.norm(hi-lo)/2),mask_size=N)
    return tri,np.ascontiguousarray(vertices[extra]/1000,dtype='<f4'),meta
def plane(meta,normal,position,flip=False):
    n=np.asarray(normal,dtype=float)
    if n.shape!=(3,) or not np.isfinite(n).all() or np.linalg.norm(n)<.5:raise ValueError('Invalid plane normal')
    n/=np.linalg.norm(n);position=float(position)
    if not np.isfinite(position) or not 0<=position<=100:raise ValueError('Invalid plane position')
    lo,hi=np.array(meta['bounds_mm']);corners=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]);dist=corners@n
    offset=float(dist.min()+(dist.max()-dist.min())*position/100);d=-offset
    axis=np.eye(3)[np.argmin(abs(n))];u=np.cross(n,axis);u/=np.linalg.norm(u);v=np.cross(n,u)
    uv=corners@np.stack([u,v],axis=1);span=max(1,float(np.ptp(uv,axis=0).max())*1.02);uvlo=(uv.min(0)+uv.max(0))/2-span/2
    p=np.zeros(16,dtype='<f4');p[:4]=[*n,d];p[4:7]=u;p[7:10]=v;p[10:12]=uvlo;p[12]=N/span
    return p,render_geometry(p,position,flip)
def render_geometry(params,position,flip):
    p=np.asarray(params,dtype='<f4');normal=p[:3].astype(float);uu=p[4:7].astype(float);vv=p[7:10].astype(float)
    # Render with the exact float32 plane/projection used by PL, in metres.
    origin=-float(p[3])*normal/(normal@normal)
    corners3=np.array([origin+uu*x+vv*y for x,y in [(p[10],p[11]),(p[10]+N/p[12],p[11]),(p[10]+N/p[12],p[11]+N/p[12]),(p[10],p[11]+N/p[12])]])/1000
    info=dict(plane_m=(p[:4]*np.array([1,1,1,.001],dtype=np.float32)).tolist(),corners_m=corners3.tolist(),pixel_mm=float(1/p[12]),position=position,flip=bool(flip))
    return info
