# make <REF>_cover.jpg for every finished video; detect its frame style by comparing border pixels
import os,subprocess,glob,numpy as np,sys
from PIL import Image
W='/home/claude/work'; FR={n:np.asarray(Image.open(f'/home/claude/kit/frames/{n}/frame.png').convert('RGBA').resize((270,480))).astype(float) for n in range(1,11)}
refs=sys.argv[1:] or sorted(os.listdir(W))
for r in refs:
    vs=[v for v in glob.glob(f'{W}/{r}/{r}_*.mp4')]
    if not vs or os.path.exists(f'{W}/{r}/{r}_cover.jpg'): continue
    v=vs[0]; t=f'{W}/{r}/_f.png'
    subprocess.run(['ffmpeg','-v','error','-y','-ss','3','-i',v,'-frames:v','1','-vf','scale=270:480',t])
    a=np.asarray(Image.open(t).convert('RGB')).astype(float)
    best=min(FR,key=lambda n:(np.abs(a-FR[n][...,:3])*(FR[n][...,3:]/255)).sum()/(FR[n][...,3].sum()+1))
    os.remove(t)
    name=os.path.basename(v)[len(r)+1:-4].replace('_',' ')
    subprocess.run(['python3','/home/claude/kit/cover.py',v,name,str(best),f'{W}/{r}/{r}_cover.jpg'])
    print(r,best,flush=True)
