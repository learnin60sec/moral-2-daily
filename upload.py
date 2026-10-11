"""
YOUTUBE UPLOAD for Moral Story Studio (YouTube Data API v3, your own channel).
  python upload.py login            one time: browser opens -> choose the NEW channel -> allow  (saves youtube_token.json)
  python upload.py <project folder>  upload that project's FINAL.mp4 (title, description, tags, thumbnail made by itself)
Needs client_secret.json in this folder (Google Cloud -> APIs & Services -> Credentials -> OAuth client ID -> Desktop app;
YouTube Data API v3 enabled). The same client_secret.json as the 60-second channel can be used.
Settings (setx):  STUDIO_UPLOAD = schedule (default) | public | private
                  STUDIO_AUDIENCE = family (default) | kids
                  STUDIO_TIMES = "10:00,18:00"   (IST, used by schedule: 1st video of the day, 2nd video ...)
"""
import os, sys, json, glob, datetime, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN, SECRET = os.path.join(HERE, "youtube_token.json"), os.path.join(HERE, "client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]


def need(pkg, mod):
    try:
        __import__(mod)
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)


def credentials():
    need("google-auth-oauthlib", "google_auth_oauthlib"); need("google-api-python-client", "googleapiclient")
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if os.getenv("YT_TOKEN_JSON") and not os.path.exists(TOKEN):          # GitHub: token comes from a secret
        open(TOKEN, "w").write(os.getenv("YT_TOKEN_JSON"))
    if not os.path.exists(TOKEN):
        sys.exit("Not logged in to YouTube yet. Run:  python upload.py login")
    c = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not c.valid:
        c.refresh(Request()); open(TOKEN, "w").write(c.to_json())
    return c


def login():
    need("google-auth-oauthlib", "google_auth_oauthlib")
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not os.path.exists(SECRET):
        sys.exit("client_secret.json not found in this folder (see the top of upload.py).")
    c = InstalledAppFlow.from_client_secrets_file(SECRET, SCOPES).run_local_server(port=0, prompt="consent")
    open(TOKEN, "w").write(c.to_json())
    print("Logged in. Saved youtube_token.json  (for GitHub: put its whole text in the secret YT_TOKEN_JSON)")


def publish_time(slot):
    """schedule: today's slot time in IST; if it has passed, tomorrow. Returns RFC3339 UTC."""
    times = [t.strip() for t in os.getenv("STUDIO_TIMES", "10:00,18:00").split(",") if t.strip()]
    hh, mm = map(int, times[min(slot, len(times) - 1)].split(":"))
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30)); now = datetime.datetime.now(ist)
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if t < now + datetime.timedelta(minutes=20): t += datetime.timedelta(days=1)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def metadata(P):
    """title, description, tags from the story (AI if available, otherwise simple)"""
    sys.path.insert(0, HERE)
    import studio as S
    story, chosen = P.load("story.json") or {}, P.load("chosen.json") or {}
    title = story.get("title") or chosen.get("title") or "Hindi Moral Story"
    moral = story.get("moral") or chosen.get("moral", "")
    text = None
    try:
        text = S.ask(f"""Write YouTube text for a 5-minute Hindi 2D cartoon moral story video. Story title: "{title}". Moral: "{moral}".
Summary: {json.dumps([s.get('summary', '') for s in story.get('scenes', [])], ensure_ascii=False)[:1500]}
JSON only: {{"title": "Hindi title under 70 characters, curious but honest, may end with | Hindi Kahani",
"description": "Hindi, 5-7 lines: hook question, short summary without the ending, the moral, a line asking to subscribe",
"tags": ["15 tags in Hindi and Hinglish"], "thumbnail_text": "2-4 Hindi words"}}""")
    except SystemExit:
        pass
    text = text if isinstance(text, dict) else {}
    return {"title": (text.get("title") or f"{title} | Hindi Kahani")[:95],
            "description": (text.get("description") or f"{title}\nसीख: {moral}") + "\n\n#HindiKahani #MoralStory #कहानी\n(AI से बनाई गई एनिमेटेड कहानी)",
            "tags": [str(t) for t in (text.get("tags") or ["hindi kahani", "moral story", "हिंदी कहानी"])][:20],
            "thumb": text.get("thumbnail_text") or title[:20]}


def thumbnail(P, words):
    """the most colourful scene picture + big Hindi words (drawn by ffmpeg/libass so Hindi joins correctly)"""
    import numpy as np
    from PIL import Image
    pics = sorted(glob.glob(P.p("images", "*.png")))
    pics = [p for p in pics if "_f" not in os.path.basename(p)]
    if not pics: return None
    best = max(pics[:20], key=lambda p: float(np.asarray(Image.open(p).convert("HSV").resize((64, 36)))[..., 1].mean()))
    sys.path.insert(0, HERE); import studio as S
    font = "Nirmala UI" if os.name == "nt" else "Noto Sans Devanagari"
    fontsdir = "C:/Windows/Fonts" if os.name == "nt" else "/usr/share/fonts/truetype/noto"
    ass = P.p("work", "thumb.ass")
    open(ass, "w", encoding="utf-8").write("\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1280", "PlayResY: 720", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
        f"Style: T,{font},96,&H0000FFFF,&H00000000,&H00000000,1,1,8,4,2,40,40,40", "", "[Events]",
        "Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Text", f"Dialogue: 0,0:00:00.00,0:00:05.00,T,0,0,0,{words}"]))
    out = P.p("thumbnail.jpg"); esc = lambda p: p.replace("\\", "/").replace(":", "\\:")
    r = subprocess.run([S.ffmpeg(), "-y", "-v", "error", "-loop", "1", "-i", best, "-vf",
                        f"scale=1280:720,ass='{esc(ass)}':fontsdir='{esc(fontsdir)}':shaping=complex", "-frames:v", "1", out], capture_output=True)
    return out if r.returncode == 0 and os.path.exists(out) else None


def upload(folder, slot=0):
    sys.path.insert(0, HERE); import studio as S
    P = S.Project(folder); video = P.p("FINAL.mp4")
    if not os.path.exists(video): sys.exit("FINAL.mp4 not found")
    qc = open(P.p("QC_REPORT.txt"), encoding="utf-8").read() if os.path.exists(P.p("QC_REPORT.txt")) else ""
    if "CORRECTED & COMPLETE" not in qc and os.getenv("STUDIO_UPLOAD_IF", "complete") == "complete":
        print("NOT uploaded: QC_REPORT is not 'CORRECTED & COMPLETE'. Fix it (CHECK_VIDEO.bat) or setx STUDIO_UPLOAD_IF any"); return None
    if os.path.exists(P.p("UPLOADED.json")):
        print("Already uploaded:", P.load("UPLOADED.json")); return P.load("UPLOADED.json")
    m = metadata(P); mode = os.getenv("STUDIO_UPLOAD", "schedule").lower()
    status = {"privacyStatus": "private" if mode in ("private", "schedule") else "public",
              "selfDeclaredMadeForKids": os.getenv("STUDIO_AUDIENCE", "family").lower() == "kids",
              "containsSyntheticMedia": True}
    if mode == "schedule": status["publishAt"] = publish_time(slot)
    body = {"snippet": {"title": m["title"], "description": m["description"], "tags": m["tags"], "categoryId": "1",
                        "defaultLanguage": "hi", "defaultAudioLanguage": "hi"}, "status": status}
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=credentials())
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(video, chunksize=8 * 1024 * 1024, resumable=True))
    res = None
    while res is None:
        st, res = req.next_chunk()
        if st: print(f"  uploading {int(st.progress() * 100)}%")
    vid = res["id"]; print(f"UPLOADED: https://youtu.be/{vid}  ({mode}{' at ' + status['publishAt'] if 'publishAt' in status else ''})")
    th = thumbnail(P, m["thumb"])
    if th:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th)).execute(); print("  thumbnail set")
        except Exception as e:
            print("  (thumbnail not set - verify the channel with your phone number in YouTube to allow custom thumbnails)", str(e)[:80])
    info = {"id": vid, "url": f"https://youtu.be/{vid}", "title": m["title"], "mode": mode, "publishAt": status.get("publishAt")}
    P.save("UPLOADED.json", info); return info


def upload_m2(P, slot=0):
    """Moral 2: title/description from story.json, thumbnail = main character picture + title, AI-made flag, schedule/public/private"""
    video = P.p("FINAL.mp4")
    if not os.path.exists(video): sys.exit("FINAL.mp4 not found")
    qc = open(P.p("QC_REPORT.txt"), encoding="utf-8").read() if os.path.exists(P.p("QC_REPORT.txt")) else ""
    if "CORRECTED & COMPLETE" not in qc and os.getenv("STUDIO_UPLOAD_IF", "complete") == "complete":
        print("NOT uploaded: QC_REPORT is not 'CORRECTED & COMPLETE' (setx STUDIO_UPLOAD_IF any to upload anyway)"); return None
    if os.path.exists(P.p("UPLOADED.json")): return P.load("UPLOADED.json")
    st = P.load("story.json"); sys.path.insert(0, HERE); import studio as S
    text = None
    try:
        text = S.ask(f"""Write YouTube text for a Hindi 2D cartoon moral story video. Title: "{st.get('title', '')}". Moral: "{st.get('moral', '')}".
Story start: {' '.join(b['narration'] for b in st.get('beats', [])[:3])[:900]}
JSON only: {{"title": "Hindi title under 70 characters, curious but honest, ending with | Hindi Kahani", "description": "Hindi, 5-7 lines:
hook question, short summary without the ending, the moral, ask to subscribe", "tags": ["15 tags Hindi and Hinglish"], "thumbnail_text": "2-4 Hindi words"}}""")
    except SystemExit:
        pass
    text = text if isinstance(text, dict) else {}
    m = {"title": (text.get("title") or f"{st.get('title', '')} | Hindi Kahani")[:95],
         "description": (text.get("description") or f"{st.get('title', '')}\nसीख: {st.get('moral', '')}") + "\n\n#HindiKahani #MoralStory #कहानी\n(AI की मदद से बनाई गई एनिमेटेड कहानी)",
         "tags": [str(t) for t in (text.get("tags") or ["hindi kahani", "moral story"])][:20], "thumb": text.get("thumbnail_text") or st.get("title", "")[:20]}
    mode = os.getenv("STUDIO_UPLOAD", "schedule").lower()
    status = {"privacyStatus": "private" if mode in ("private", "schedule") else "public",
              "selfDeclaredMadeForKids": os.getenv("STUDIO_AUDIENCE", "family").lower() == "kids", "containsSyntheticMedia": True}
    if mode == "schedule": status["publishAt"] = publish_time(slot)
    body = {"snippet": {"title": m["title"], "description": m["description"], "tags": m["tags"], "categoryId": "1",
                        "defaultLanguage": "hi", "defaultAudioLanguage": "hi"}, "status": status}
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=credentials())
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(video, chunksize=8 * 1024 * 1024, resumable=True))
    res = None
    while res is None:
        stt, res = req.next_chunk()
        if stt: print(f"  uploading {int(stt.progress() * 100)}%")
    vid = res["id"]
    import glob as _g
    pics = sorted(_g.glob(os.path.join(P.dir, "pictures*", "*.png")))
    if pics:
        os.makedirs(P.p("work"), exist_ok=True); os.makedirs(P.p("images"), exist_ok=True)
        import shutil as _sh; _sh.copy(pics[0], P.p("images", "001.png"))
        th = thumbnail(P, m["thumb"])
        if th:
            try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th)).execute()
            except Exception as e: print("  (thumbnail not set - verify the channel with a phone number)", str(e)[:60])
    info = {"id": vid, "url": f"https://youtu.be/{vid}", "title": m["title"], "mode": mode, "publishAt": status.get("publishAt")}
    P.save("UPLOADED.json", info); return info


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    login() if sys.argv[1] == "login" else upload(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
