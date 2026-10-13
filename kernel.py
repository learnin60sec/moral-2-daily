"""KAGGLE JOB (sent automatically by cloud_daily.py): ComfyUI + Wan 2.2 14B + Lightning (4 steps) - the same workflow as the
successful test - makes one 5-second clip per picture listed in job.json. One GPU (14B needs the RAM)."""
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
RIFE_OK = False
try:                                                                  # smooth motion: RIFE frame interpolation (16 -> 32 fps)
    nd = f'{C}/custom_nodes/ComfyUI-Frame-Interpolation'
    if not os.path.exists(nd): subprocess.run(['git', 'clone', '-q', '--depth', '1', 'https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git', nd], check=True)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-r', f'{nd}/requirements-no-cupy.txt'])
    chk = subprocess.run([sys.executable, '-c', f"import sys; sys.path[:0] = ['{C}', '{nd}']; from vfi_models.rife import RIFE_VFI; print('ok')"],
                         capture_output=True, text=True, cwd=C)
    RIFE_OK = 'ok' in chk.stdout
    say('RIFE smooth motion: ' + ('ready' if RIFE_OK else 'not available - clips stay at 16 fps (' + chk.stderr.strip()[-120:] + ')'))
except Exception as e:
    say(f'RIFE smooth motion not available ({str(e)[:100]})')
jobs = glob.glob('/kaggle/input/**/job.json', recursive=True)
if not jobs: sys.exit('job.json not found in the input dataset')
EXPECTED_JOB = None                                                  # filled in by cloud_daily.py for every run
jobs = [j for j in jobs if EXPECTED_JOB is None or json.load(open(j)).get('job_id') == EXPECTED_JOB]
if not jobs: sys.exit(f'STOP: the input is not job {EXPECTED_JOB} (old data) - nothing done')
JOB = json.load(open(jobs[0])); JDIR = os.path.dirname(jobs[0])
say(f"job {JOB.get('job_id')}: {len(JOB['pictures'])} pages, {len(JOB.get('make_pictures', {}))} pictures to draw")
WF = json.loads(r'''{"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}}, "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}}, "3": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", "strength_model": 1.0}}, "4": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["2", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", "strength_model": 1.0}}, "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["3", 0], "shift": 5.0}}, "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["4", 0], "shift": 5.0}}, "7": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}}, "8": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}}, "9": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": "x"}}, "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": "new people appearing, new animals appearing, objects turning into creatures, transformation, morphing, extra limbs, distorted face, changing clothes, camera shake, fast zoom, text, watermark, flicker, blurry"}}, "11": {"class_type": "LoadImage", "inputs": {"image": "example.png"}}, "12": {"class_type": "WanImageToVideo", "inputs": {"positive": ["9", 0], "negative": ["10", 0], "vae": ["8", 0], "start_image": ["11", 0], "width": 832, "height": 480, "length": 81, "batch_size": 1}}, "13": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["5", 0], "add_noise": "enable", "noise_seed": 11, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0], "negative": ["12", 1], "latent_image": ["12", 2], "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable"}}, "14": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["6", 0], "add_noise": "disable", "noise_seed": 0, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0], "negative": ["12", 1], "latent_image": ["13", 0], "start_at_step": 2, "end_at_step": 10000, "return_with_leftover_noise": "disable"}}, "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["8", 0]}}, "16": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["15", 0], "filename_prefix": "wan14b_clip", "fps": 16.0, "lossless": false, "quality": 90, "method": "default"}}}''')
WF['12']['inputs']['length'] = int(round(JOB.get('seconds', 5) * 16 / 4)) * 4 + 1
if JOB.get('size'): WF['12']['inputs']['width'], WF['12']['inputs']['height'] = int(JOB['size'][0]), int(JOB['size'][1])   # smaller = faster
if JOB.get('negative'): WF['10']['inputs']['text'] = JOB['negative']
if RIFE_OK and JOB.get('smooth', True):
    WF['17'] = {'class_type': 'RIFE VFI', 'inputs': {'ckpt_name': 'rife49.pth', 'frames': ['15', 0], 'clear_cache_after_n_frames': 10,
                                                     'multiplier': 2, 'fast_mode': True, 'ensemble': True, 'scale_factor': 1.0}}
    WF['16']['inputs']['images'] = ['17', 0]; WF['16']['inputs']['fps'] = 32.0
    say('clips: 32 fps (RIFE)')                      # e.g. realistic style: no cartoon look
json.dump(WF, open('/kaggle/working/workflow_api.json', 'w'))
RUNNER_TEXT = '"""Runs a ComfyUI workflow (API format) for every picture. Used by the Kaggle notebook; also testable with any ComfyUI URL."""\nimport os, sys, json, time, glob, shutil, subprocess, copy\nimport requests\nCOMFY = os.getenv("COMFY_DIR", "/tmp/ComfyUI"); URL = os.getenv("COMFY_URL", "http://127.0.0.1:8188")\nOUT = os.getenv("OUT_DIR", "/kaggle/working/outputs"); T0 = time.time()\ndef say(x): print(f"[{time.time() - T0:6.0f} s] {x}", flush=True)\n\n\ndef start_comfy():\n    if os.getenv("COMFY_ALREADY_RUNNING") == "1": return None\n    log = open("/kaggle/working/comfy_log.txt" if os.path.isdir("/kaggle/working") else "/tmp/comfy_log.txt", "w")\n    p = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch", "--preview-method", "none"],\n                         cwd=COMFY, stdout=log, stderr=subprocess.STDOUT)\n    say("starting ComfyUI ...")\n    for _ in range(240):\n        try:\n            requests.get(f"{URL}/system_stats", timeout=3); say("ComfyUI is ready"); return p\n        except Exception:\n            if p.poll() is not None: sys.exit("ComfyUI stopped while starting - see comfy_log.txt")\n            time.sleep(2)\n    sys.exit("ComfyUI did not start in 8 minutes - see comfy_log.txt")\n\n\ndef run_one(wf, label):\n    t = time.time()\n    r = requests.post(f"{URL}/prompt", json={"prompt": wf, "client_id": "kaggle"}, timeout=60)\n    if r.status_code != 200: say(f"  {label}: ComfyUI refused the workflow: {r.text[:800]}"); return []\n    pid = r.json()["prompt_id"]; say(f"  {label}: queued (job {pid[:8]})")\n    last = 0\n    while True:\n        time.sleep(5)\n        try: h = requests.get(f"{URL}/history/{pid}", timeout=30).json()\n        except Exception: say("  ComfyUI stopped answering (out of memory?) - see comfy_log.txt"); return []\n        if pid in h: break\n        if time.time() - last > 30: say(f"  {label}: working ... {time.time() - t:.0f} s"); last = time.time()\n    h = h[pid]; st = h.get("status", {})\n    if st.get("status_str") == "error":\n        msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]\n        say(f"  {label}: ERROR {json.dumps(msgs)[:800]}"); return []\n    files = []\n    for node_out in h.get("outputs", {}).values():\n        for key in ("images", "gifs", "videos", "video"):\n            for f in node_out.get(key, []) or []:\n                if isinstance(f, dict) and f.get("filename"):\n                    src = os.path.join(COMFY, f.get("type", "output"), f.get("subfolder", ""), f["filename"])\n                    if os.path.exists(src): files.append(src)\n    say(f"  {label}: done in {time.time() - t:.0f} s, {len(files)} output file(s)")\n    return files\n\n\ndef to_mp4(webp, fps=None):\n    """animated WEBP from ComfyUI -> MP4 next to it, at the clip\'s real speed (every frame\'s own duration is respected)"""\n    try:\n        from PIL import Image, ImageSequence\n        import imageio_ffmpeg\n        im = Image.open(webp); frames, durs = [], []\n        for f in ImageSequence.Iterator(im):\n            frames.append(f.convert("RGB")); durs.append(max(1, f.info.get("duration") or im.info.get("duration") or 42))\n        if len(frames) < 2: return\n        out_fps = 24; total = sum(durs) / 1000.0; n_out = max(2, round(total * out_fps))\n        starts = [sum(durs[:k]) / 1000.0 for k in range(len(durs))]\n        w, h = frames[0].size; w, h = w - w % 2, h - h % 2\n        p = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "quiet", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(out_fps), "-i", "-",\n                              "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", webp[:-5] + ".mp4"], stdin=subprocess.PIPE)\n        k = 0\n        for j in range(n_out):\n            t = j / out_fps\n            while k + 1 < len(starts) and starts[k + 1] <= t: k += 1\n            p.stdin.write(frames[k].crop((0, 0, w, h)).tobytes())\n        p.stdin.close(); p.wait(); say(f"  made {os.path.basename(webp)[:-5]}.mp4 ({total:.1f} s)")\n    except Exception as e:\n        say(f"  (mp4 not made: {str(e)[:80]})")\n\n\ndef main():\n    S = json.load(open(os.getenv("SETTINGS", "/kaggle/working/settings.json")))\n    wf0 = json.load(open(S["workflow"]))\n    loaders = [k for k, n in wf0.items() if n.get("class_type") in ("LoadImage", "LoadImageMask", "VHS_LoadImagePath")]\n    texts = [k for k, n in wf0.items() if n.get("class_type") in ("CLIPTextEncode", "TextEncodeHunyuanVideo_ImageToVideo") or "prompt" in str(n.get("_meta", {}).get("title", "")).lower()]\n    say(f"workflow: {len(wf0)} nodes | picture inputs: {loaders or \'none\'} | text prompts: {texts or \'none\'}")\n    proc = start_comfy()\n    os.makedirs(OUT, exist_ok=True); os.makedirs(os.path.join(COMFY, "input"), exist_ok=True)\n    pics = S.get("pictures") or [None]\n    for i, pic in enumerate(pics, 1):\n        wf = copy.deepcopy(wf0); label = f"{i}/{len(pics)} {os.path.basename(pic) if pic else \'run\'}"\n        if pic:\n            name = f"in_{i:03d}_{os.path.basename(pic)}"; shutil.copy(pic, os.path.join(COMFY, "input", name))\n            for k in loaders: wf[k]["inputs"]["image"] = name\n        ptxt = (S.get("prompts") or [None] * len(pics))[i - 1] or S.get("prompt")\n        if ptxt and texts:\n            k = texts[0]\n            for field in ("text", "prompt", "positive_prompt"):\n                if field in wf[k]["inputs"] and isinstance(wf[k]["inputs"][field], str): wf[k]["inputs"][field] = ptxt; break\n            say(f"  {label}: prompt = {ptxt[:90]}...")\n        for f in run_one(wf, label):\n            base = os.path.splitext(os.path.basename(pic))[0] if pic else "run"\n            dst = os.path.join(OUT, f"{base}__{os.path.basename(f)}"); shutil.copy(f, dst)\n            if dst.lower().endswith(".webp"): to_mp4(dst)\n    shutil.make_archive(OUT, "zip", OUT)\n    say(f"ALL DONE -> {OUT}.zip  ({len(os.listdir(OUT))} files)")\n    if proc: proc.terminate()\n\n\nif __name__ == "__main__":\n    main()\n'

# ---------- PICTURES: drawn here with ComfyUI. image_model "schnell" = FLUX schnell (fast) | "kontext" = FLUX Kontext (same characters on every page)
MAKE = JOB.get('make_pictures', {})
MADE = '/kaggle/working/clips'; os.makedirs(MADE, exist_ok=True)
def KEEP(path, name):
    """save a drawn picture as NNN.png; black bars drawn by the model are cut away and the 16:9 frame is filled again"""
    from PIL import Image as _I
    import numpy as _np
    im_ = _I.open(path).convert('RGB'); a_ = _np.asarray(im_.convert('L')).astype(float)
    def _edge(lines):                                               # outer lines that are a flat dark bar (dark AND without detail)
        n_ = 0
        for ln in lines:
            if ln.mean() < 45 and ln.std() < 9: n_ += 1
            else: break
        return n_
    t_, b_, l_, r_ = _edge(a_), _edge(a_[::-1]), _edge(a_.T), _edge(a_.T[::-1])
    if max(t_, b_, l_, r_) > 6:
        im_ = im_.crop((l_, t_, im_.width - r_, im_.height - b_)); W_, H_ = 1344, 768
        sc_ = max(W_ / im_.width, H_ / im_.height); im_ = im_.resize((int(im_.width * sc_ + 1), int(im_.height * sc_ + 1)), _I.LANCZOS)
        x_, y_ = (im_.width - W_) // 2, (im_.height - H_) // 2; im_ = im_.crop((x_, y_, x_ + W_, y_ + H_))
        say(f'   {name}: black bars removed ({t_}/{b_}/{l_}/{r_} px)')
    im_.save(os.path.join(MADE, name)); say(f'   drew {name}')
if MAKE:
    KONTEXT = JOB.get('image_model') == 'kontext'
    say(f"drawing {len(MAKE)} pictures with {'FLUX Kontext (same characters)' if KONTEXT else 'FLUX schnell'} ...")
    from huggingface_hub import hf_hub_download as _dl
    if KONTEXT:
        need_ = [('Comfy-Org/flux1-kontext-dev_ComfyUI', 'split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors', 'diffusion_models'),
                 ('comfyanonymous/flux_text_encoders', 'clip_l.safetensors', 'text_encoders'),
                 ('comfyanonymous/flux_text_encoders', 't5xxl_fp8_e4m3fn_scaled.safetensors', 'text_encoders'),
                 ('Comfy-Org/Lumina_Image_2.0_Repackaged', 'split_files/vae/ae.safetensors', 'vae')]
    else:
        need_ = [('Comfy-Org/flux1-schnell', 'flux1-schnell-fp8.safetensors', 'checkpoints')]
    PIC_FILES = []
    for repo_, path_, folder_ in need_:
        dst_ = f'{C}/models/{folder_}/{os.path.basename(path_)}'; os.makedirs(os.path.dirname(dst_), exist_ok=True)
        if not os.path.exists(dst_): shutil.move(_dl(repo_, path_, local_dir='/tmp/hf'), dst_)
        PIC_FILES.append(dst_)
    open('/kaggle/working/run_comfy.py', 'w').write(RUNNER_TEXT); sys.path.insert(0, '/kaggle/working')
    os.environ.update(COMFY_DIR=C, OUT_DIR='/kaggle/working/flux_out')
    import importlib, run_comfy as R; importlib.reload(R)
    proc = R.start_comfy()
    if KONTEXT:
        KW = json.loads(r'''{"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev-kontext_fp8_scaled.safetensors", "weight_dtype": "default"}}, "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "flux", "device": "default"}}, "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}}, "4": {"class_type": "LoadImage", "inputs": {"image": "cast.png"}}, "5": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["4", 0]}}, "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}}, "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "x"}}, "8": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]}}, "9": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["8", 0], "guidance": 2.5}}, "10": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}}, "11": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1344, "height": 768, "batch_size": 1}}, "12": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 7, "steps": 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["9", 0], "negative": ["10", 0], "latent_image": ["11", 0], "denoise": 1.0}}, "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}}, "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": "page"}}}''')
        CW = json.loads(r'''{"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev-kontext_fp8_scaled.safetensors", "weight_dtype": "default"}}, "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "flux", "device": "default"}}, "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}}, "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "x"}}, "9": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["7", 0], "guidance": 3.5}}, "10": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}}, "11": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1344, "height": 768, "batch_size": 1}}, "12": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 2024, "steps": 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["9", 0], "negative": ["10", 0], "latent_image": ["11", 0], "denoise": 1.0}}, "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}}, "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": "cast"}}}''')
        cw = json.loads(json.dumps(CW)); cw['7']['inputs']['text'] = JOB.get('cast_prompt', '')
        files = R.run_one(cw, 'cast sheet')
        if not files: sys.exit('STOP: the cast sheet could not be drawn')
        os.makedirs(f'{C}/input', exist_ok=True); shutil.copy(files[0], f'{C}/input/cast.png'); shutil.copy(files[0], os.path.join(MADE, 'cast.png'))
        say('   cast sheet ready')
        for n, (name, prompt) in enumerate(sorted(MAKE.items()), 1):
            w = json.loads(json.dumps(KW))
            w['7']['inputs']['text'] = ("Use the characters from the reference image and keep them EXACTLY the same: same faces, hair, body, skin tone, "
                                       "clothes and colours. Draw a completely new scene with the characters in new poses. " + prompt)
            w['12']['inputs']['seed'] = 1000 + n
            files = R.run_one(w, f'picture {n}/{len(MAKE)} {name}')
            if files: KEEP(files[0], name)
    else:
        FW = json.loads(r'''{"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}}, "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "x"}}, "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": ""}}, "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1344, "height": 768, "batch_size": 1}}, "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 7, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "denoise": 1.0}}, "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}}, "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "page"}}}''')
        for n, (name, prompt) in enumerate(sorted(MAKE.items()), 1):
            w = json.loads(json.dumps(FW)); w['2']['inputs']['text'] = prompt; w['5']['inputs']['seed'] = 1000 + n
            files = R.run_one(w, f'picture {n}/{len(MAKE)} {name}')
            if files: KEEP(files[0], name)
    if proc: proc.terminate(); time.sleep(5)
    for f_ in PIC_FILES:                                            # free the disk before the video models arrive
        if os.path.exists(f_): os.remove(f_)
def pic_path(n):
    p = os.path.join(JDIR, n)
    return p if os.path.exists(p) else os.path.join(MADE, n)
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
for _n, _f in (('wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors', 'diffusion_models'), ('wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors', 'diffusion_models'),
                ('wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors', 'loras'), ('wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors', 'loras'),
                ('wan_2.1_vae.safetensors', 'vae')):
    KNOWN[_n] = ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', f'split_files/{_f}/{_n}', _f)
NEED = sorted({v for n in WF.values() for v in n['inputs'].values() if isinstance(v, str) and v.endswith('.safetensors')})
for name in NEED:
    repo, path, folder = KNOWN[name]; os.makedirs(f'{M}/{folder}', exist_ok=True)
    if not os.path.exists(f'{M}/{folder}/{name}'):
        f = hf_hub_download(repo, path, local_dir='/tmp/hf'); shutil.move(f, f'{M}/{folder}/{name}')
    say(f'model ready: {name}')
open('/kaggle/working/run_comfy.py', 'w').write(RUNNER_TEXT)
pics = [pic_path(n) for n in JOB['pictures'] if os.path.exists(pic_path(n))]
json.dump({'workflow': '/kaggle/working/workflow_api.json', 'pictures': pics, 'prompts': [JOB['prompts'].get(os.path.basename(n), '') for n in pics]},
          open('/kaggle/working/settings.json', 'w'))
env = dict(os.environ, OUT_DIR='/kaggle/working/clips', SETTINGS='/kaggle/working/settings.json', COMFY_DIR=C)
subprocess.run([sys.executable, '/kaggle/working/run_comfy.py'], cwd='/kaggle/working', env=env)
os.makedirs('/kaggle/working/clips', exist_ok=True)
UPSCALED = 0
if JOB.get('upscale', True):
    subprocess.run(['pkill', '-f', 'main.py'], capture_output=True); time.sleep(5)          # the video models leave the GPU
    try:
        import torch, numpy as np, imageio_ffmpeg
        from spandrel import ModelLoader
        up = f'{C}/models/upscale_models/RealESRGAN_x4plus_anime_6B.pth'; os.makedirs(os.path.dirname(up), exist_ok=True)
        if not os.path.exists(up):
            import urllib.request
            urllib.request.urlretrieve('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth', up)
        net = ModelLoader().load_from_file(up).model.eval().cuda().half()
        FF = imageio_ffmpeg.get_ffmpeg_exe(); OW, OH = 1280, 738
        for clip in sorted(glob.glob('/kaggle/working/clips/*.mp4')):
            t0 = time.time()
            info = subprocess.run([FF, '-i', clip], capture_output=True, text=True).stderr
            import re as _re
            mm = _re.search(r', (\d+)x(\d+)[, ]', info); fr = _re.search(r'([\d.]+) fps', info)
            if not mm: continue
            w, h = int(mm.group(1)), int(mm.group(2)); fps = fr.group(1) if fr else '32'
            rd = subprocess.Popen([FF, '-v', 'quiet', '-i', clip, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
            tmp = clip[:-4] + '_up.mp4'
            wr = subprocess.Popen([FF, '-y', '-v', 'quiet', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OW}x{OH}', '-r', fps, '-i', '-',
                                   '-c:v', 'libx264', '-crf', '15', '-preset', 'medium', '-pix_fmt', 'yuv420p', tmp], stdin=subprocess.PIPE)
            n = 0
            with torch.no_grad():
                while True:
                    raw = rd.stdout.read(w * h * 3)
                    if len(raw) < w * h * 3: break
                    x = torch.frombuffer(bytearray(raw), dtype=torch.uint8).view(h, w, 3).permute(2, 0, 1)[None].cuda().half() / 255.0
                    y = net(x).clamp(0, 1)
                    y = torch.nn.functional.interpolate(y.float(), size=(OH, OW), mode='bilinear', antialias=True, align_corners=False)
                    wr.stdin.write((y[0].permute(1, 2, 0) * 255).round().byte().cpu().numpy().tobytes()); n += 1
            wr.stdin.close(); wr.wait(); rd.wait()
            if n > 10 and os.path.getsize(tmp) > 20000: os.replace(tmp, clip); UPSCALED += 1
            elif os.path.exists(tmp): os.remove(tmp)
            say(f'   sharper: {os.path.basename(clip)} ({n} frames, {time.time() - t0:.0f} s)')
    except Exception as e:
        say(f'upscaler not used ({str(e)[:150]}) - clips kept as they are')
for f in glob.glob('/kaggle/working/clips/*'):                     # keep NNN.mp4 (clips) and NNN.png (drawn pictures)
    b_ = os.path.basename(f)
    if f.endswith('.mp4') and '__' in b_: shutil.move(f, os.path.join('/kaggle/working/clips', b_.split('__')[0] + '.mp4'))
    elif not (f.endswith('.mp4') or (f.endswith('.png') and len(b_) == 7)): os.remove(f)
made_pics = sorted(f for f in os.listdir('/kaggle/working/clips') if f.endswith('.png'))
made_clips = sorted(f for f in os.listdir('/kaggle/working/clips') if f.endswith('.mp4'))
def _tail(path, n=40):
    try: return open(path, errors='ignore').read().splitlines()[-n:]
    except Exception: return []
report = {'job_id': JOB.get('job_id'), 'smooth_rife': RIFE_OK, 'upscaled': UPSCALED, 'pictures_asked': sorted(JOB.get('make_pictures', {})), 'pictures_made': made_pics, 'clips_asked': JOB['pictures'], 'clips_made': made_clips,
          'minutes': round((time.time() - T0) / 60, 1), 'comfy_log_tail': _tail('/kaggle/working/comfy_log.txt') + _tail('/tmp/comfy_log.txt')}
json.dump(report, open('/kaggle/working/clips/report.json', 'w'), indent=1)
import zipfile
with zipfile.ZipFile('/kaggle/working/results.zip', 'w', zipfile.ZIP_STORED) as z:
    for f in os.listdir('/kaggle/working/clips'):
        if f.endswith(('.mp4', '.png', '.json')): z.write(os.path.join('/kaggle/working/clips', f), f)
for f in glob.glob('/kaggle/working/clips/*'): os.remove(f)          # only results.zip (+ logs) is left to download
say(f'JOB DONE: {len(made_pics)} pictures, {len(made_clips)} clips -> results.zip')
