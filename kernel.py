"""KAGGLE JOB (sent automatically by cloud_daily.py): ComfyUI + Wan 2.2 makes one clip per picture in job.json, on BOTH GPUs."""
import os, sys, glob, json, shutil, site, subprocess, time
T0 = time.time()
def say(x): print(f"[{time.time() - T0:6.0f} s] {x}", flush=True)
for d in set(site.getsitepackages() + [site.getusersitepackages()] + sys.path):
    for p in glob.glob(str(d) + '/torchao*'): shutil.rmtree(p, ignore_errors=True)
C = '/tmp/ComfyUI'
if not os.path.exists(C): subprocess.run(['git', 'clone', '-q', '--depth', '1', 'https://github.com/comfyanonymous/ComfyUI.git', C], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-r', f'{C}/requirements.txt'])
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'huggingface_hub', 'imageio-ffmpeg', 'requests'])
say('ComfyUI installed')
jobs = glob.glob('/kaggle/input/**/job.json', recursive=True)
if not jobs: sys.exit('job.json not found in the input dataset')
JOB = json.load(open(jobs[0])); JDIR = os.path.dirname(jobs[0])
WF = json.loads(r'''{"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}}, "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}}, "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}}, "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}}, "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "Static locked-off camera, the camera does not move. The people and animals stay perfectly still, their faces, bodies and clothes do not change. Only nature moves gently: leaves and grass sway softly in a light wind, clouds drift slowly, a little dust floats in the warm light. Calm 2D illustration."}}, "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "new people appearing, new animals appearing, objects turning into creatures, transformation, morphing, extra limbs, distorted face, changing clothes, camera shake, fast zoom, text, watermark, flicker, blurry"}}, "7": {"class_type": "LoadImage", "inputs": {"image": "example.png"}}, "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": 832, "height": 480, "length": 73, "batch_size": 1, "start_image": ["7", 0]}}, "9": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "seed": 11, "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["8", 0], "denoise": 1.0}}, "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}}, "11": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["10", 0], "filename_prefix": "wan_clip", "fps": 24.0, "lossless": false, "quality": 90, "method": "default"}}}''')
WF['8']['inputs']['length'] = int(round(JOB.get('seconds', 5) * 24 / 4)) * 4 + 1
from huggingface_hub import hf_hub_download
M = f'{C}/models'
KNOWN = {  # file name -> (huggingface repo, path in repo, ComfyUI folder)
 'svd_xt.safetensors': ('stabilityai/stable-video-diffusion-img2vid-xt', 'svd_xt.safetensors', 'checkpoints'),
 'svd_xt_1_1.safetensors': ('stabilityai/stable-video-diffusion-img2vid-xt-1-1', 'svd_xt_1_1.safetensors', 'checkpoints'),
 'ltx-video-2b-v0.9.5.safetensors': ('Lightricks/LTX-Video', 'ltx-video-2b-v0.9.5.safetensors', 'checkpoints'),
 't5xxl_fp8_e4m3fn.safetensors': ('comfyanonymous/flux_text_encoders', 't5xxl_fp8_e4m3fn.safetensors', 'text_encoders'),
 't5xxl_fp16.safetensors': ('comfyanonymous/flux_text_encoders', 't5xxl_fp16.safetensors', 'text_encoders'),
 'wan2.2_ti2v_5B_fp16.safetensors': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors', 'diffusion_models'),
 'umt5_xxl_fp8_e4m3fn_scaled.safetensors': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'text_encoders'),
 'wan2.2_vae.safetensors': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/vae/wan2.2_vae.safetensors', 'vae'),
}
for name in ('wan2.2_ti2v_5B_fp16.safetensors', 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'wan2.2_vae.safetensors'):
    repo, path, folder = KNOWN[name]; os.makedirs(f'{M}/{folder}', exist_ok=True)
    if not os.path.exists(f'{M}/{folder}/{name}'):
        f = hf_hub_download(repo, path, local_dir='/tmp/hf'); shutil.move(f, f'{M}/{folder}/{name}')
say('models ready')
RUNNER_TEXT = '"""Runs a ComfyUI workflow (API format) for every picture. Used by the Kaggle notebook; also testable with any ComfyUI URL."""\nimport os, sys, json, time, glob, shutil, subprocess, copy\nimport requests\nCOMFY = os.getenv("COMFY_DIR", "/tmp/ComfyUI"); URL = os.getenv("COMFY_URL", "http://127.0.0.1:8188")\nOUT = os.getenv("OUT_DIR", "/kaggle/working/outputs"); T0 = time.time()\ndef say(x): print(f"[{time.time() - T0:6.0f} s] {x}", flush=True)\n\n\ndef start_comfy():\n    if os.getenv("COMFY_ALREADY_RUNNING") == "1": return None\n    log = open("/kaggle/working/comfy_log.txt" if os.path.isdir("/kaggle/working") else "/tmp/comfy_log.txt", "w")\n    p = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch", "--preview-method", "none"],\n                         cwd=COMFY, stdout=log, stderr=subprocess.STDOUT)\n    say("starting ComfyUI ...")\n    for _ in range(240):\n        try:\n            requests.get(f"{URL}/system_stats", timeout=3); say("ComfyUI is ready"); return p\n        except Exception:\n            if p.poll() is not None: sys.exit("ComfyUI stopped while starting - see comfy_log.txt")\n            time.sleep(2)\n    sys.exit("ComfyUI did not start in 8 minutes - see comfy_log.txt")\n\n\ndef run_one(wf, label):\n    t = time.time()\n    r = requests.post(f"{URL}/prompt", json={"prompt": wf, "client_id": "kaggle"}, timeout=60)\n    if r.status_code != 200: say(f"  {label}: ComfyUI refused the workflow: {r.text[:800]}"); return []\n    pid = r.json()["prompt_id"]; say(f"  {label}: queued (job {pid[:8]})")\n    last = 0\n    while True:\n        time.sleep(5)\n        try: h = requests.get(f"{URL}/history/{pid}", timeout=30).json()\n        except Exception: say("  ComfyUI stopped answering (out of memory?) - see comfy_log.txt"); return []\n        if pid in h: break\n        if time.time() - last > 30: say(f"  {label}: working ... {time.time() - t:.0f} s"); last = time.time()\n    h = h[pid]; st = h.get("status", {})\n    if st.get("status_str") == "error":\n        msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]\n        say(f"  {label}: ERROR {json.dumps(msgs)[:800]}"); return []\n    files = []\n    for node_out in h.get("outputs", {}).values():\n        for key in ("images", "gifs", "videos", "video"):\n            for f in node_out.get(key, []) or []:\n                if isinstance(f, dict) and f.get("filename"):\n                    src = os.path.join(COMFY, f.get("type", "output"), f.get("subfolder", ""), f["filename"])\n                    if os.path.exists(src): files.append(src)\n    say(f"  {label}: done in {time.time() - t:.0f} s, {len(files)} output file(s)")\n    return files\n\n\ndef to_mp4(webp, fps=24):\n    """animated WEBP from ComfyUI -> MP4 next to it"""\n    try:\n        from PIL import Image, ImageSequence\n        import imageio_ffmpeg\n        im = Image.open(webp); frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]\n        if len(frames) < 2: return\n        w, h = frames[0].size; w, h = w - w % 2, h - h % 2\n        p = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "quiet", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",\n                              "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", webp[:-5] + ".mp4"], stdin=subprocess.PIPE)\n        for f in frames: p.stdin.write(f.crop((0, 0, w, h)).tobytes())\n        p.stdin.close(); p.wait(); say(f"  made {os.path.basename(webp)[:-5]}.mp4 ({len(frames)} frames)")\n    except Exception as e:\n        say(f"  (mp4 not made: {str(e)[:80]})")\n\n\ndef main():\n    S = json.load(open(os.getenv("SETTINGS", "/kaggle/working/settings.json")))\n    wf0 = json.load(open(S["workflow"]))\n    loaders = [k for k, n in wf0.items() if n.get("class_type") in ("LoadImage", "LoadImageMask", "VHS_LoadImagePath")]\n    texts = [k for k, n in wf0.items() if n.get("class_type") in ("CLIPTextEncode", "TextEncodeHunyuanVideo_ImageToVideo") or "prompt" in str(n.get("_meta", {}).get("title", "")).lower()]\n    say(f"workflow: {len(wf0)} nodes | picture inputs: {loaders or \'none\'} | text prompts: {texts or \'none\'}")\n    proc = start_comfy()\n    os.makedirs(OUT, exist_ok=True); os.makedirs(os.path.join(COMFY, "input"), exist_ok=True)\n    pics = S.get("pictures") or [None]\n    for i, pic in enumerate(pics, 1):\n        wf = copy.deepcopy(wf0); label = f"{i}/{len(pics)} {os.path.basename(pic) if pic else \'run\'}"\n        if pic:\n            name = f"in_{i:03d}_{os.path.basename(pic)}"; shutil.copy(pic, os.path.join(COMFY, "input", name))\n            for k in loaders: wf[k]["inputs"]["image"] = name\n        ptxt = (S.get("prompts") or [None] * len(pics))[i - 1] or S.get("prompt")\n        if ptxt and texts:\n            k = texts[0]\n            for field in ("text", "prompt", "positive_prompt"):\n                if field in wf[k]["inputs"] and isinstance(wf[k]["inputs"][field], str): wf[k]["inputs"][field] = ptxt; break\n            say(f"  {label}: prompt = {ptxt[:90]}...")\n        for f in run_one(wf, label):\n            base = os.path.splitext(os.path.basename(pic))[0] if pic else "run"\n            dst = os.path.join(OUT, f"{base}__{os.path.basename(f)}"); shutil.copy(f, dst)\n            if dst.lower().endswith(".webp"): to_mp4(dst)\n    shutil.make_archive(OUT, "zip", OUT)\n    say(f"ALL DONE -> {OUT}.zip  ({len(os.listdir(OUT))} files)")\n    if proc: proc.terminate()\n\n\nif __name__ == "__main__":\n    main()\n'
open('/kaggle/working/run_comfy.py', 'w').write(RUNNER_TEXT)
import torch, requests
pics = [os.path.join(JDIR, n) for n in JOB['pictures']]
gpus = max(1, min(2, torch.cuda.device_count())); say(f'GPUs: {gpus} | pictures: {len(pics)}')
if gpus >= 2: WF['1']['inputs']['weight_dtype'] = 'fp8_e4m3fn'      # two copies must fit in RAM -> lighter weights
json.dump(WF, open('/kaggle/working/workflow_api.json', 'w'))
servers, runs = [], []
for g in range(gpus):
    log = open(f'/kaggle/working/comfy_log_gpu{g}.txt', 'w')
    servers.append(subprocess.Popen([sys.executable, 'main.py', '--listen', '127.0.0.1', '--port', str(8188 + g), '--cuda-device', str(g),
                                     '--disable-auto-launch', '--preview-method', 'none'], cwd=C, stdout=log, stderr=subprocess.STDOUT))
for g in range(gpus):
    for _ in range(240):
        try: requests.get(f'http://127.0.0.1:{8188 + g}/system_stats', timeout=3); break
        except Exception: time.sleep(2)
    say(f'ComfyUI on GPU {g} ready')
for g in range(gpus):                                                # each GPU gets every second picture
    mine = pics[g::gpus]
    json.dump({'workflow': '/kaggle/working/workflow_api.json', 'pictures': mine, 'prompts': [JOB['prompts'].get(os.path.basename(n), '') for n in mine]},
              open(f'/kaggle/working/settings_gpu{g}.json', 'w'))
    env = dict(os.environ, OUT_DIR='/kaggle/working/clips', SETTINGS=f'/kaggle/working/settings_gpu{g}.json',
               COMFY_URL=f'http://127.0.0.1:{8188 + g}', COMFY_ALREADY_RUNNING='1', COMFY_DIR=C)
    runs.append(subprocess.Popen([sys.executable, '/kaggle/working/run_comfy.py'], cwd='/kaggle/working', env=env))
for r in runs: r.wait()
for s_ in servers: s_.terminate()
os.makedirs('/kaggle/working/clips', exist_ok=True)
for f in glob.glob('/kaggle/working/clips/*'):                     # keep only NNN.mp4 (page number) for the video maker
    if f.endswith('.mp4') and '__' in os.path.basename(f): shutil.move(f, os.path.join('/kaggle/working/clips', os.path.basename(f).split('__')[0] + '.mp4'))
    elif not f.endswith('.mp4'): os.remove(f)
say('JOB DONE: ' + ', '.join(sorted(os.listdir('/kaggle/working/clips'))))
