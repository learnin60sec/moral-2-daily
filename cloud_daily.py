"""
CLOUD DAILY - runs on GitHub every day, laptop can stay OFF.
 1 story + one-take voice   2 pictures (Cloudflare FLUX, 2nd account when the 1st is used up)
 3 key moments + AI video prompts (Groq vision)   4 Kaggle job: ComfyUI + Wan 2.2 clips   5 video   6 YouTube upload
Settings (env): M2_MINUTES 3 | M2_SECONDS_PER_PICTURE 5 | M2_CLIPS 10 | M2_KAGGLE_MINUTES 240 | M2_AUTO_UPLOAD 1
"""
import os, sys, json, time, glob, shutil, base64, io, subprocess, re, datetime
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
    STYLE = (" Cinematic realistic film footage, natural lifelike motion, soft dramatic light, the same people with exactly the same faces and clothes."
             if m2.REALISTIC else " Premium 2D cartoon style, the same characters with exactly the same faces, clothes and colours.")
    fallback = (moment.rstrip(". ") + ". " if moment else "") + ("The characters make small natural movements, gentle wind moves the grass, "
                "static camera, nothing enters the frame from the edges, nothing covers any face." + STYLE)
    from PIL import Image
    im = Image.open(pic).convert("RGB"); im.thumbnail((768, 768)); b = io.BytesIO(); im.save(b, "JPEG", quality=85)
    img64 = base64.b64encode(b.getvalue()).decode()
    ask = ("You write prompts for the Wan 2.2 image-to-video model. Look at this " + ("cinematic realistic" if m2.REALISTIC else "2D cartoon") +
           " picture; it is the FIRST frame of a 5-second clip. " + ("The mood is suspense and mystery. " if m2.MYSTERY else "") + 
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
    for pre in ("KAGGLE", "KAGGLE2", "KAGGLE3", "KAGGLE4", "KAGGLE5"):
        u, k, t = os.getenv(f"{pre}_USERNAME"), os.getenv(f"{pre}_KEY"), os.getenv(f"{pre}_API_TOKEN")
        if u and (k or t): out.append({"user": u, "key": k, "token": t, "name": pre})
    return out


CLIP_MIN = float(os.getenv("M2_MIN_PER_CLIP", "17.5"))
IMAGE_MODEL = os.getenv("M2_IMAGE_MODEL", "kontext").lower()          # kontext = same characters on every page (slower) | schnell = fast
IMG_MIN = 4.0 if IMAGE_MODEL == "kontext" else 0.6                  # minutes per picture on a Kaggle T4
SETUP_MIN = 25.0 if IMAGE_MODEL == "kontext" else 17.0
SMOOTH = os.getenv("M2_SMOOTH", "1") == "1"; UPSCALE = os.getenv("M2_UPSCALE", "1") == "1"
ENH_MIN = (0.5 if SMOOTH else 0) + (0.8 if UPSCALE else 0)           # RIFE 16->32 fps + cartoon upscaler, per clip
SETUP_MIN += 3 if (SMOOTH or UPSCALE) else 0
PAGE_MIN = CLIP_MIN + IMG_MIN + ENH_MIN
WEEK_BUDGET = float(os.getenv("M2_KAGGLE_WEEKLY_MIN", "1740"))      # 29 of the 30 free hours (1 hour safety)
LEDGER = os.path.join(HERE, "kaggle_usage.json")


def week_start():
    """Kaggle's GPU week (we count from Saturday 00:00 UTC; change with M2_QUOTA_RESET_WEEKDAY, Monday=0 ... Sunday=6)"""
    wd = int(os.getenv("M2_QUOTA_RESET_WEEKDAY", "5"))
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - datetime.timedelta(days=(now.weekday() - wd) % 7)).strftime("%Y-%m-%d")


def ledger():
    try: d = json.load(open(LEDGER))
    except Exception: d = {}
    if d.get("week_start") != week_start(): d = {"week_start": week_start(), "used_min": {}, "full": []}
    return d


def save_ledger(d):
    json.dump(d, open(LEDGER, "w"), indent=1)


def room_today(acc, d):
    """clips this account can still make today: what is left of the week, and what fits in one run"""
    if acc["user"] in d.get("full", []): return 0
    left = WEEK_BUDGET - d["used_min"].get(acc["user"], 0.0) - SETUP_MIN
    per_run = float(os.getenv("M2_KAGGLE_MINUTES", "300")) - SETUP_MIN - 40          # 40 min for Kaggle's queue and slow moments
    return max(0, int(min(left, per_run) // PAGE_MIN))


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


def start_job(acc, P, names, prompts, tag, draw_only=()):
    """upload this run's pictures + prompts as a NEW dataset (unique name -> Kaggle can never use an old one) and start the job"""
    stamp = time.strftime("%Y%m%d-%H%M%S"); job_id = f"{stamp}-{tag.lower()}"
    ds_slug = f"m2-job-{job_id}"; ds_id, k_id = f"{acc['user']}/{ds_slug}", f"{acc['user']}/m2-clips"
    jd = f"/tmp/m2_job_{tag}"; shutil.rmtree(jd, ignore_errors=True); os.makedirs(jd)
    draw = {}
    for n in names:
        src = P.p(m2.pics_dir(P), n)
        if os.path.exists(src): shutil.copy(src, os.path.join(jd, n))
        else: draw[n] = DRAW.get(n, "")
    for n in draw_only: draw[n] = DRAW.get(n, "")                      # picture only, no clip
    size = [int(v) for v in os.getenv("M2_CLIP_SIZE", "832x480").lower().split("x")]
    negative = ("cartoon, anime, 2D, illustration, painting, CGI, plastic skin, waxy face, deformed hands, extra fingers, new people appearing, "
                "objects turning into something else, morphing, distorted face, changing clothes, fast camera shake, text, watermark, flicker, blurry") if m2.REALISTIC else ""
    json.dump({"job_id": job_id, "image_model": IMAGE_MODEL, "cast_prompt": CAST_PROMPT.get("text", ""), "pictures": names, "prompts": {n: prompts[n] for n in names}, "make_pictures": draw, "seconds": 5, "size": size, "negative": negative, "smooth": SMOOTH, "upscale": UPSCALE},
              open(os.path.join(jd, "job.json"), "w"))
    json.dump({"title": ds_slug, "id": ds_id, "licenses": [{"name": "CC0-1.0"}]}, open(os.path.join(jd, "dataset-metadata.json"), "w"))
    kaggle_cli("datasets", "create", "-p", jd, "-r", "zip", acc=acc, check=True)
    for _ in range(45):                                               # wait until Kaggle has processed THIS dataset
        if "ready" in kaggle_cli("datasets", "status", ds_id, acc=acc).stdout.lower(): break
        time.sleep(20)
    kd = f"/tmp/m2_kernel_{tag}"; shutil.rmtree(kd, ignore_errors=True); os.makedirs(kd)
    kern = [k_ for k_ in (os.path.join(_ME, "kaggle_job", "kernel.py"), os.path.join(_ME, "kernel.py"), os.path.join(HERE, "kernel.py")) if os.path.exists(k_)]
    if not kern: raise RuntimeError("kernel.py not found next to cloud_daily.py")
    code = open(kern[0], encoding="utf-8").read().replace('EXPECTED_JOB = None', f'EXPECTED_JOB = "{job_id}"', 1)
    open(os.path.join(kd, "kernel.py"), "w", encoding="utf-8").write(code)
    json.dump({"id": k_id, "title": "m2-clips", "code_file": "kernel.py", "language": "python", "kernel_type": "script", "is_private": True,
               "enable_gpu": True, "enable_internet": True, "dataset_sources": [ds_id], "competition_sources": [], "kernel_sources": []},
              open(os.path.join(kd, "kernel-metadata.json"), "w"))
    kaggle_cli("kernels", "push", "-p", kd, acc=acc, check=True)
    JOB_IDS[k_id + acc["name"]] = job_id
    return k_id


JOB_IDS = {}

DRAW = {}
CAST_PROMPT = {}


def cast_prompt(st):
    """one picture with every main character side by side - the reference FLUX Kontext keeps on every page"""
    looks = st.get("characters", {})
    people = "; ".join(f"{n}: {l}" for n, l in list(looks.items())[:5]) or "the main character"
    return (f"Character reference sheet for one story. These characters, each drawn ONCE: {people}. All of them standing side by side in one row, "
            "full body, front view, friendly calm faces, clearly separated, on a plain soft light-coloured background with nothing else. "
            + (m2.STYLE_REAL if m2.REALISTIC else m2.STYLE_FULL))


def kaggle_clips(P, st, pages):
    CAST_PROMPT["text"] = cast_prompt(st)
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
            prompts[name], who = (moment.rstrip(". ") + ". " if moment else "") + ("The characters make small natural movements, gentle wind moves the grass, " +
                                  ("slow cinematic camera push-in, nothing enters the frame from the edges, nothing covers any face. Cinematic realistic film footage, natural "
                                  "lifelike motion, the same people with exactly the same faces and clothes." if m2.REALISTIC else
                                  "static camera, nothing enters the frame from the edges, nothing covers any face. Premium 2D cartoon style, the same "
                                  "characters with exactly the same faces, clothes and colours.")), "story text (picture drawn on Kaggle)"
        say(f"   prompt {name} (written by {who}): {prompts[name][:110]}...")
    if DRAW: say(f"   {len(DRAW)} pictures will be drawn on Kaggle with ComfyUI (FLUX)")
    names = sorted(prompts); jobs = []
    led = ledger(); room = {a["name"]: room_today(a, led) for a in accs}
    for n, a in enumerate(accs):
        say(f"   account {n + 1}: {led['used_min'].get(a['user'], 0) / 60:.1f} h used this Kaggle week -> room for {room[a['name']]} clips today")
    share = {a["name"]: [] for a in accs}; draw_only = {a["name"]: [] for a in accs}
    pending = list(names)
    week_left = {a["name"]: WEEK_BUDGET - led["used_min"].get(a["user"], 0.0) - SETUP_MIN for a in accs}
    while pending:                       # one page at a time to the account with the MOST WEEKLY TIME LEFT (fresh accounts work more, tired ones less)
        open_ = [a for a in accs if len(share[a["name"]]) < room[a["name"]]]
        if not open_: break
        a = max(open_, key=lambda x: week_left[x["name"]] - len(share[x["name"]]) * PAGE_MIN); share[a["name"]].append(pending.pop(0))
    if pending:
        say(f"   no Kaggle time left for {len(pending)} pages -> they stay living pictures (their pictures are still drawn where time allows)")
        spare = {a["name"]: max(0.0, (room[a["name"]] - len(share[a["name"]])) * PAGE_MIN + PAGE_MIN * 0.9) for a in accs}
        for n_ in [x for x in pending if x in DRAW]:
            a = max(accs, key=lambda x: spare[x["name"]])
            if spare[a["name"]] < IMG_MIN: break
            draw_only[a["name"]].append(n_); spare[a["name"]] -= IMG_MIN
    for n, acc in enumerate(accs):
        mine, extra = share[acc["name"]], draw_only[acc["name"]]
        if not mine and not extra: continue
        try:
            jobs.append((acc, start_job(acc, P, mine, prompts, acc["name"], extra), mine))
            say(f"   Kaggle job started on account {n + 1} ({acc['user']}): {len(mine)} clips" + (f" + {len(extra)} pictures only" if extra else "")
                + f", pictures by {IMAGE_MODEL}, about {int(len(mine) * PAGE_MIN + len(extra) * IMG_MIN + SETUP_MIN)} min")
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
        if "quota" in stt.lower():
            led = ledger(); led.setdefault("full", []).append(acc["user"]); save_ledger(led); say(f"   account {n_acc}: weekly GPU quota used up")
        od = f"/tmp/m2_out_{acc['name']}"; shutil.rmtree(od, ignore_errors=True); os.makedirs(od)
        try: kaggle_cli("kernels", "output", k_id, "-p", od, acc=acc)          # also after an error: whatever was made is used
        except Exception as e: say(f"   account {n_acc}: could not download the results ({str(e)[:120]})"); continue
        import zipfile
        for zf in glob.glob(os.path.join(od, "**", "results.zip"), recursive=True):
            with zipfile.ZipFile(zf) as z: z.extractall(os.path.join(od, "results"))
        rep = glob.glob(os.path.join(od, "**", "report.json"), recursive=True)
        want = JOB_IDS.get(k_id + acc["name"])
        if rep and want and json.load(open(rep[0])).get("job_id") != want:
            say(f"   account {n_acc}: results belong to an OLD job ({json.load(open(rep[0])).get('job_id')}) - NOT used"); continue
        if not rep:
            say(f"   account {n_acc}: no job report -> results not trusted, NOT used"); continue
        if rep:
            r_ = json.load(open(rep[0]))
            led = ledger(); led["used_min"][acc["user"]] = round(led["used_min"].get(acc["user"], 0.0) + float(r_.get("minutes") or 0), 1); save_ledger(led)
            say(f"   account {n_acc} report: pictures {len(r_.get('pictures_made', []))}/{len(r_.get('pictures_asked', []))}, "
                f"clips {len(r_.get('clips_made', []))}/{len(r_.get('clips_asked', []))}, {r_.get('minutes')} min on Kaggle, "
                f"smooth 32 fps: {'yes' if r_.get('smooth_rife') else 'no'}, sharper clips: {r_.get('upscaled', 0)}")
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
        for f in glob.glob(os.path.join(od, "results", "*.mp4")):
            name = os.path.basename(f).split("__")[0]
            if re.fullmatch(r"\d{3}\.mp4", name): shutil.copy(f, P.p("clips", name)); got += 1
        for f in glob.glob(os.path.join(od, "results", "*.png")):              # pictures drawn on Kaggle (this job only)
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
    accs_ = kaggle_accounts()
    if accs_ and k == 0 and os.getenv("M2_FIT_TO_KAGGLE", "1") == "1":   # every page MUST become a clip -> the story only as long as Kaggle can animate today
        led_ = ledger(); can = sum(room_today(a, led_) for a in accs_)
        sec_pic = float(os.getenv("M2_SECONDS_PER_PICTURE", "6")); fit = round(can * sec_pic / 60 * 0.9, 1)
        say(f"   Kaggle can animate {can} pages today -> up to {fit} min with a moving clip on EVERY page")
        if fit < minutes:
            if fit < 1.0: say("STOP: not enough Kaggle time left this week for a full-clip video - the week resets on Saturday"); sys.exit(1)
            say(f"   video shortened from {minutes} to {fit} min so no page is left without a clip"); minutes = fit
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
    if os.getenv("GITHUB_EVENT_NAME", "schedule") == "schedule":      # only the automatic 2D run counts as "today's video is done"
        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        open(os.path.join(HERE, "last_done.txt"), "w").write(datetime.datetime.now(ist).strftime("%Y-%m-%d"))
    say(f"=== DONE in {(time.time() - T0) / 60:.0f} min ===")


if __name__ == "__main__":
    main()
