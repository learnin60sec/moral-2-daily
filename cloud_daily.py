"""
CLOUD DAILY - runs on GitHub every day, laptop can stay OFF.
 1 story + one-take voice   2 pictures (Cloudflare FLUX, 2nd account when the 1st is used up)
 3 key moments + AI video prompts (Groq vision)   4 Kaggle job: ComfyUI + Wan 2.2 clips   5 video   6 YouTube upload
Settings (env): M2_MINUTES 3 | M2_SECONDS_PER_PICTURE 5 | M2_CLIPS 10 | M2_KAGGLE_MINUTES 240 | M2_AUTO_UPLOAD 1
"""
import os, sys, json, time, glob, shutil, base64, io, subprocess, re
_ME = os.path.dirname(os.path.abspath(__file__))
HERE = _ME if os.path.exists(os.path.join(_ME, "m2.py")) else os.path.dirname(_ME)   # flat repo or the moral_2 folder
sys.path.insert(0, HERE)
os.environ.setdefault("M2_SECONDS_PER_PICTURE", "5"); os.environ.setdefault("STUDIO_UNATTENDED", "1")
import requests
import studio as S, m2
T0 = time.time(); LOG = os.path.join(HERE, "cloud_log.txt")
def say(x):
    line = f"[{time.strftime('%H:%M:%S')} +{(time.time() - T0) / 60:5.1f} min] {x}"; print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


# ---------------------------------------------------------------- 2) pictures with Cloudflare FLUX
def cf_accounts():
    acc = [(os.getenv("CLOUDFLARE_ACCOUNT_ID"), os.getenv("CLOUDFLARE_API_TOKEN")), (os.getenv("CLOUDFLARE2_ACCOUNT_ID"), os.getenv("CLOUDFLARE2_API_TOKEN"))]
    return [a for a in acc if a[0] and a[1]]


def flux(prompt, acc):
    """bytes of one picture | ("LIMIT", message) when this account's free DAILY amount is used up | None on other errors.
    'Too many requests right now' (rate limit) is NOT the daily limit: wait and try again."""
    for wait in (0, 20, 40, 60, 90):
        if wait: time.sleep(wait)
        try:
            r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc[0]}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                              headers={"Authorization": f"Bearer {acc[1]}"}, json={"prompt": prompt, "steps": 8}, timeout=180)
        except Exception as e:
            say(f"   picture: network {str(e)[:80]} - trying again"); continue
        if r.headers.get("content-type", "").startswith("image/"): return r.content
        try: j = r.json()
        except Exception: j = {"raw": r.text[:300]}
        if r.status_code == 200 and isinstance(j, dict) and j.get("result", {}).get("image"): return base64.b64decode(j["result"]["image"])
        text = json.dumps(j.get("errors", j) if isinstance(j, dict) else j, ensure_ascii=False)[:300]
        low = text.lower()
        if any(w in low for w in ("4006", "neuron", "daily", "allocation", "free tier", "quota")):
            return ("LIMIT", f"{r.status_code} {text}")
        if r.status_code in (429, 500, 502, 503, 504):
            say(f"   Cloudflare busy ({r.status_code}): {text[:120]} - waiting and trying again"); continue
        say(f"   picture error {r.status_code}: {text[:200]}"); return None
    return None


def make_pictures(P, st):
    looks = st.get("characters", {}); accs = cf_accounts(); ai = 0; d = P.p(m2.pics_dir(P)); os.makedirs(d, exist_ok=True)
    if not accs: say("NO Cloudflare keys - pictures cannot be made"); return 0
    made = 0
    for i, p in enumerate(st["pictures"], 1):
        out = os.path.join(d, f"{i:03d}.png")
        if os.path.exists(out): made += 1; continue
        prompt = m2.full_prompt(p, looks) + " Always the same character design and the same clothes in every picture."
        for _try in range(3):
            res = flux(prompt, accs[ai])
            if isinstance(res, tuple):
                say(f"   account {ai + 1} says: {res[1][:200]}")
                ai += 1
                if ai >= len(accs): say(f"   Cloudflare free amount used up at picture {i} - the video uses {made} pictures"); return made
                say(f"   -> account {ai + 1}"); continue
            if res: S.clean_frame(res, out); made += 1; break
            time.sleep(3)
        if i % 10 == 0: say(f"   pictures {i}/{len(st['pictures'])}")
    return made


# ---------------------------------------------------------------- 3) key moments + AI prompts
def key_pages(P, st, k):
    have = [i for i in range(1, len(st["pictures"]) + 1) if os.path.exists(P.p(m2.pics_dir(P), f"{i:03d}.png"))]
    if k <= 0: return list(range(1, len(st["pictures"]) + 1))        # M2_CLIPS=all -> EVERY page becomes a moving clip
    first = []
    for bi in range(len(st["beats"])):
        mine = [i for i in have if st["pictures"][i - 1]["beat"] == bi]
        if mine: first.append(mine[len(mine) // 2])                  # the middle moment of every part
    if len(first) > k: first = [first[round(j * (len(first) - 1) / (k - 1))] for j in range(k)] if k > 1 else first[:1]
    return sorted(set(first))


def ai_prompt(pic, moment):
    """the AI LOOKS at the picture and writes the Wan 2.2 prompt: Groq vision first, Gemini vision second, story text last"""
    STYLE = " Premium 2D cartoon style, the same characters with exactly the same faces, clothes and colours."
    fallback = (moment.rstrip(". ") + ". " if moment else "") + ("The characters make small natural movements, gentle wind moves the grass, "
                "static camera, nothing enters the frame from the edges, nothing covers any face." + STYLE)
    from PIL import Image
    im = Image.open(pic).convert("RGB"); im.thumbnail((768, 768)); b = io.BytesIO(); im.save(b, "JPEG", quality=85)
    img64 = base64.b64encode(b.getvalue()).decode()
    ask = ("You write prompts for the Wan 2.2 image-to-video model. Look at this 2D cartoon picture; it is the FIRST frame of a 5-second clip. "
           "Write ONE English prompt of 50-80 words in this order: (1) the main character and ONE clear action that fits the picture"
           + (f" and this story moment: '{moment}'" if moment else "") + "; (2) one small movement for each other person or animal; "
           "(3) one gentle background movement (grass, clouds, smoke or water). Then end with exactly: 'Static camera. Nothing enters the frame "
           "from the edges. No leaves or branches cover any face. Same faces and clothes.' Do not invent people, animals or objects that are "
           "not in the picture. Return only the prompt.")
    why = []
    gk = os.getenv("GROQ_API_KEY")
    if gk:
        for model in ("meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"):
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {gk}"}, timeout=60,
                                  json={"model": model, "temperature": 0.3, "messages": [{"role": "user", "content": [
                                      {"type": "text", "text": ask}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img64}}]}]})
                if r.status_code == 200:
                    t = r.json()["choices"][0]["message"]["content"].strip().strip('"')
                    if 30 < len(t) < 1500: return t + STYLE, "Groq"
                why.append(f"Groq {model.split('/')[-1][:20]} {r.status_code}: {r.text[:90]}")
            except Exception as e:
                why.append(f"Groq {str(e)[:80]}")
    key = os.getenv("GEMINI_API_KEY")
    if key:
        for model in ("gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest"):
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, timeout=60,
                                  json={"contents": [{"parts": [{"text": ask}, {"inline_data": {"mime_type": "image/jpeg", "data": img64}}]}]})
                if r.status_code == 200:
                    t = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"')
                    if 30 < len(t) < 1500: return t + STYLE, "Gemini"
                why.append(f"Gemini {model} {r.status_code}: {r.text[:90]}")
            except Exception as e:
                why.append(f"Gemini {str(e)[:80]}")
    say("   (AI could not look at the picture: " + " | ".join(why)[:300] + ")")
    return fallback, "story text"

# ---------------------------------------------------------------- 4) Kaggle job
def kaggle_accounts():
    """account 1 = KAGGLE_*, account 2 = KAGGLE2_* (each: username + key or api token)"""
    out = []
    for pre in ("KAGGLE", "KAGGLE2"):
        u, k, t = os.getenv(f"{pre}_USERNAME"), os.getenv(f"{pre}_KEY"), os.getenv(f"{pre}_API_TOKEN")
        if u and (k or t): out.append({"user": u, "key": k, "token": t, "name": pre})
    return out


def kaggle_cli(*args, acc=None, check=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("KAGGLE")}
    if acc:
        cfg = f"/tmp/kcfg_{acc['name']}"; os.makedirs(cfg, exist_ok=True)
        env.update({"KAGGLE_USERNAME": acc["user"], "KAGGLE_CONFIG_DIR": cfg})
        if acc["key"]: env["KAGGLE_KEY"] = acc["key"]
        if acc["token"]: env["KAGGLE_API_TOKEN"] = acc["token"]
    r = subprocess.run(["kaggle"] + list(args), capture_output=True, text=True, env=env)
    if check and r.returncode != 0: raise RuntimeError(f"kaggle {' '.join(args)}: {r.stdout[-300:]} {r.stderr[-300:]}")
    return r


def start_job(acc, P, names, prompts, tag):
    """upload the pictures + prompts as this account's dataset and start its Kaggle job"""
    ds_id, k_id = f"{acc['user']}/m2-clips-job", f"{acc['user']}/m2-clips"
    jd = f"/tmp/m2_job_{tag}"; shutil.rmtree(jd, ignore_errors=True); os.makedirs(jd)
    draw = {}
    for n in names:
        src = P.p(m2.pics_dir(P), n)
        if os.path.exists(src): shutil.copy(src, os.path.join(jd, n))
        else: draw[n] = DRAW.get(n, "")
    json.dump({"pictures": names, "prompts": {n: prompts[n] for n in names}, "make_pictures": draw, "seconds": 5}, open(os.path.join(jd, "job.json"), "w"))
    json.dump({"title": "m2-clips-job", "id": ds_id, "licenses": [{"name": "CC0-1.0"}]}, open(os.path.join(jd, "dataset-metadata.json"), "w"))
    r = kaggle_cli("datasets", "version", "-p", jd, "-m", time.strftime("%Y-%m-%d %H:%M"), "-r", "zip", acc=acc)
    if r.returncode != 0: kaggle_cli("datasets", "create", "-p", jd, "-r", "zip", acc=acc, check=True)
    for _ in range(30):
        if "ready" in kaggle_cli("datasets", "status", ds_id, acc=acc).stdout.lower(): break
        time.sleep(20)
    kd = f"/tmp/m2_kernel_{tag}"; shutil.rmtree(kd, ignore_errors=True); os.makedirs(kd)
    kern = [k_ for k_ in (os.path.join(_ME, "kaggle_job", "kernel.py"), os.path.join(_ME, "kernel.py"), os.path.join(HERE, "kernel.py")) if os.path.exists(k_)]
    if not kern: raise RuntimeError("kernel.py not found next to cloud_daily.py")
    shutil.copy(kern[0], os.path.join(kd, "kernel.py"))
    json.dump({"id": k_id, "title": "m2-clips", "code_file": "kernel.py", "language": "python", "kernel_type": "script", "is_private": True,
               "enable_gpu": True, "enable_internet": True, "dataset_sources": [ds_id], "competition_sources": [], "kernel_sources": []},
              open(os.path.join(kd, "kernel-metadata.json"), "w"))
    kaggle_cli("kernels", "push", "-p", kd, acc=acc, check=True)
    return k_id


DRAW = {}


def kaggle_clips(P, st, pages):
    accs = kaggle_accounts()
    if not accs: say("no Kaggle keys -> video without AI clips"); return 0
    prompts = {}; looks = st.get("characters", {})
    os.makedirs(P.p(m2.pics_dir(P)), exist_ok=True); os.makedirs(P.p("clips"), exist_ok=True)
    for i in pages:
        name = f"{i:03d}.png"; moment = st["pictures"][i - 1].get("action", "")
        if os.path.exists(P.p(m2.pics_dir(P), name)):
            prompts[name], who = ai_prompt(P.p(m2.pics_dir(P), name), moment)
        else:                                                         # no picture yet: Kaggle draws it first (FLUX), prompt from the story
            DRAW[name] = m2.full_prompt(st["pictures"][i - 1], looks) + " Always the same character design and the same clothes in every picture."
            prompts[name], who = (moment.rstrip(". ") + ". " if moment else "") + ("The characters make small natural movements, gentle wind moves the grass, "
                                  "static camera, nothing enters the frame from the edges, nothing covers any face. Premium 2D cartoon style, the same "
                                  "characters with exactly the same faces, clothes and colours."), "story text (picture drawn on Kaggle)"
        say(f"   prompt {name} (written by {who}): {prompts[name][:110]}...")
    if DRAW: say(f"   {len(DRAW)} pictures will be drawn on Kaggle with ComfyUI (FLUX)")
    names = sorted(prompts); jobs = []
    for n, acc in enumerate(accs):                                     # pages shared out: 1st, 3rd, 5th ... / 2nd, 4th ...
        mine = names[n::len(accs)]
        if not mine: continue
        try:
            jobs.append((acc, start_job(acc, P, mine, prompts, acc["name"]), mine))
            say(f"   Kaggle job started on account {n + 1} ({acc['user']}): {len(mine)} clips, about {len(mine) * 15 + 20} min")
        except Exception as e:
            say(f"   account {n + 1} could not start: {str(e)[:200]}")
    limit = time.time() + 60 * float(os.getenv("M2_KAGGLE_MINUTES", "300")); done = {}
    while jobs and len(done) < len(jobs) and time.time() < limit:
        time.sleep(60)
        for acc, k_id, mine in jobs:
            if k_id + acc["name"] in done: continue
            stt = kaggle_cli("kernels", "status", k_id, acc=acc).stdout.lower()
            if any(w in stt for w in ("complete", "error", "cancel")): done[k_id + acc["name"]] = stt
        if int(time.time() - T0) % 900 < 60: say(f"   Kaggle working ... {len(done)} of {len(jobs)} accounts finished")
    os.makedirs(P.p("clips"), exist_ok=True); got = 0
    for n_acc, (acc, k_id, mine) in enumerate(jobs, 1):
        stt = done.get(k_id + acc["name"], "not finished in time")
        say(f"   account {n_acc}: Kaggle job status = {stt.strip()[-60:]}")
        od = f"/tmp/m2_out_{acc['name']}"; shutil.rmtree(od, ignore_errors=True); os.makedirs(od)
        try: kaggle_cli("kernels", "output", k_id, "-p", od, acc=acc)          # also after an error: whatever was made is used
        except Exception as e: say(f"   account {n_acc}: could not download the results ({str(e)[:120]})"); continue
        import zipfile
        for zf in glob.glob(os.path.join(od, "**", "results.zip"), recursive=True):
            with zipfile.ZipFile(zf) as z: z.extractall(os.path.join(od, "results"))
        rep = glob.glob(os.path.join(od, "**", "report.json"), recursive=True)
        if rep:
            r_ = json.load(open(rep[0]))
            say(f"   account {n_acc} report: pictures {len(r_.get('pictures_made', []))}/{len(r_.get('pictures_asked', []))}, "
                f"clips {len(r_.get('clips_made', []))}/{len(r_.get('clips_asked', []))}, {r_.get('minutes')} min on Kaggle")
            if len(r_.get("clips_made", [])) < len(r_.get("clips_asked", [])):
                for line in r_.get("comfy_log_tail", [])[-12:]: say(f"      ComfyUI: {line[:160]}")
        else:
            say(f"   account {n_acc}: no report from Kaggle - last lines of the Kaggle log:")
        logs = [f for f in glob.glob(os.path.join(od, "**", "*.log"), recursive=True)]
        if logs and (not rep or "complete" not in stt):
            try:
                txt = open(logs[0], errors="ignore").read()
                for line in re.findall(r'"data":"(.*?)"', txt)[-15:] or txt.splitlines()[-15:]: say(f"      Kaggle: {line[:160]}")
            except Exception: pass
        for f in glob.glob(os.path.join(od, "**", "*.mp4"), recursive=True):
            name = os.path.basename(f).split("__")[0]
            if re.fullmatch(r"\d{3}\.mp4", name): shutil.copy(f, P.p("clips", name)); got += 1
        for f in glob.glob(os.path.join(od, "**", "*.png"), recursive=True):    # pictures drawn on Kaggle
            name = os.path.basename(f); dst = P.p(m2.pics_dir(P), name)
            if re.fullmatch(r"\d{3}\.png", name) and not os.path.exists(dst): S.clean_frame(open(f, "rb").read(), dst); say(f"   picture {name} drawn on Kaggle")
    say(f"   {got} AI clips received (of {len(pages)})"); return got

# ---------------------------------------------------------------- 4b) CLIP DOCTOR
def _clip_frames(path, n=9, w=160, h=90):
    import numpy as np
    raw = subprocess.run([S.ffmpeg(), "-v", "quiet", "-i", path, "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    if not raw: return None
    a = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype("float64")
    return a[np.linspace(0, len(a) - 1, n).astype(int)]


def _worst_similarity(a, b, k=10):
    import numpy as np
    vals = []
    for i in range(0, a.shape[0] - k + 1, k):
        for j in range(0, a.shape[1] - k + 1, k):
            x, y = a[i:i + k, j:j + k], b[i:i + k, j:j + k]; mx, my = x.mean(), y.mean()
            vals.append(((2 * mx * my + 6.5) * (2 * ((x - mx) * (y - my)).mean() + 58.5)) / ((mx ** 2 + my ** 2 + 6.5) * (x.var() + y.var() + 58.5)))
    return float(np.percentile(vals, 10))


def _ai_clip_ok(path):
    """AI eyes: first and last frame - did anything turn into something else, a new character appear, or a face melt?"""
    key_g, key_m = os.getenv("GROQ_API_KEY"), os.getenv("GEMINI_API_KEY")
    if not (key_g or key_m): return True, "no AI check"
    imgs = []
    for t in ("0.1", "4.7"):
        raw = subprocess.run([S.ffmpeg(), "-v", "quiet", "-ss", t, "-i", path, "-frames:v", "1", "-vf", "scale=512:-2", "-f", "image2", "-c:v", "mjpeg", "-"], capture_output=True).stdout
        if raw: imgs.append(base64.b64encode(raw).decode())
    if len(imgs) < 2: return True, "frames not read"
    ask = ("Picture 1 is the first frame and picture 2 the last frame of a 5-second cartoon clip. Answer NO only if something clearly went "
           "wrong: a person or animal turned into something else, a new person or creature appeared, a face or body melted or became "
           "distorted, or the scene changed to a different place. Small natural movements are fine. "
           'JSON only: {"ok": true or false, "problem": "short reason"}')
    try:
        if key_g:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key_g}"}, timeout=60,
                              json={"model": "meta-llama/llama-4-scout-17b-16e-instruct", "temperature": 0, "response_format": {"type": "json_object"},
                                    "messages": [{"role": "user", "content": [{"type": "text", "text": ask}] + [
                                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}} for b in imgs]}]})
            if r.status_code == 200:
                j = S.parse(r.json()["choices"][0]["message"]["content"]); return bool(j.get("ok", True)), str(j.get("problem", ""))[:100]
        if key_m:
            r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent", headers={"x-goog-api-key": key_m}, timeout=60,
                              json={"contents": [{"parts": [{"text": ask}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in imgs]}],
                                    "generationConfig": {"responseMimeType": "application/json"}})
            if r.status_code == 200:
                j = S.parse(r.json()["candidates"][0]["content"]["parts"][0]["text"]); return bool(j.get("ok", True)), str(j.get("problem", ""))[:100]
    except Exception:
        pass
    return True, "AI check not answered"


def clip_doctor(P):
    """every AI clip is checked; a bad one is moved to clips_rejected/ and its page uses the living picture instead"""
    clips = sorted(glob.glob(P.p("clips", "*.mp4")))
    if not clips: return
    os.makedirs(P.p("clips_rejected"), exist_ok=True); bad = 0
    for c in clips:
        fr = _clip_frames(c); why = None
        if fr is None or len(fr) < 3: why = "unreadable"
        else:
            import numpy as np
            sim = min(_worst_similarity(fr[0], f) for f in fr[1:]); jump = max(float(np.abs(fr[i + 1] - fr[i]).mean()) for i in range(len(fr) - 1))
            if sim < float(os.getenv("M2_CLIP_MIN_SIMILARITY", "0.05")) or jump > float(os.getenv("M2_CLIP_MAX_JUMP", "25")):
                why = f"melting / scene jump (similarity {sim:.2f}, jump {jump:.0f})"
        if not why:
            ok, prob = _ai_clip_ok(c)
            if not ok: why = f"AI: {prob}"
        if why:
            shutil.move(c, P.p("clips_rejected", os.path.basename(c))); bad += 1
            say(f"   CLIP DOCTOR: {os.path.basename(c)} REJECTED - {why} -> this page uses the living picture")
    say(f"   CLIP DOCTOR: {len(clips) - bad} of {len(clips)} clips passed")


# ---------------------------------------------------------------- the day
def main():
    minutes = float(os.getenv("M2_MINUTES", "3")); kc = os.getenv("M2_CLIPS", "all").lower()
    k = 0 if kc in ("all", "0", "") else int(kc)
    say(f"=== CLOUD DAILY: {minutes:.0f}-min video, AI clips: {'ALL pictures' if k == 0 else k} ===")
    say("STEP 1 story + voice"); P = m2.story(minutes); st = P.load("story.json")
    say(f"   {st.get('title', '')}: {len(st['pictures'])} pictures needed")
    src_ = os.getenv("M2_PICTURES", "kaggle").lower()
    if src_ == "kaggle" and kaggle_accounts():                        # pictures drawn on Kaggle with ComfyUI (FLUX), no Cloudflare limits
        say("STEP 2 pictures: drawn on Kaggle with ComfyUI (FLUX) in the same job as the clips"); made = 0
    else:
        say("STEP 2 pictures (Cloudflare)"); made = make_pictures(P, st); say(f"   {made} pictures made")
    if src_ == "kaggle" and kaggle_accounts():
        pass
    elif made < len(st["pictures"]) and kaggle_accounts():
        say(f"   {len(st['pictures']) - made} pictures missing -> Kaggle will draw them (FLUX) before making the clips")
    elif made < len(st["pictures"]) * 0.5:                              # no Kaggle: one more chance after a pause
        say("   too few pictures - waiting 15 min and trying once more"); time.sleep(900)
        made = make_pictures(P, st); say(f"   {made} pictures made")
        if made < len(st["pictures"]) * 0.5: say("STOP: too few pictures today (Cloudflare limit?) - try again tomorrow"); sys.exit(1)
    say("STEP 3+4 key moments -> Kaggle clips")
    try: kaggle_clips(P, st, key_pages(P, st, k))
    except Exception as e: say(f"   Kaggle step failed ({str(e)[:200]}) -> video without AI clips")
    say("STEP 4b clip doctor"); clip_doctor(P)
    have = len(glob.glob(P.p(m2.pics_dir(P), "*.png")))
    if have < len(st["pictures"]) and cf_accounts():                  # Kaggle missed some pictures -> Cloudflare fills only those
        say(f"   {len(st['pictures']) - have} pictures still missing -> Cloudflare backup"); make_pictures(P, st)
        have = len(glob.glob(P.p(m2.pics_dir(P), "*.png")))
    if have < len(st["pictures"]) * 0.5: say(f"STOP: only {have} of {len(st['pictures'])} pictures (Cloudflare and Kaggle) - try again tomorrow"); sys.exit(1)
    say("STEP 5 video"); m2.video(True)
    qc = open(P.p("QC_REPORT.txt"), encoding="utf-8").read() if os.path.exists(P.p("QC_REPORT.txt")) else ""
    say("   QC: " + qc.splitlines()[0] if qc else "   QC missing")
    open(P.p("FINAL_DONE"), "w").write(time.strftime("%Y-%m-%d %H:%M"))
    if os.getenv("M2_AUTO_UPLOAD", "1") == "1" and os.path.exists(os.path.join(HERE, "youtube_token.json")):
        say("STEP 6 YouTube upload")
        try:
            import upload as U; info = U.upload_m2(P); say(f"   {info['url'] + ' (' + info['mode'] + ')' if info else 'not uploaded (QC)'}")
        except Exception as e: say(f"   upload ERROR: {str(e)[:200]}")
    shutil.copy(P.p("FINAL.mp4"), os.path.join(HERE, "FINAL_TODAY.mp4"))
    say(f"=== DONE in {(time.time() - T0) / 60:.0f} min ===")


if __name__ == "__main__":
    main()
