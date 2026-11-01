import json,subprocess,sys,os
ref=sys.argv[1]; os.chdir(f'/home/claude/work/{ref}')
u=json.load(open('urls.json'))['urls']
for i,x in enumerate(u,1):
    if not x or 'douyin' in x or 'youtube' in x or os.path.exists(f'src/v{i}.mp4'): continue
    if x.endswith('.mp4') and 'tiktok' not in x:
        r=subprocess.run(['curl','-sSL','-m','120','-o',f'src/v{i}.mp4',x]); 
    else:
        r=subprocess.run(['yt-dlp','-q','--impersonate','chrome','-o',f'src/v{i}.mp4',x],capture_output=True,text=True)
    ok=os.path.exists(f'src/v{i}.mp4')
    print(ref,i,'OK' if ok else 'FAIL',x[:70],(r.stderr or '')[-100:] if not ok else '')
