import base64, glob, os, shutil, subprocess, tempfile, time
from pathlib import Path
import runpod

MUSETALK_DIR=Path(os.getenv('MUSETALK_DIR','/workspace/MuseTalk'))
WORK_DIR=Path(os.getenv('FACETALK_WORK_DIR','/workspace/facetalk_jobs')); WORK_DIR.mkdir(parents=True,exist_ok=True)

def run(cmd,cwd,timeout=1200):
    p=subprocess.run(cmd,cwd=str(cwd),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError(p.stdout[-5000:])

def newest(folder,since):
    fs=[Path(p) for p in glob.glob(str(folder/'**'/'*.mp4'),recursive=True)]
    fs=[p for p in fs if p.exists() and p.stat().st_mtime>=since-2]
    return max(fs,key=lambda p:p.stat().st_mtime) if fs else None

def handler(job):
    i=job.get('input') or {}
    if i.get('action')=='health':
        return {'ok':True,'musetalk_installed':(MUSETALK_DIR/'scripts/inference.py').exists(),'musetalk_models':(MUSETALK_DIR/'models/musetalkV15/unet.pth').exists()}
    image_b64=i.get('image_b64'); audio_b64=i.get('audio_b64')
    if not image_b64 or not audio_b64: return {'error':'image_b64 and audio_b64 are required'}
    jobdir=Path(tempfile.mkdtemp(prefix='facetalk_',dir=str(WORK_DIR)))
    try:
        image=jobdir/'face.jpg'; audio=jobdir/'speech.mp3'
        image.write_bytes(base64.b64decode(image_b64)); audio.write_bytes(base64.b64decode(audio_b64))
        result=jobdir/'results'; result.mkdir()
        cfg=jobdir/'musetalk.yaml'; cfg.write_text(f'task_0:\n  video_path: "{image.as_posix()}"\n  audio_path: "{audio.as_posix()}"\n',encoding='utf-8')
        started=time.time()
        run(['python','-m','scripts.inference','--inference_config',str(cfg),'--result_dir',str(result),'--unet_model_path','models/musetalkV15/unet.pth','--unet_config','models/musetalkV15/musetalk.json','--version','v15'],MUSETALK_DIR,int(os.getenv('MUSETALK_TIMEOUT','1200')))
        out=newest(result,started) or newest(MUSETALK_DIR/'results',started)
        if not out: raise RuntimeError('MuseTalk finished but no mp4 was found')
        data=out.read_bytes()
        return {'ok':True,'video_b64':base64.b64encode(data).decode('ascii'),'bytes':len(data)}
    finally:
        shutil.rmtree(jobdir,ignore_errors=True)

runpod.serverless.start({'handler':handler})
