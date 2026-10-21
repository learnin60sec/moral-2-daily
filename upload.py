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
                        "defaultLanguage": "en", "defaultAudioLanguage": "hi"}, "status": status}
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
    try:
        lists = add_to_playlists(yt, vid, st); print("  playlists:", ", ".join(lists))
    except Exception as e:
        lists = []; print("  (playlists not updated:", str(e)[:120], ")")
    info = {"id": vid, "url": f"https://youtu.be/{vid}", "title": m["title"], "style": m.get("style", ""), "mode": mode, "publishAt": status.get("publishAt"), "playlists": lists}
    P.save("UPLOADED.json", info); return info


import re
_DEV = None


def _en(text):
    """English letters only: every Hindi (Devanagari) letter is removed, and the punctuation that is left over at the start or end is cleaned"""
    import re
    t = re.sub(r"\s+", " ", re.sub("[\u0900-\u097F]+", "", str(text or ""))).strip()
    t = re.sub(r"^[\s:;,.\-\u2013\u2014|?!/]+", "", t)
    return t.strip()


def fit_tags(tags, limit=450):
    """tags the way YouTube counts them: a tag that contains a space is counted WITH quotes (+2), every tag +1 for its comma; the total must stay under 500.
    No < > or quotes inside a tag, at most 80 characters each, no duplicates; the order is kept (the first tags matter most)"""
    out, seen, total = [], set(), 0
    for t in tags or []:
        t = re.sub(r'[<>"]', "", str(t)).strip()[:80].strip()
        if len(t) < 2 or t.lower() in seen: continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if total + cost > limit: continue
        out.append(t); seen.add(t.lower()); total += cost
    return out


def _insert_safely(yt, body, media_path, label="video"):
    """upload; if YouTube rejects the keywords (HTTP 400 'invalid video keywords') the SAME upload is repeated with fewer tags and then with none -
    a video must never be lost because of its tags"""
    from googleapiclient.http import MediaFileUpload
    try: from googleapiclient.errors import HttpError
    except Exception: HttpError = Exception
    all_tags = list(body["snippet"].get("tags") or []); tries = (all_tags, fit_tags(all_tags, 250)[:10], [])
    for attempt, tags in enumerate(tries):
        body["snippet"]["tags"] = tags
        try:
            req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(media_path, chunksize=8 * 1024 * 1024, resumable=True))
            res = None
            while res is None:
                stt, res = req.next_chunk()
                if stt: print(f"  uploading the {label} {int(stt.progress() * 100)}%")
            return res
        except HttpError as e:
            msg = str(e).lower()
            if attempt < len(tries) - 1 and ("keyword" in msg or "invalidtags" in msg or "tags" in msg):
                print(f"  YouTube did not accept the tags ({str(e)[:90].strip()}) - trying again with {'fewer' if attempt == 0 else 'no'} tags"); continue
            raise


def english_metadata(P, st):
    """YouTube title, description, tags and thumbnail words - ALL English, written to make people click (curiosity, never the answer)"""
    sys.path.insert(0, HERE); import studio as S
    try:
        import m2 as _m2; mystery, real = _m2.MYSTERY, _m2.REALISTIC
    except Exception:
        mystery, real = True, False
    kind = "Hindi Mystery Story" if mystery else "Hindi Moral Story"
    style = os.getenv("M2_TITLE_STYLE", "auto").lower()                # the title test: English on one day, Hinglish on the next (compare CTR in Studio later)
    if style not in ("english", "hinglish"): style = "hinglish" if datetime.date.today().toordinal() % 2 else "english"
    phrase = _en(st.get("search_phrase"))
    start = " ".join(b.get("narration", "") for b in st.get("beats", [])[:4])[:1100]
    prompt = f"""You are the best YouTube growth strategist for an animated {'cinematic ' if real else '2D cartoon '}{kind} channel called "The Moral Story Club" (stories are narrated in Hindi with Hindi subtitles, for the whole family).
Write the ENGLISH YouTube text for this video so that people see the thumbnail and the title and MUST click.
Story title (Hindi): {st.get('title', '')}
Moral (Hindi): {st.get('moral', '')}
The video opens with this hook (Hindi): {st.get('hook', '')}
Story start (Hindi): {start}
RULES
{("TITLE: ENGLISH words only, at most 68 characters. Open a curiosity gap about the strangest moment or the central question. NEVER reveal the answer or the ending. Put the most intriguing words in the first 40 characters. Strong simple words, optionally ONE emoji (😱 🔍 😮). No lies, no ALL-CAPS sentence (one word may be capitalised). Finish with ' | " + kind + "' only if the whole title still fits in 68 characters.") if style == "english" else
 ("TITLE: HINGLISH = Hindi words written in English letters, the way Hindi-speaking families type and say them (for example 'Raat Ko Ghanti Kisne Bajayi?'), at most 68 characters. Open a curiosity gap, NEVER reveal the answer. The most intriguing words in the first 40 characters, optionally ONE emoji, no ALL-CAPS sentence. " + ("Use the words of this real search naturally: " + phrase + ". " if phrase else "") + "Finish with ' | Hindi Kahani' only if it still fits in 68 characters.")}
DESCRIPTION: English only. Line 1 = the hook question (the first 100 characters decide the click). Then 3-4 lines: the setup WITHOUT the answer, a challenge ("Can you solve it before the end? Write your guess in the comments!"), one line "Narrated in Hindi with Hindi subtitles - a story for the whole family.", a subscribe line ("Subscribe to The Moral Story Club and press the bell - a new story every day at 6 PM IST."), then one line "This story was made with the help of AI.", then 5 English hashtags.
TAGS: 20 English tags, from broad to specific (hindi stories, hindi mystery story, animated story in hindi, village mystery, bedtime story, ... plus words from this story).
THUMBNAIL_TEXT: {"2-4 English words, ALL CAPS, at most 22 characters, creates curiosity, never the answer (for example WHO RANG THE BELL?)." if style == "english" else "2-4 HINGLISH words in English letters, ALL CAPS, at most 22 characters, creates curiosity, never the answer (for example KISNE BAJAYI GHANTI?)."}
JSON only: {{"title": "...", "description": "...", "tags": ["..."], "thumbnail_text": "..."}}"""
    d = None
    try: d = S.ask_writer(prompt, temperature=0.8, check=lambda x: isinstance(x, dict) and len(_en(x.get("title"))) >= 12 and len(_en(x.get("description"))) >= 80)
    except SystemExit: d = None
    d = d if isinstance(d, dict) else {}
    fb_title = "A Midnight Mystery Nobody Could Explain 😱" if mystery else "A Village Story That Will Touch Your Heart"
    title = _en(d.get("title")).strip(' "') or fb_title
    if len(title) > 68: title = title[:68].rsplit(" ", 1)[0]
    suffix = kind if style == "english" else "Hindi Kahani"
    if suffix.lower() not in title.lower() and len(title) + len(suffix) + 3 <= 68: title = f"{title} | {suffix}"
    desc = str(d.get("description") or "")
    desc = "\n".join(l for l in (_en(l) for l in desc.splitlines()) if re.search("[A-Za-z0-9]", l)).strip() or ("Can you solve this mystery before the end? Write your guess in the comments!\nNarrated in Hindi with Hindi subtitles - a story for the whole family.\n"
                                                                     "Subscribe to The Moral Story Club and press the bell - a new story every day at 6 PM IST.")
    if "made with the help of AI" not in desc: desc += "\n\nThis story was made with the help of AI."
    if "#" not in desc: desc += "\n#HindiStories #MysteryStory #AnimatedStory #BedtimeStory #StoriesForKids"
    tags = [t for t in (_en(x) for x in (d.get("tags") or [])) if t][:25] or ["hindi stories", "hindi mystery story", "animated story in hindi", "bedtime story", "moral story"]
    hinglish = (["hindi kahani", "hindi kahaniya", "rahasya kahani", "jasoosi kahani", "mystery story in hindi", "hindi cartoon story", "cartoon kahani", "village mystery story hindi", "kids story in hindi", "bedtime story in hindi"]
                if mystery else ["hindi kahani", "hindi kahaniya", "moral story in hindi", "naitik kahani", "hindi cartoon story", "cartoon kahani", "kids story in hindi", "bedtime story in hindi"])
    tags = fit_tags(hinglish + tags)                                   # Hindi-speaking viewers type these Latin-letter words; counted the way YouTube counts
    keywords = "Hindi Kahani | Rahasya Kahani | Mystery Story in Hindi | Cartoon Kahani" if mystery else "Hindi Kahani | Moral Story in Hindi | Cartoon Kahani | Kids Story in Hindi"
    body_lines = [l for l in desc.splitlines() if not re.fullmatch(r"(#\w+\s*)+", l.strip())]
    desc = "\n".join(body_lines).strip()
    if "made with the help of AI" not in desc: desc += "\n\nThis story was made with the help of AI."
    desc += "\n\n" + keywords + "\n\n" + "#HindiKahani #MysteryStory #HindiStories #AnimatedStory #BedtimeStory" if mystery else "\n\n" + keywords + "\n\n" + "#HindiKahani #MoralStory #HindiStories #AnimatedStory #BedtimeStory"
    thumb = _en(d.get("thumbnail_text")).upper().strip(' "') or ("CAN YOU SOLVE IT?" if mystery else "WATCH TILL THE END")
    return {"title": title, "description": desc[:4900], "tags": tags, "thumb": thumb[:28], "kind": kind, "style": style}


def thumbnail_en(P, st, text, kind="Hindi Mystery Story"):
    """1280x720 thumbnail: the strongest moment (the hook picture), richer colours, a dark side for the words, HUGE outlined English words, a red series tag, the channel logo"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
    pics = sorted(glob.glob(os.path.join(P.dir, "pictures*", "*.png")))
    if not pics: return None
    path = pics[0]
    try:
        hp = st.get("hook_part", 0); idx = [i for i, p in enumerate(st.get("pictures", []), 1) if p.get("beat") == hp]
        cand = [x for x in pics if os.path.basename(x) == f"{idx[0]:03d}.png"] if idx else []
        path = cand[0] if cand else max(pics[:max(3, len(pics) // 2)], key=lambda q: float(np.asarray(Image.open(q).convert("HSV").resize((64, 36)))[..., 1].mean()))
    except Exception: pass
    im = Image.open(path).convert("RGB"); w, h = im.size; tw, th_ = (w, int(w * 9 / 16)) if w / h < 16 / 9 else (int(h * 16 / 9), h)
    im = im.crop(((w - tw) // 2, (h - th_) // 2, (w - tw) // 2 + tw, (h - th_) // 2 + th_)).resize((1280, 720), Image.LANCZOS)
    im = ImageEnhance.Sharpness(ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.28)).enhance(1.12)).enhance(1.35)
    sh = np.zeros((720, 1280), np.float32)                                   # dark gradient from the left (for the words) and a soft vignette
    xs = np.linspace(0, 1, 1280)[None, :]; sh += np.clip(1.0 - xs / 0.62, 0, 1) * 0.72
    ys = np.linspace(0, 1, 720)[:, None]; sh += np.clip((ys - 0.7) / 0.3, 0, 1) * 0.35
    arr = np.asarray(im).astype(np.float32) * (1 - np.clip(sh, 0, 0.82)[..., None]); im = Image.fromarray(arr.astype(np.uint8))
    d = ImageDraw.Draw(im)
    def font(sz):
        for fp in (os.path.join(HERE, "ThumbFont.ttf"), "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            if os.path.exists(fp):
                try:
                    f = ImageFont.truetype(fp, sz)
                    try: f.set_variation_by_axes([800])
                    except Exception: pass
                    return f
                except Exception: continue
        return ImageFont.load_default()
    words = (text or "WATCH THIS").upper().split(); best = None
    for split in range(1, len(words) + 1) if len(words) > 1 else [1]:        # 1 or 2 lines, whichever lets the letters be biggest
        lines = [" ".join(words[:split]), " ".join(words[split:])] if len(words) > 1 and split < len(words) else [" ".join(words)]
        if len(lines) > 2: continue
        for sz in range(230, 70, -6):
            f = font(sz); wmax = max(d.textlength(l, font=f) for l in lines)
            if wmax <= 760 and len(lines) * sz * 1.02 <= 470: break
        if best is None or sz > best[0]: best = (sz, lines)
    sz, lines = best; f = font(sz); y = 360 - int(len(lines) * sz * 1.0 / 2) + 40
    for k, l in enumerate(lines):
        col = (255, 255, 255) if k % 2 == 0 else (255, 224, 40); x = 48
        d.text((x + 6, y + 8), l, font=f, fill=(0, 0, 0), stroke_width=max(8, sz // 10), stroke_fill=(0, 0, 0))
        d.text((x, y), l, font=f, fill=col, stroke_width=max(8, sz // 10), stroke_fill=(0, 0, 0)); y += int(sz * 1.02)
    tag = "MYSTERY STORY" if "Mystery" in kind else "MORAL STORY"; ft = font(46); tw_ = d.textlength(tag, font=ft)
    d.rounded_rectangle((40, 36, 40 + tw_ + 44, 36 + 74), radius=16, fill=(222, 30, 36), outline=(255, 255, 255), width=4); d.text((62, 40), tag, font=ft, fill=(255, 255, 255))
    lg = os.path.join(HERE, "CORNER_LOGO.png")
    if os.path.exists(lg):
        L = Image.open(lg).convert("RGBA"); L = L.resize((300, int(300 * L.height / L.width)), Image.LANCZOS); im.paste(L, (1280 - 300 - 28, 28), L)
    out = P.p("thumbnail.jpg")
    for q in (90, 82, 74, 66):
        im.save(out, quality=q)
        if os.path.getsize(out) < 1_900_000: break
    return out


PLAYLISTS = {   # title: (description, words that send a story there)
    "All New Stories": ("Every day's new moral story - a new one every day at 6 PM.", []),
    "Farmer Stories": ("Stories of hard work in the fields and the farmer's wisdom.", ["किसान", "खेत", "फसल", "हल", "बैल", "farmer", "field", "crop"]),
    "Honesty Stories": ("Truth always wins - stories about honesty.", ["ईमानदार", "ईमानदारी", "सच", "सच्चाई", "honest", "truth"]),
    "Friendship & Family": ("The sweetness of relationships - friends, brothers, parents.", ["दोस्त", "मित्र", "दोस्ती", "परिवार", "भाई", "बहन", "माँ", "पिता", "दादी", "दादा", "friend", "family"]),
    "Greed & Lessons": ("What greed brings, and what it teaches.", ["लालच", "लालची", "सूदखोर", "साहूकार", "घमंड", "greed", "greedy"]),
    "Mystery Stories": ("Suspense and mystery stories with a clever twist.", ["रहस्य", "रहस्यमय", "राज़", "गायब", "चोरी", "mystery", "secret"]),
}


def playlist_for(st):
    """the best topic playlist for a story (by the words in its title, moral and story)"""
    text = " ".join([str(st.get("title", "")), str(st.get("moral", ""))] + [b.get("narration", "") for b in st.get("beats", [])]).lower()
    best, hits = None, 0
    for name, (_, words) in PLAYLISTS.items():
        n = sum(text.count(w.lower()) for w in words)
        if n > hits: best, hits = name, n
    return best


def add_to_playlists(yt, video_id, st):
    """creates the channel's playlists the first time, then puts the video in 'All New Stories' + its topic playlist"""
    have, token = {}, None
    while True:
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        for it in r.get("items", []): have[it["snippet"]["title"]] = it["id"]
        token = r.get("nextPageToken")
        if not token: break
    added = []
    for name in ["All New Stories"] + ([playlist_for(st)] if playlist_for(st) else []):
        if name not in have:
            body = {"snippet": {"title": name, "description": PLAYLISTS[name][0], "defaultLanguage": "en"}, "status": {"privacyStatus": "public"}}
            have[name] = yt.playlists().insert(part="snippet,status", body=body).execute()["id"]
            print(f"  playlist created: {name}")
        yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": have[name],
                                  "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
        added.append(name)
    return added


def upload_m2(P, slot=0):
    """Moral 2: title/description from story.json, thumbnail = main character picture + title, AI-made flag, schedule/public/private"""
    video = P.p("FINAL.mp4")
    if not os.path.exists(video): sys.exit("FINAL.mp4 not found")
    qc = open(P.p("QC_REPORT.txt"), encoding="utf-8").read() if os.path.exists(P.p("QC_REPORT.txt")) else ""
    if "CORRECTED & COMPLETE" not in qc and os.getenv("STUDIO_UPLOAD_IF", "complete") == "complete":
        print("NOT uploaded: QC_REPORT is not 'CORRECTED & COMPLETE' (setx STUDIO_UPLOAD_IF any to upload anyway)"); return None
    if os.path.exists(P.p("UPLOADED.json")): return P.load("UPLOADED.json")
    st = P.load("story.json"); sys.path.insert(0, HERE); import studio as S
    m = english_metadata(P, st)                                       # title, description, tags and thumbnail words: all English
    print("  title:", m["title"]); print("  thumbnail words:", m["thumb"])
    try: P.save("youtube_text.json", m)                              # the Short reuses it
    except Exception: pass
    mode = os.getenv("STUDIO_UPLOAD", "schedule").lower()
    status = {"privacyStatus": "private" if mode in ("private", "schedule") else "public",
              "selfDeclaredMadeForKids": os.getenv("STUDIO_AUDIENCE", "family").lower() == "kids", "containsSyntheticMedia": True}
    if mode == "schedule": status["publishAt"] = publish_time(slot)
    body = {"snippet": {"title": m["title"], "description": m["description"], "tags": m["tags"], "categoryId": "1",
                        "defaultLanguage": "en", "defaultAudioLanguage": "hi"}, "status": status}
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=credentials())
    res = _insert_safely(yt, body, video, "video")
    vid = res["id"]
    import glob as _g
    pics = sorted(_g.glob(os.path.join(P.dir, "pictures*", "*.png")))
    if pics:
        os.makedirs(P.p("work"), exist_ok=True); os.makedirs(P.p("images"), exist_ok=True)
        import shutil as _sh; _sh.copy(pics[0], P.p("images", "001.png"))
        th = None
        try: th = thumbnail_en(P, st, m["thumb"], m.get("kind", "Hindi Mystery Story"))
        except Exception as e: print("  (English thumbnail failed:", str(e)[:100], ")")
        th = th or thumbnail(P, m["thumb"])
        if th:
            try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th)).execute()
            except Exception as e: print("  (thumbnail not set - verify the channel with a phone number)", str(e)[:60])
    try:
        lists = add_to_playlists(yt, vid, st); print("  playlists:", ", ".join(lists))
    except Exception as e:
        lists = []; print("  (playlists not updated:", str(e)[:120], ")")
    info = {"id": vid, "url": f"https://youtu.be/{vid}", "title": m["title"], "style": m.get("style", ""), "mode": mode, "publishAt": status.get("publishAt"), "playlists": lists}
    P.save("UPLOADED.json", info); return info


def _publish_after(rfc, minutes=30):
    """an RFC3339 time + minutes (the Short goes public after the main video, so the link in its description works)"""
    t = datetime.datetime.strptime(rfc, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def upload_short(P, st, main_info, short_path):
    """the Short: English title + #Shorts, the link to the full video first in the description, published 30 minutes after the main video"""
    if os.path.exists(P.p("SHORT_UPLOADED.json")): return P.load("SHORT_UPLOADED.json")
    m = P.load("youtube_text.json"); link = main_info["url"]
    base = re.sub(r"\s*\|\s*(?:Hindi (?:Mystery|Moral) Story|Hindi Kahani)\s*$", "", m["title"]).strip()
    title = (base + " #Shorts")[:100]
    first = next((l for l in m["description"].splitlines() if l.strip()), "")
    desc = (f"Watch the FULL story here: {link}\n\n{first}\n\nNarrated in Hindi with Hindi subtitles.\nA new story every day at 6 PM IST - subscribe to The Moral Story Club.\n\n"
            "This story was made with the help of AI.\n\n#Shorts #HindiKahani #MysteryStory #HindiStories")
    mode = os.getenv("STUDIO_UPLOAD", "schedule").lower()
    status = {"privacyStatus": "private" if mode in ("private", "schedule") else "public",
              "selfDeclaredMadeForKids": os.getenv("STUDIO_AUDIENCE", "family").lower() == "kids", "containsSyntheticMedia": True}
    if mode == "schedule" and main_info.get("publishAt"): status["publishAt"] = _publish_after(main_info["publishAt"], int(os.getenv("M2_SHORT_DELAY_MIN", "30")))
    elif mode == "schedule": status["publishAt"] = publish_time(0)
    body = {"snippet": {"title": title, "description": desc, "tags": fit_tags((m.get("tags") or [])[:20] + ["shorts"]), "categoryId": "1", "defaultLanguage": "en", "defaultAudioLanguage": "hi"}, "status": status}
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=credentials())
    res = _insert_safely(yt, body, short_path, "Short")
    info = {"id": res["id"], "url": f"https://youtube.com/shorts/{res['id']}", "title": title, "publishAt": status.get("publishAt")}
    P.save("SHORT_UPLOADED.json", info); return info


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    login() if sys.argv[1] == "login" else upload(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
