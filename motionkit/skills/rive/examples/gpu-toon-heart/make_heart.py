# Writes heart.glb: a smooth 3D heart (implicit surface, star-shaped from the origin)
import json, struct, numpy as np
def F(x,y,z):  # Taubin heart, z up
    return (x*x + 2.25*y*y + z*z - 1)**3 - x*x*z**3 - 0.1125*y*y*z**3
def grad(p,e=1e-4):
    x,y,z=p
    return np.array([(F(x+e,y,z)-F(x-e,y,z)),(F(x,y+e,z)-F(x,y-e,z)),(F(x,y,z+e)-F(x,y,z-e))])/(2*e)
NU,NV=96,64
pos=[];nrm=[]
c=np.array([0,0,-0.05])
for j in range(NV+1):
    th=np.pi*j/NV
    for i in range(NU+1):
        ph=2*np.pi*i/NU
        d=np.array([np.sin(th)*np.cos(ph),np.sin(th)*np.sin(ph),np.cos(th)])
        lo,hi=0.0,2.0
        for _ in range(50):
            m=(lo+hi)/2
            if F(*(c+d*m))<0: lo=m
            else: hi=m
        p=c+d*lo; g=grad(p); g=g/np.linalg.norm(g)
        # glTF is y-up: map heart z-up -> y-up, heart y (depth) -> z
        pos.append([p[0],p[2],p[1]]); nrm.append([g[0],g[2],g[1]])
idx=[]
for j in range(NV):
    for i in range(NU):
        a=j*(NU+1)+i; b=a+NU+1
        idx += [a,b,a+1, a+1,b,b+1]
pos=np.array(pos,np.float32); nrm=np.array(nrm,np.float32); idx=np.array(idx,np.uint16)
# winding: make triangles CCW seen from outside
p0,p1,p2=pos[idx[0::3]],pos[idx[1::3]],pos[idx[2::3]]
fn=np.cross(p1-p0,p2-p0); out=(fn*(p0+p1+p2)).sum(1)
if (out<0).sum()>(out>0).sum():
    t=idx.reshape(-1,3); t[:,[1,2]]=t[:,[2,1]]; idx=t.reshape(-1)
bin_=pos.tobytes()+nrm.tobytes()+idx.tobytes()
while len(bin_)%4: bin_+=b'\0'
n=len(pos)
gl={"asset":{"version":"2.0"},"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0,"name":"Heart"}],
 "meshes":[{"primitives":[{"attributes":{"POSITION":0,"NORMAL":1},"indices":2}]}],
 "buffers":[{"byteLength":len(bin_)}],
 "bufferViews":[{"buffer":0,"byteOffset":0,"byteLength":n*12},{"buffer":0,"byteOffset":n*12,"byteLength":n*12},{"buffer":0,"byteOffset":n*24,"byteLength":idx.nbytes}],
 "accessors":[{"bufferView":0,"componentType":5126,"count":n,"type":"VEC3","min":pos.min(0).tolist(),"max":pos.max(0).tolist()},
  {"bufferView":1,"componentType":5126,"count":n,"type":"VEC3"},{"bufferView":2,"componentType":5123,"count":len(idx),"type":"SCALAR"}]}
js=json.dumps(gl,separators=(',',':')).encode()
while len(js)%4: js+=b' '
glb=struct.pack('<III',0x46546C67,2,12+8+len(js)+8+len(bin_))+struct.pack('<II',len(js),0x4E4F534A)+js+struct.pack('<II',len(bin_),0x004E4942)+bin_
open('heart.glb','wb').write(glb); print(n,'verts',len(idx)//3,'tris',len(glb),'bytes')
