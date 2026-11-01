import sys,json,subprocess,numpy as np
from faster_whisper import WhisperModel
raw=subprocess.run(["ffmpeg","-v","error","-i",sys.argv[1],"-f","f32le","-ac","1","-ar","16000","-"],capture_output=True).stdout
a=np.frombuffer(raw,np.float32)
m=WhisperModel("small",compute_type="int8")
segs,_=m.transcribe(a,language="ar",word_timestamps=True)
W=[]
for s in segs:
    print(f"{s.start:5.1f}-{s.end:5.1f} {s.text}")
    W+=[(w.start,w.end,w.word) for w in s.words]
json.dump(W,open(sys.argv[2],"w"),ensure_ascii=False)
