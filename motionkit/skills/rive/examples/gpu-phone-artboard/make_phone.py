# phone.glb: mesh 0 = rounded slab body (pos, normal); mesh 1 = screen quad (pos, normal, uv)
import json, struct, numpy as np
W,H,D,R = 0.78, 1.6, 0.09, 0.14   # half width, half height, half depth, corner radius
SEG=10; RING=8                       # corner segments, edge-round rings
# outline of a rounded rect (CCW from +z)
outline=[]
for cx,cy,a0 in [(W-R,H-R,0),(-(W-R),H-R,90),(-(W-R),-(H-R),180),(W-R,-(H-R),270)]:
    for s in range(SEG+1):
        a=np.radians(a0+90*s/SEG); outline.append((cx+R*np.cos(a),cy+R*np.sin(a),np.cos(a),np.sin(a)))
pos=[];nrm=[];idx=[]
# rounded edge: sweep a half circle of radius D around the outline (pillowy sides)
N=len(outline)
for r in range(RING+1):
    t=np.pi*r/RING - np.pi/2          # -90..90 deg, back to front
    for (x,y,nx,ny) in outline:
        pos.append([x+nx*D*np.cos(t)*0.6, y+ny*D*np.cos(t)*0.6, D*np.sin(t)])
        n=np.array([nx*np.cos(t),ny*np.cos(t),np.sin(t)]); nrm.append(n/np.linalg.norm(n))
for r in range(RING):
    for i in range(N):
        a=r*N+i; b=r*N+(i+1)%N; c=a+N; d=b+N
        idx+=[a,b,d,a,d,c]
# front and back caps (fan from centre)
for z,nz in [(D,1),(-D,-1)]:
    c0=len(pos); pos.append([0,0,z]); nrm.append([0,0,nz])
    ring0=len(pos)
    for (x,y,nx,ny) in outline: pos.append([x+nx*D*0.6*0,y+ny*0,z]); nrm.append([0,0,nz])
    for i in range(N):
        a=ring0+i; b=ring0+(i+1)%N
        idx+= [c0,a,b] if nz>0 else [c0,b,a]
pos=np.array(pos,np.float32); nrm=np.array(nrm,np.float32); idx=np.array(idx,np.uint16)
# screen quad just in front of the face, 9:19.5-ish inset
sw,sh,z=W-0.07,H-0.07,D+0.002
spos=np.array([[-sw,-sh,z],[sw,-sh,z],[sw,sh,z],[-sw,sh,z]],np.float32)
snrm=np.array([[0,0,1]]*4,np.float32)
suv=np.array([[0,1],[1,1],[1,0],[0,0]],np.float32)
sidx=np.array([0,1,2,0,2,3],np.uint16)
chunks=[pos,nrm,idx,spos,snrm,suv,sidx]
bin_=b'';views=[]
for c in chunks:
    while len(bin_)%4: bin_+=b'\0'
    views.append({"buffer":0,"byteOffset":len(bin_),"byteLength":c.nbytes}); bin_+=c.tobytes()
while len(bin_)%4: bin_+=b'\0'
def acc(i,c,typ,ct): return {"bufferView":i,"componentType":ct,"count":len(c),"type":typ}
accs=[acc(0,pos,"VEC3",5126),acc(1,nrm,"VEC3",5126),acc(2,idx,"SCALAR",5123),acc(3,spos,"VEC3",5126),acc(4,snrm,"VEC3",5126),acc(5,suv,"VEC2",5126),acc(6,sidx,"SCALAR",5123)]
gl={"asset":{"version":"2.0"},"scene":0,"scenes":[{"nodes":[0,1]}],"nodes":[{"mesh":0,"name":"Body"},{"mesh":1,"name":"Screen"}],
 "meshes":[{"name":"Body","primitives":[{"attributes":{"POSITION":0,"NORMAL":1},"indices":2}]},
           {"name":"Screen","primitives":[{"attributes":{"POSITION":3,"NORMAL":4,"TEXCOORD_0":5},"indices":6}]}],
 "buffers":[{"byteLength":len(bin_)}],"bufferViews":views,"accessors":accs}
js=json.dumps(gl,separators=(',',':')).encode()
while len(js)%4: js+=b' '
glb=struct.pack('<III',0x46546C67,2,12+8+len(js)+8+len(bin_))+struct.pack('<II',len(js),0x4E4F534A)+js+struct.pack('<II',len(bin_),0x004E4942)+bin_
open('phone.glb','wb').write(glb); print(len(pos),'verts',len(glb),'bytes')

# The proof embeds Montserrat for its labels: copy it from the CLI's own samples if missing.
import glob, os, shutil
if not os.path.exists('Montserrat.ttf'):
    found = glob.glob(os.path.expanduser('~/.rive/versions/*/samples/rml_triangle/Montserrat.ttf'))
    if found:
        shutil.copy(found[0], 'Montserrat.ttf')
    else:
        print('Copy any .ttf here as Montserrat.ttf (the scene references it).')
