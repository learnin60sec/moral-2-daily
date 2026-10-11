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
    """bytes of one picture, 'LIMIT' when this account's free daily amount is used up, None on other errors"""
    r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc[0]}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                      headers={"Authorization": f"Bearer {acc[1]}"}, json={"prompt": prompt, "steps": 8}, timeout=180)
    if r.headers.get("content-type", "").startswith("image/"): return r.content
    try: j = r.json()
    except Exception: return None
    if r.status_code == 200 and j.get("result", {}).get("image"): return base64.b64decode(j["result"]["image"])
    text = json.dumps(j.get("errors", j))[:300]
    if r.status_code == 429 or "4006" in text or "neurons" in text.lower(): return "LIMIT"
    say(f"   picture error {r.status_code}: {text[:150]}"); return None


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
            if res == "LIMIT":
                ai += 1
                if ai >= len(accs): say(f"   Cloudflare free amount used up at picture {i} - the video uses {made} pictures"); return made
                say("   account 1 used up -> account 2"); continue
            if res: S.clean_frame(res, out); made += 1; break
            time.sleep(3)
        if i % 10 == 0: say(f"   pictures {i}/{len(st['pictures'])}")
    return made


# ---------------------------------------------------------------- 3) key moments + AI prompts
def key_pages(P, st, k):
    have = [i for i in range(1, len(st["pictures"]) + 1) if os.path.exists(P.p(m2.pics_dir(P), f"{i:03d}.png"))]
    if k <= 0: return have                                            # M2_CLIPS=all -> EVERY picture becomes a moving clip
    first = []
    for bi in range(len(st["beats"])):
        mine = [i for i in have if st["pictures"][i - 1]["beat"] == bi]
        if mine: first.append(mine[len(mine) // 2])                  # the middle moment of every part
    if len(first) > k: first = [first[round(j * (len(first) - 1) / (k - 1))] for j in range(k)] if k > 1 else first[:1]
    return sorted(set(first))


def ai_prompt(pic, moment):
    key = os.getenv("GROQ_API_KEY")
    STYLE = " Premium 2D cartoon style, the same characters with exactly the same faces, clothes and colours."
    fallback = (moment + ". " if moment else "") + "Small natural calm movements, gentle wind in the trees, slow steady camera. Nothing new appears." + STYLE
    if not key: return fallback
    from PIL import Image
    im = Image.open(pic).convert("RGB"); im.thumbnail((768, 768)); b = io.BytesIO(); im.save(b, "JPEG", quality=85)
    ask = ("You write prompts for the Wan 2.2 image-to-video model. Look at this 2D cartoon picture (the FIRST frame of a 5-second clip). "
           "Write ONE English prompt of 60-90 words: name what is in the picture (people, animals, objects, place, light) and give each "
           "of them a small, natural, calm movement that fits the picture" + (f" and this story moment: {moment}" if moment else "") + ". "
           "Camera: static or a very slow push-in. Keep every face, body and clothes exactly the same. Nothing new appears, nothing "
           "flies or passes in front of the camera, nobody turns into something else. Return only the prompt text.")
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=60,
                          json={"model": "meta-llama/llama-4-scout-17b-16e-instruct", "temperature": 0.3, "messages": [{"role": "user", "content": [
                              {"type": "text", "text": ask}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()}}]}]})
        if r.status_code == 200:
            t = r.json()["choices"][0]["message"]["content"].strip().strip('"')
            if 30 < len(t) < 1500: return t + STYLE
    except Exception:
        pass
    return fallback


# ---------------------------------------------------------------- 4) Kaggle job
def kaggle_cli(*args, check=False):
    r = subprocess.run(["kaggle"] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0: raise RuntimeError(f"kaggle {' '.join(args)}: {r.stdout[-300:]} {r.stderr[-300:]}")
    return r


def kaggle_clips(P, st, pages):
    user = os.getenv("KAGGLE_USERNAME")
    if not user or not (os.getenv("KAGGLE_KEY") or os.getenv("KAGGLE_API_TOKEN")): say("no Kaggle keys -> video without AI clips"); return 0
    ds_id, k_id = f"{user}/m2-clips-job", f"{user}/m2-clips"
    jd = "/tmp/m2_job"; shutil.rmtree(jd, ignore_errors=True); os.makedirs(jd)
    prompts = {}
    for i in pages:
        name = f"{i:03d}.png"; src = P.p(m2.pics_dir(P), name); shutil.copy(src, os.path.join(jd, name))
        prompts[name] = ai_prompt(src, st["pictures"][i - 1].get("action", ""))
        say(f"   prompt {name}: {prompts[name][:90]}...")
    json.dump({"pictures": sorted(prompts), "prompts": prompts, "seconds": 5}, open(os.path.join(jd, "job.json"), "w"))
    json.dump({"title": "m2-clips-job", "id": ds_id, "licenses": [{"name": "CC0-1.0"}]}, open(os.path.join(jd, "dataset-metadata.json"), "w"))
    r = kaggle_cli("datasets", "version", "-p", jd, "-m", time.strftime("%Y-%m-%d %H:%M"), "-r", "zip")
    if r.returncode != 0: kaggle_cli("datasets", "create", "-p", jd, "-r", "zip", check=True)
    for _ in range(30):                                               # wait until Kaggle has processed the new pictures
        if "ready" in kaggle_cli("datasets", "status", ds_id).stdout.lower(): break
        time.sleep(20)
    kd = "/tmp/m2_kernel"; shutil.rmtree(kd, ignore_errors=True); os.makedirs(kd)
    kern = [k_ for k_ in (os.path.join(_ME, "kaggle_job", "kernel.py"), os.path.join(_ME, "kernel.py"), os.path.join(HERE, "kernel.py")) if os.path.exists(k_)]
    if not kern: raise RuntimeError("kernel.py not found next to cloud_daily.py")
    shutil.copy(kern[0], os.path.join(kd, "kernel.py"))
    json.dump({"id": k_id, "title": "m2-clips", "code_file": "kernel.py", "language": "python", "kernel_type": "script", "is_private": True,
               "enable_gpu": True, "enable_internet": True, "dataset_sources": [ds_id], "competition_sources": [], "kernel_sources": []},
              open(os.path.join(kd, "kernel-metadata.json"), "w"))
    kaggle_cli("kernels", "push", "-p", kd, check=True); say(f"   Kaggle job started ({len(pages)} clips on 2 GPUs, about {len(pages) * 9 // 2 + 20} min)")
    limit = time.time() + 60 * float(os.getenv("M2_KAGGLE_MINUTES", "300"))
    status = ""
    while time.time() < limit:
        time.sleep(60)
        status = kaggle_cli("kernels", "status", k_id).stdout.lower()
        if "complete" in status or "error" in status or "cancel" in status: break
        if int(time.time() - T0) % 900 < 60: say(f"   Kaggle still working ... {status.strip()[-40:]}")
    if "complete" not in status: say(f"   Kaggle job did not finish ({status.strip()[-60:]}) -> video without AI clips"); return 0
    od = "/tmp/m2_out"; shutil.rmtree(od, ignore_errors=True); os.makedirs(od)
    kaggle_cli("kernels", "output", k_id, "-p", od)
    os.makedirs(P.p("clips"), exist_ok=True); got = 0
    for f in glob.glob(os.path.join(od, "**", "*.mp4"), recursive=True):
        name = os.path.basename(f).split("__")[0]
        if re.fullmatch(r"\d{3}\.mp4", name): shutil.copy(f, P.p("clips", name)); got += 1
    say(f"   {got} AI clips received"); return got


# ---------------------------------------------------------------- the day
def main():
    minutes = float(os.getenv("M2_MINUTES", "3")); kc = os.getenv("M2_CLIPS", "all").lower()
    k = 0 if kc in ("all", "0", "") else int(kc)
    say(f"=== CLOUD DAILY: {minutes:.0f}-min video, AI clips: {'ALL pictures' if k == 0 else k} ===")
    say("STEP 1 story + voice"); P = m2.story(minutes); st = P.load("story.json")
    say(f"   {st.get('title', '')}: {len(st['pictures'])} pictures needed")
    say("STEP 2 pictures (Cloudflare)"); made = make_pictures(P, st); say(f"   {made} pictures made")
    if made < len(st["pictures"]) * 0.5: say("STOP: too few pictures today (Cloudflare limit?) - try again tomorrow"); sys.exit(1)
    say("STEP 3+4 key moments -> Kaggle clips")
    try: kaggle_clips(P, st, key_pages(P, st, k))
    except Exception as e: say(f"   Kaggle step failed ({str(e)[:200]}) -> video without AI clips")
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
