import json,base64,sys,urllib.request,os
key=open(os.environ.get('GK','/home/claude/.gk')).read().strip()
text=open(sys.argv[1]).read().strip().replace('\n',' ')
instr="صوت مغربي طبيعي متحمس كيدير إعلان بيع، كيهضر بحال واحد كيهضر مع صاحبتو، تبع التشكيل بالضبط، ما تنطقش التعليمات:"
body={"contents":[{"parts":[{"text":text}]}],
 "generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":sys.argv[3] if len(sys.argv)>3 else "Laomedeia"}}}}}
req=urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key})
r=json.load(urllib.request.urlopen(req,timeout=180))
p=r["candidates"][0]["content"]["parts"][0]["inlineData"]
open(sys.argv[2]+".pcm","wb").write(base64.b64decode(p["data"]));print(p["mimeType"])
