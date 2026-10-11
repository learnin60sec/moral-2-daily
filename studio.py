"""
MORAL STORY STUDIO - the 6-stage "Master Prompt" workflow (ChatGPT -> Gemini -> Google Flow), automated.
    python studio.py new                 Stage 1: 15 story ideas -> you pick a number -> Stages 2-3 run by themselves
    python studio.py sheets              Stage 4: Gemini character sheets (helper window: copy prompt, download)
    python studio.py images              Stage 5: Gemini scene images, one per 8-second shot (helper window)
    python studio.py clips               Stage 6: Google Flow clips (helper window: copy picture + prompt, download)
    python studio.py qc                  check every clip (length, 16:9, sound, 2D style) -> QC_REPORT.txt
    python studio.py redo                make only the failed clips again
    python studio.py final               join everything: one narrator voice for all narration, subtitles -> FINAL.mp4
    python studio.py status              what is done / what is next
Options:  --minutes 15 (story length)   --project <folder>   --auto (pick the best idea yourself)
Keys: GEMINI_API_KEY and/or GROQ_API_KEY (text AI).  Nothing is ever posted for you - you stay in control.
"""
import os, sys, re, json, time, glob, shutil, subprocess, webbrowser, argparse, asyncio, math
HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_URL, GEMINI_URL = "https://labs.google/fx/tools/flow", "https://gemini.google.com/app"

STYLE_LOCK = ("STRICT 2D CARTOON ANIMATION ONLY. Animate the attached approved 2D illustrated starting frame. Preserve the exact "
              "illustrated character designs, simplified cartoon facial features, clean drawn outlines, flat painted colors, subtle 2D "
              "cel shading, illustrated village environment, and overall 2D art direction. Keep every frame visually consistent with "
              "the supplied 2D image. All movement must look like professional 2D cartoon animation, not live-action movement captured "
              "by a camera. Maintain the illustrated appearance from the first frame to the last frame. Do not convert any character "
              "or environment into photorealistic, semi-realistic, live-action, or 3D imagery.")
STYLE_BIBLE = ("Premium traditional 2D cartoon animation for an Indian village moral story. Clearly illustrated, hand-drawn-looking "
               "cartoon characters with simplified stylized anatomy, clean and consistent ink-like outlines, flat painted color regions, "
               "subtle 2D cel shading, expressive cartoon faces, deliberately illustrated Indian village backgrounds. The result must look "
               "like a polished 2D animated cartoon, NOT filmed reality. No photorealism, no 3D, no anime, no text.")
FINAL_REMINDER = "Remain premium hand-drawn-looking 2D cartoon animation in every frame. Never become live-action, photorealistic, semi-realistic, or 3D."
NARRATOR = {"voice_id": "NARRATOR_01", "edge": ("hi-IN-MadhurNeural", "+0%", "-3Hz"),
            "description": "Adult male, natural Indian Hindi, warm, clear, medium-deep, steady storytelling pace"}


EMOTIONS = {  # emotion -> (rate, pitch, volume, pause after the line in seconds)
    "warm": ("+0%", "+0Hz", "+0%", 0.4), "suspense": ("-8%", "-5Hz", "-4%", 0.7), "sad": ("-9%", "-6Hz", "-6%", 0.7),
    "joy": ("+5%", "+4Hz", "+4%", 0.35), "angry": ("+5%", "-3Hz", "+10%", 0.4), "shock": ("+3%", "+6Hz", "+8%", 0.6),
    "wise": ("-6%", "-3Hz", "+0%", 0.6), "tension": ("+4%", "-2Hz", "+6%", 0.4)}


# ------------------------------------------------------------------ text AI (Groq first, then Gemini; quiet fallbacks)
_DEAD = set()


def parse(text):
    if not text: return None
    text = text.replace("```json", "").replace("```", "")
    m = re.search(r"\{.*\}", text, re.S)
    try: return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError: return None


def ask(prompt):
    import requests
    gk = os.getenv("GROQ_API_KEY")
    if gk and "groq" not in _DEAD:
        for model in ("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b"):
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {gk}"}, timeout=240,
                                  json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": .8,
                                        "response_format": {"type": "json_object"}})
                if r.status_code == 200:
                    d = parse(r.json()["choices"][0]["message"]["content"])
                    if d: return d
            except Exception:
                pass
        _DEAD.add("groq")
    key = os.getenv("GEMINI_API_KEY")
    if key:
        try:
            ms = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key}, timeout=30).json().get("models", [])
            names = sorted([m["name"].split("/")[-1] for m in ms if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m["name"]
                            and not any(x in m["name"] for x in ("image", "tts", "audio", "live"))], key=lambda n: ("lite" not in n, n))
        except Exception:
            names = []
        for n in names:
            if n in _DEAD: continue
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{n}:generateContent", headers={"x-goog-api-key": key},
                                  json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}, timeout=240)
                if r.status_code == 200:
                    d = parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                    if d: return d
                else:
                    _DEAD.add(n)
            except Exception:
                _DEAD.add(n)
    sys.exit("STOPPED: no text AI answered (set GROQ_API_KEY or GEMINI_API_KEY, or wait for the free limit to reset)")


def youtube_views(title):
    """total views of the 10 most-viewed similar Hindi moral-story videos of the last 90 days (YOUTUBE_API_KEY)"""
    import requests, datetime
    key = os.getenv("YOUTUBE_API_KEY")
    if not key: return 0
    after = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=30, params={"part": "id", "type": "video",
                         "q": f"{title} moral story hindi kahani", "order": "viewCount", "publishedAfter": after,
                         "regionCode": "IN", "maxResults": 10, "key": key}).json()
        ids = ",".join(x["id"]["videoId"] for x in r.get("items", []))
        if not ids: return 0
        v = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=30, params={"part": "statistics", "id": ids, "key": key}).json()
        return sum(int(x["statistics"].get("viewCount", 0)) for x in v.get("items", []))
    except Exception:
        return 0


# ------------------------------------------------------------------ project state
class Project:
    def __init__(self, folder):
        self.dir = folder; os.makedirs(folder, exist_ok=True)
        for sub in ("characters", "images", "clips", "audio", "work"): os.makedirs(os.path.join(folder, sub), exist_ok=True)
    def p(self, *a): return os.path.join(self.dir, *a)
    def load(self, name, default=None):
        try: return json.load(open(self.p(name), encoding="utf-8"))
        except Exception: return default
    def save(self, name, data):
        json.dump(data, open(self.p(name), "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def latest_project():
    ps = sorted(glob.glob(os.path.join(HERE, "projects", "*")))
    return ps[-1] if ps else None


# ------------------------------------------------------------------ STAGE 1-3
USED = os.path.join(HERE, "used_stories.json")


def used_stories():
    try: return json.load(open(USED, encoding="utf-8"))
    except Exception: return []


def stage1(P, auto=False):
    used = used_stories()
    avoid = ("\nDo NOT repeat or closely resemble these stories already made: " + "; ".join(used[-80:])) if used else ""
    d = ask(avoid + """\nYou are a professional Hindi moral story writer. Generate exactly 15 ORIGINAL, family-friendly Hindi moral story ideas set in
an Indian village (genre like: two bullocks of Raju, poor farmer and greedy moneylender, two brothers' partition, old farmer's last wish,
hard-working farmer and lazy son - genre only, do not copy plots). Each idea: interesting opening, relatable village characters, central
conflict, emotional development, turning point, logical ending, clear moral, enough depth for 15-20 minutes. Write in Hindi (Devanagari).
JSON only: {"ideas": [{"no": 1, "title": "...", "characters": "...", "concept": "...", "conflict": "...", "twist": "...", "moral": "...", "score": 1-10}]}
"score" = how strong the idea is for a viral YouTube moral story.""")
    ideas = [i for i in d.get("ideas", []) if isinstance(i, dict) and i.get("title")][:15]
    fresh = [i for i in ideas if i["title"] not in used]
    ideas = fresh or ideas
    P.save("ideas.json", ideas)
    txt = "\n\n".join(f"{i['no']}. {i['title']}\n   पात्र: {i.get('characters','')}\n   कॉन्सेप्ट: {i.get('concept','')}\n   संघर्ष: {i.get('conflict','')}"
                      f"\n   मोड़: {i.get('twist','')}\n   सीख: {i.get('moral','')}" for i in ideas)
    open(P.p("1_IDEAS.txt"), "w", encoding="utf-8").write(txt)
    print(txt)
    if auto:
        import math
        for i in ideas:
            v = youtube_views(i["title"])
            i["yt_views"] = v; i["total"] = round(i.get("score", 5) + (math.log10(v + 10) if v else 0), 2)
            print(f"  {i['no']:>2}. {i['title'][:40]:40s}  AI {i.get('score', 0)}  YouTube views {v:,}  -> {i['total']}")
        pick = max(ideas, key=lambda i: i.get("total", i.get("score", 0)))["no"]
    else:
        pick = int(input("\nStory number chuno (1-15): ").strip() or 1)
    chosen = next((i for i in ideas if int(i["no"]) == pick), ideas[0])
    P.save("chosen.json", chosen); print("CHOSEN:", chosen["title"])
    json.dump(used + [chosen["title"]], open(USED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return chosen


def stage2(P, minutes):
    idea = P.load("chosen.json")
    n_scenes = max(4, round(minutes * 0.8))
    words = int(minutes * 130)
    out = ask(f"""Plan the COMPLETE Hindi moral story "{idea['title']}" ({json.dumps(idea, ensure_ascii=False)}) for a {minutes}-minute 2D animated
YouTube video. Make exactly {n_scenes} numbered scenes: strong opening hook, village and characters, main conflict, development,
emotional turning point/climax, satisfying ending with the moral. JSON only:
{{"scenes": [{{"id": 1, "title": "...", "summary": "what happens (Hindi)"}}]}}""")
    scenes = [x for x in out.get("scenes", []) if isinstance(x, dict)][:n_scenes]; full = []
    for k, x in enumerate(scenes, 1): x.setdefault("id", k); x.setdefault("title", f"Scene {k}"); x.setdefault("summary", x.get("title", ""))
    per = max(60, words // len(scenes))
    for sc in scenes:
        prev = " / ".join(f"{x.get('id', '')}: {x.get('summary') or x.get('title', '')}" for x in full[-3:]) or "start of the story"
        d = ask(f"""Write SCENE {sc['id']} "{sc['title']}" of the Hindi moral story "{idea['title']}". Scene plan: {sc['summary']}.
Story so far: {prev}. About {per} spoken Hindi words in this scene (narration + dialogue together), natural conversational Hindi (Devanagari).
Do not confuse narration with dialogue. JSON only:
{{"id": {sc['id']}, "title": "{sc['title']}", "summary": "{sc['summary']}",
 "visual": "A. location, time, characters, action, expressions, props, illustrated environment, 2D camera directions (English)",
 "narration": "B. exact Hindi narrator voiceover for this scene",
 "dialogue": [{{"speaker": "character name", "line": "C. exact Hindi line"}}],
 "audio": "D. ambience, music mood, sound effects, pauses (English)",
 "continuity": "E. clothing, props, positions, lighting to carry into the next scene (English)"}}""")
        d = d if isinstance(d, dict) else {}
        d.setdefault("id", sc["id"]); d.setdefault("title", sc.get("title", "")); d.setdefault("summary", sc.get("summary", ""))
        d["dialogue"] = [x for x in d.get("dialogue", []) if isinstance(x, dict) and x.get("speaker") and x.get("line")]
        full.append(d); print(f"  scene {sc['id']}/{len(scenes)} written")
    P.save("story.json", {"title": idea["title"], "moral": idea.get("moral", ""), "scenes": full})
    txt = [f"{idea['title']}\n{'=' * 50}"]
    for s in full:
        txt.append(f"\nSCENE {s.get('id')} - {s.get('title', '')}\nA. VISUAL: {s.get('visual','')}\nB. NARRATION: {s.get('narration','')}\nC. DIALOGUE:")
        txt += [f"   {d['speaker']}: {d['line']}" for d in s.get("dialogue", [])]
        txt.append(f"D. AUDIO: {s.get('audio','')}\nE. CONTINUITY: {s.get('continuity','')}")
    txt.append(f"\nसीख: {idea.get('moral','')}")
    open(P.p("2_STORY.txt"), "w", encoding="utf-8").write("\n".join(txt))


def stage3(P):
    story = P.load("story.json")
    speakers = sorted({d["speaker"] for s in story["scenes"] for d in s.get("dialogue", [])})
    d = ask(f"""From this Hindi moral story extract EVERY identifiable human and animal character (speakers: {speakers}) and build a permanent
Character Consistency Bible for PREMIUM 2D CARTOON animation. STORY: {json.dumps(story, ensure_ascii=False)[:14000]}
JSON only: {{"characters": [{{"id": "CHARACTER 01", "name": "exact name as used in the story", "role": "...", "age": "...", "gender": "...",
 "look": "complete 2D cartoon visual description in English, ONE fixed design: age, height/body, skin, face shape, hair/moustache, exact
 TRADITIONAL INDIAN VILLAGE clothing with exact colours (dhoti/kurta/saree/turban/gamchha - never suits or western clothes),
 footwear, accessories, distinctive features", "expressions": "typical expressions and body language",
 "voice": {{"voice_id": "VOICE_01", "age": "...", "gender": "...", "pitch": "...", "tone": "...", "pace": "...", "notes": "..."}},
 "scenes": [1, 2]}}]}}""")
    chars = d.get("characters", [])
    chars = [c for c in chars if isinstance(c, dict) and c.get("name")]
    for i, c in enumerate(chars, 1):
        c["id"] = f"CHARACTER {i:02d}"; c.setdefault("look", ""); c.setdefault("role", ""); c.setdefault("age", "")
        if not isinstance(c.get("voice"), dict): c["voice"] = {}
        c["voice"]["voice_id"] = f"VOICE_{i:02d}"
    P.save("bible.json", {"characters": chars, "narrator": NARRATOR})
    lines = [f"{c['id']} - {c['name']} ({c.get('role','')}, {c.get('age','')})\n  LOOK: {c.get('look','')}\n  VOICE {c['voice']['voice_id']}: "
             f"{c['voice'].get('gender','')} {c['voice'].get('age','')}, {c['voice'].get('pitch','')}, {c['voice'].get('tone','')}" for c in chars]
    lines.append(f"\nNARRATOR_01: {NARRATOR['description']}")
    open(P.p("3_CHARACTERS.txt"), "w", encoding="utf-8").write("\n\n".join(lines))
    print(f"  {len(chars)} characters + voice bible ready")


# ------------------------------------------------------------------ STAGE 4-6 (prompts + shot plan, all by code)
def sheet_prompt(c):
    return (f"Create ONE 16:9 character reference sheet (1920x1080) in this style: {STYLE_BIBLE}\n"
            f"TOP: the text \"{c['name']} - {c['id']} - {c.get('role','')}, {c.get('age','')}\".\n"
            f"MIDDLE: five FULL-BODY views of the SAME character, not cropped: 1) front view 2) left-side view 3) right-side view "
            f"4) back view 5) three-quarter view. The left and right views must be genuinely different profiles.\n"
            f"BOTTOM: a short readable description.\nCHARACTER: {c.get('look','')}\n"
            f"Clean white background. All five views keep the same identity, anatomy, clothing, colors and accessories. "
            f"Do not combine different characters. Not realistic, not 3D.")


def split_words(text, limit=24):
    """one shot = whole sentences. A sentence is never cut in the middle; only a very long one is split at a comma."""
    sents = [x.strip() for x in re.split(r"(?<=[।!?\.])\s+", text.strip()) if x.strip()]
    pieces = []
    for sent in sents:
        if len(sent.split()) <= limit + 8:
            pieces.append(sent); continue
        cur = ""
        for part in re.split(r"(?<=[,;])\s+", sent):                  # very long sentence -> at commas only
            if cur and len((cur + " " + part).split()) > limit:
                pieces.append(cur.strip()); cur = part
            else:
                cur = (cur + " " + part).strip()
        if cur: pieces.append(cur)
    out, cur = [], ""
    for pc in pieces:                                                   # join short sentences up to the limit
        if cur and len((cur + " " + pc).split()) > limit:
            out.append(cur); cur = pc
        else:
            cur = (cur + " " + pc).strip()
    if cur: out.append(cur)
    return out

def tag_emotions(shots):
    """one AI call: the feeling of every line, and a natural spoken version with pauses (same words, only '...' and commas)"""
    try:
        d = ask("You are the voice director of a Hindi moral story. For every line give the emotion the narrator/character should use: "
                "warm, suspense, sad, joy, angry, shock, wise or tension. Also give 'spoken': the SAME Hindi words, adding at most one or two "
                "commas where a human storyteller naturally breathes (never '...', do not change, add or remove words). "
                'JSON only: {"lines": [{"i": 0, "emotion": "warm", "spoken": "..."}]}\n'
                + "\n".join(f"{i}|{s['kind']}|{s.get('speaker') or 'narrator'}|{s['text']}" for i, s in enumerate(shots)))
        items = d.get("lines") or d.get("emotions") or d.get("items") or [] if isinstance(d, dict) else []
        for k, it in enumerate(items):
            if isinstance(it, str):                                   # just a list of emotions, in order
                it = {"i": k, "emotion": it}
            if not isinstance(it, dict): continue
            try: i = int(it.get("i", k))
            except (TypeError, ValueError): i = k
            if 0 <= i < len(shots):
                e = str(it.get("emotion", "warm")).lower().strip(); shots[i]["emotion"] = e if e in EMOTIONS else "warm"
                sp = str(it.get("spoken") or "")
                same = re.sub(r"[\s.,…!?।-]", "", sp) == re.sub(r"[\s.,…!?।-]", "", shots[i]["text"])
                sp = re.sub(r"\s*(\.\.\.|…)\s*", ", ", sp).replace(", ,", ",")
                if sp and same: shots[i]["spoken"] = sp                    # only pauses were added - safe to use
    except (SystemExit, Exception) as e:
        print(f"  (emotions could not be read fully - neutral voice for the rest: {str(e)[:60]})")
    for s in shots: s.setdefault("emotion", "warm")
    return shots


def mark_key_shots(shots, max_keys=None):
    """KEY shots go to Flow (opening of every scene, the last scene's climax, the very end, some dialogue);
    all other shots are made automatically as storybook motion (slow zoom/pan on the picture)"""
    max_keys = max_keys or int(os.getenv("STUDIO_KEY_SHOTS", "15"))
    want = []
    scenes = sorted({s["scene"] for s in shots})
    for sc in scenes:
        first = next(s for s in shots if s["scene"] == sc); want.append(first["id"])
    last_scene = [s for s in shots if s["scene"] == scenes[-1]]
    want += [s["id"] for s in last_scene[-3:]]
    dialog = [s for s in shots if s["kind"] == "dialogue" and s["id"] not in want]
    step = max(1, len(dialog) // max(1, max_keys - len(set(want))))
    want += [s["id"] for s in dialog[::step]]
    keep = []
    for w in want:
        if w not in keep: keep.append(w)
    keep = set(keep[:max_keys])
    for s in shots: s["key"] = s["id"] in keep
    return shots


def plan_shots(P):
    story, bible = P.load("story.json"), P.load("bible.json")
    byname = {c["name"]: c for c in bible["characters"]}
    shots = []
    for s in story["scenes"]:
        present = [n for n in byname if n in (s.get("visual", "") + " " + s.get("narration", "")) or any(d["speaker"] == n for d in s.get("dialogue", []))]
        k = 0
        def add(kind, text, speaker=None):
            nonlocal k; k += 1
            shots.append({"id": f"S{int(s['id']):02d}_SH{k:02d}", "scene": int(s["id"]), "kind": kind, "text": text, "speaker": speaker,
                          "characters": present or list(byname)[:2], "visual": s.get("visual", ""), "audio": s.get("audio", ""),
                          "continuity": s.get("continuity", "")})
        for piece in split_words(s.get("narration", "")): add("narration", piece)
        for d in s.get("dialogue", []):
            for piece in split_words(d["line"]): add("dialogue", piece, d["speaker"])
    for i, sh in enumerate(shots):
        chars = [byname[n] for n in sh["characters"] if n in byname]
        who = "; ".join(f"{c['name']} ({c['id']}): {c.get('look','')}" for c in chars)
        action = (f"{sh['speaker']} is about to speak, the others look at {sh['speaker']}" if sh["kind"] == "dialogue"
                  else "the characters go about the scene action")
        sh["image_prompt"] = (f"Wide 16:9 cinematic scene from a 2D cartoon movie, full background visible: {sh['visual']} "
                              f"Moment: {action}. Rural Indian village setting with a detailed painted background (houses, fields, trees, sky). "
                              f"Characters in the scene (full body, whole head and face inside the frame, placed in the middle of the picture): {who}. "
                              f"Traditional Indian village clothes only (dhoti, kurta, saree, gamchha), no suits or western clothes. "
                              f"Continuity: {sh['continuity']}. Style: {STYLE_BIBLE} "
                              f"NOT a character sheet, NOT a plain white or grey background, NOT a turnaround. "
                              f"No text, no letters, no signs, no captions, no speech bubbles.")
        if sh["kind"] == "dialogue":
            c = byname.get(sh["speaker"], {"id": "?", "voice": {}})
            v = c.get("voice", {})
            voice = (f"VOICE ID: {v.get('voice_id','?')} for {sh['speaker']} ({c['id']}) only: {v.get('gender','')} {v.get('age','')}, "
                     f"{v.get('pitch','')} pitch, {v.get('tone','')} tone, {v.get('pace','')} pace. Only {sh['speaker']} speaks this line, "
                     f"with cartoon mouth and facial animation; nobody else talks.\nEXACT HINDI LINE ({sh['speaker']}): \"{sh['text']}\"")
            timeline = f"0:00-0:01 {sh['speaker']} looks up; 0:01-0:07 says the line with natural gestures; 0:07-0:08 listeners react."
        else:
            voice = ("NO SPEECH in this clip: the narration is added later by the studio with one fixed narrator voice (NARRATOR_01). "
                     "Characters must NOT move their mouths as if speaking.")
            timeline = "0:00-0:08 calm continuous 2D action matching the narration, gentle 2D animated camera push-in."
        sh["flow_prompt"] = (f"{STYLE_LOCK}\nREFERENCE: Animate the supplied approved 2D starting frame; preserve its illustrated appearance and "
                             f"character identities.\nSCENE: {sh['visual']}\nACTION (8 seconds): {timeline}\n{voice}\nAMBIENCE: {sh['audio']}\n"
                             f"ENDING: hold the final pose for continuity ({sh['continuity']}).\n{FINAL_REMINDER}\nExactly 8 seconds, 16:9.")
    mark_key_shots(shots)
    tag_emotions(shots)
    P.save("shots.json", shots)
    open(P.p("5_SHOTS.txt"), "w", encoding="utf-8").write("\n\n".join(
        f"{s['id']} [{s['kind']}{' - ' + s['speaker'] if s['speaker'] else ''}] {s['text']}\nIMAGE PROMPT:\n{s['image_prompt']}\nFLOW PROMPT:\n{s['flow_prompt']}" for s in shots))
    print(f"  {len(shots)} shots of 8 seconds = about {len(shots) * 8 / 60:.1f} minutes")
    return shots


# ------------------------------------------------------------------ helper window (copy -> paste in Gemini/Flow -> download -> saved)
def copy_text(t):
    try:
        import pyperclip; pyperclip.copy(t); return True
    except Exception:
        return False


def copy_image(path):
    if os.name != "nt": return False
    ps = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
          f"[System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{os.path.abspath(path)}'))")
    return subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True).returncode == 0


def download_dirs():
    home = os.path.expanduser("~")
    return [d for d in dict.fromkeys([os.getenv("STUDIO_DOWNLOADS") or "", os.path.join(home, "Downloads"), os.path.join(home, "OneDrive", "Downloads")]) if d and os.path.isdir(d)]


def helper(items, url, kind):
    """items: dicts with title, prompt, dest, optional picture, optional uploads (list of files to upload)"""
    todo = [it for it in items if not os.path.exists(it["dest"])]
    if not todo: print("  all done here"); return
    import tkinter as tk
    from PIL import Image, ImageTk
    webbrowser.open(url)
    exts = (".png", ".jpg", ".jpeg", ".webp") if kind == "image" else (".mp4", ".mov", ".webm")
    taken = set(); st = {"i": 0, "since": time.time()}
    root = tk.Tk(); root.title("Studio helper"); root.attributes("-topmost", True); root.geometry("+20+20"); root.configure(bg="#1f2a44")
    title = tk.Label(root, fg="#ffd34d", bg="#1f2a44", font=("Segoe UI", 12, "bold")); title.pack(padx=10, pady=(8, 2))
    pic = tk.Label(root, bg="#1f2a44"); pic.pack()
    info = tk.Label(root, fg="white", bg="#1f2a44", wraplength=320, justify="left"); info.pack(padx=10, pady=4)
    def show():
        it = todo[st["i"]]; title.config(text=f"{it['title']}   ({len(todo) - st['i']} left)")
        if it.get("picture"):
            th = Image.open(it["picture"]).convert("RGB"); th.thumbnail((320, 180)); ph = ImageTk.PhotoImage(th); pic.config(image=ph); pic.image = ph
        else:
            pic.config(image=""); pic.image = None
        up = it.get("uploads") or []
        info.config(text=("Upload these first: " + ", ".join(os.path.basename(u) for u in up) + "\n" if up else "") +
                    ("1) Copy PICTURE -> Ctrl+V   " if it.get("picture") else "") + "2) Copy PROMPT -> Ctrl+V -> Enter/Generate -> Download")
        st["since"] = time.time()
        if it.get("picture"): copy_image(it["picture"])             # Flow: picture first (prompt via button 2)
        else: copy_text(it["prompt"])                               # Gemini: prompt is already on the clipboard
    def nxt():
        st["i"] += 1
        if st["i"] >= len(todo): root.destroy()
        else: show()
    tk.Button(root, text="1) Copy PICTURE", width=24, bg="#ffd34d", font=("Segoe UI", 11, "bold"),
              command=lambda: copy_image(todo[st["i"]]["picture"]) if todo[st["i"]].get("picture") else None).pack(pady=2)
    tk.Button(root, text="2) Copy PROMPT", width=24, bg="#7fd1ff", font=("Segoe UI", 11, "bold"),
              command=lambda: copy_text(todo[st["i"]]["prompt"])).pack(pady=2)
    tk.Button(root, text="Open upload folder", width=24, command=lambda: os.startfile(os.path.dirname(todo[st["i"]]["uploads"][0]))
              if todo[st["i"]].get("uploads") and os.name == "nt" else None).pack(pady=2)
    tk.Button(root, text="Skip", command=nxt, bg="#ccc").pack(pady=2)
    tk.Button(root, text="Stop (continue later)", command=root.destroy, bg="#888").pack(pady=(2, 8))
    def watch():
        if st["i"] < len(todo):
            for d in download_dirs():
                for f in os.listdir(d):
                    p = os.path.join(d, f)
                    if f.lower().endswith(exts) and p not in taken and os.path.getmtime(p) > st["since"]:
                        time.sleep(1.5); taken.add(p); shutil.copy(p, todo[st["i"]]["dest"]); print("  saved", os.path.basename(todo[st["i"]]["dest"])); nxt(); break
        root.after(1500, watch)
    show(); root.after(1500, watch); root.mainloop()


def stage4(P):
    items = [{"title": f"SHEET {c['id']} - {c['name']}", "prompt": sheet_prompt(c), "dest": P.p("characters", f"{c['id'].replace(' ', '_')}.png")}
             for c in P.load("bible.json")["characters"]]
    open(P.p("4_SHEET_PROMPTS.txt"), "w", encoding="utf-8").write("\n\n".join(f"{i['title']}\n{i['prompt']}" for i in items))
    helper(items, GEMINI_URL, "image")


def stage5(P):
    shots = P.load("shots.json") or plan_shots(P); bible = P.load("bible.json"); byname = {c["name"]: c for c in bible["characters"]}
    items = []
    for s in shots:
        ups = [P.p("characters", f"{byname[n]['id'].replace(' ', '_')}.png") for n in s["characters"] if n in byname]
        items.append({"title": f"IMAGE {s['id']}", "prompt": s["image_prompt"], "dest": P.p("images", f"{s['id']}.png"), "uploads": [u for u in ups if os.path.exists(u)]})
    helper(items, GEMINI_URL, "image")


def stage6(P, only=None, all_shots=False):
    shots = P.load("shots.json")
    if not any("key" in s for s in shots): mark_key_shots(shots); P.save("shots.json", shots)
    items = [{"title": f"CLIP {s['id']}" + (" (KEY)" if s.get("key") else ""), "prompt": s["flow_prompt"], "picture": P.p("images", f"{s['id']}.png"),
              "dest": P.p("clips", f"{s['id']}.mp4")}
             for s in shots if os.path.exists(P.p("images", f"{s['id']}.png")) and (only is not None and s["id"] in only
                                                                                       or only is None and (all_shots or s.get("key")))]
    print(f"  Flow clips needed: {len(items)} key shots (the other shots become storybook motion by themselves; --all for every shot)")
    helper(items, FLOW_URL, "video")


# ------------------------------------------------------------------ CLOUDFLARE (free, automatic): scene images + flipbook frames
class CFLimit(Exception):
    pass


def cf_on():
    return bool(os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_API_TOKEN")) and os.getenv("STUDIO_ENGINE", "cloudflare") != "manual"


def cf_run(model, payload):
    """returns image bytes, None on a normal failure, raises CFLimit when today's free allowance is used up"""
    import requests, base64
    try:
        r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{os.getenv('CLOUDFLARE_ACCOUNT_ID')}/ai/run/{model}",
                          headers={"Authorization": f"Bearer {os.getenv('CLOUDFLARE_API_TOKEN')}"}, json=payload, timeout=240)
    except Exception as e:
        print(f"   ({model.split('/')[-1]}: no connection {str(e)[:60]})"); return None
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
        return r.content                                        # a picture - never look for error words inside it
    if r.status_code != 200:
        msg = r.text[:400].lower()
        if r.status_code == 429 or "daily free allocation" in msg or '"code":4006' in msg.replace(" ", "") or "neurons" in msg and "limit" in msg:
            raise CFLimit(r.text[:200])
        print(f"   ({model.split('/')[-1]}: {r.status_code} {r.text[:160]})"); return None
    try:
        return base64.b64decode(r.json()["result"]["image"])
    except Exception:
        return None


def clean_frame(data, path):
    """remove black letterbox bars and save as 1280x720"""
    from PIL import Image
    import io
    import numpy as np
    im = Image.open(io.BytesIO(data)).convert("RGB"); a = np.asarray(im).astype(int)
    rows = np.where(a.max(axis=(1, 2)) > 28)[0]
    if len(rows) and (rows[0] > 4 or rows[-1] < a.shape[0] - 5):
        im = im.crop((0, int(rows[0]), im.width, int(rows[-1]) + 1))
    w, h = im.size; tw = min(w, int(h * 16 / 9)); th = min(h, int(w * 9 / 16))
    top = int((h - th) * 0.25)                                    # keep heads: take the picture a little above the middle
    im = im.crop(((w - tw) // 2, top, (w - tw) // 2 + tw, top + th)).resize((1280, 720), Image.LANCZOS)
    im.save(path)


def cf_scene_image(prompt, path, seed):
    """FLUX schnell by default (cheap in Neurons); Lucid Origin only if chosen (about 3,000 Neurons per picture!)"""
    short = prompt.replace("\n", " ")[:1700]
    flux = ("@cf/black-forest-labs/flux-1-schnell", {"steps": 6},
            " Wide cinematic composition: keep all important characters and action in the middle band of the picture.")
    lucid = ("@cf/leonardo/lucid-origin", {"width": 1344, "height": 768, "seed": seed}, "")
    order = (lucid, flux) if os.getenv("STUDIO_CF_MODEL", "flux").lower() == "lucid" else (flux,)
    for model, extra, add in order:
        data = cf_run(model, dict({"prompt": short + add}, **extra))
        if data:
            clean_frame(data, path); return True
    return False


MOVES = {"dialogue": ["the speaking character's mouth slightly open while talking, one hand gesturing", "the speaking character's head tilted a little, eyes blinking",
                      "the listeners reacting with a small nod"],
         "narration": ["characters moving slightly, natural breathing", "a gentle breeze moving leaves and clothes", "small step forward, soft light change"]}


def cf_frames(base_path, shot, n, seed):
    """flipbook: n slightly changed copies of the same picture (img2img, low strength, same seed)"""
    import base64
    b64 = base64.b64encode(open(base_path, "rb").read()).decode()
    made = 0
    for k in range(1, n + 1):
        out = base_path.replace(".png", f"_f{k}.png")
        if os.path.exists(out): made += 1; continue
        move = MOVES[shot["kind"]][(k - 1) % 3]
        prompt = (f"Same scene, same characters, same 2D cartoon style as the picture, nothing new added. {move}. "
                  f"{STYLE_BIBLE[:300]}")
        data = None
        for model, extra in (("@cf/stabilityai/stable-diffusion-xl-base-1.0", {"image_b64": b64, "strength": 0.32, "num_steps": 20,
                                                                                "guidance": 7.5, "seed": seed, "width": 1280, "height": 720}),
                             ("@cf/runwayml/stable-diffusion-v1-5-img2img", {"image_b64": b64, "strength": 0.3, "num_steps": 20, "guidance": 7.5})):
            data = cf_run(model, dict({"prompt": prompt}, **extra))
            if data: break
        if not data:
            os.environ["STUDIO_FRAMES"] = "0"; print("   (flipbook copies are not possible with this account - switching to living pictures)"); break
        clean_frame(data, out); made += 1
    return made


def live_log(P, line):
    with open(P.p("LIVE_QC.txt"), "a", encoding="utf-8") as f: f.write(time.strftime("%H:%M ") + line + "\n")
    print("   [live check] " + line)


def check_pictures_now(P, sids, shots_by_id):
    """LIVE: Groq/Gemini look at freshly made pictures; a bad one is made again (2 tries) before any video is made from it"""
    bible = P.load("bible.json") or {"characters": []}
    btxt = "; ".join(f"{c.get('name')}: {c.get('look', '')}" for c in bible.get("characters", []))
    todo = list(sids)
    for attempt in range(1, 3):
        paths = [P.p("images", f"{sid}.png") for sid in todo if os.path.exists(P.p("images", f"{sid}.png"))]
        bad = gemini_look(paths, btxt) or {}
        checked = set(P.load("checked_pictures.json", [])) | {os.path.basename(x) for x in paths}
        P.save("checked_pictures.json", sorted(checked))
        if not bad: return
        todo = []
        for pth, problems in bad.items():
            sid = os.path.basename(pth)[:-4]; sh = shots_by_id.get(sid)
            if not sh: continue
            live_log(P, f"{sid} picture: {'; '.join(problems)} -> making it again (try {attempt})")
            os.replace(pth, pth + ".bad.png")
            try:
                ok = cf_scene_image(sh["image_prompt"] + f" IMPORTANT, AVOID: {'; '.join(problems)}.", pth, 3000 + attempt)
            except CFLimit:
                os.replace(pth + ".bad.png", pth); raise
            if ok: os.remove(pth + ".bad.png"); todo.append(sid)
            else: os.replace(pth + ".bad.png", pth)
        if not todo: return


def audio_ok(path):
    """voice exists, is longer than 0.4 s and is not silent"""
    if not path or not os.path.exists(path): return False
    import numpy as np
    pcm = subprocess.run([ffmpeg(), "-v", "quiet", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "8000", "-"], capture_output=True).stdout
    a = np.frombuffer(pcm, np.int16).astype(float) / 32768
    return len(a) > 3200 and float(np.sqrt((a ** 2).mean())) > .005


def part_ok(path, D, want_sound):
    """the finished shot: right length, sound where a voice is expected, not a black picture"""
    if not os.path.exists(path) or os.path.getsize(path) < 2000: return False, "part file missing"
    dur, w, h, has_a = probe(path)
    if abs(dur - D) > .6: return False, f"length {dur:.1f}s instead of {D:.1f}s"
    if want_sound and not audio_ok(path): return False, "no voice in the shot"
    import numpy as np
    raw = subprocess.run([ffmpeg(), "-v", "quiet", "-ss", f"{D / 2:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=64:36,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    if raw and np.frombuffer(raw, np.uint8).mean() < 10: return False, "black picture"
    return True, ""


def stage_cf_images(P):
    shots = P.load("shots.json"); done = 0; by_id = {s["id"]: s for s in shots}; fresh = []
    print(f"  Cloudflare: scene pictures for {len(shots)} shots (free, automatic) - each checked as soon as it is made")
    try:
        for i, sh in enumerate(shots):
            path = P.p("images", f"{sh['id']}.png")
            if os.path.exists(path): done += 1; continue
            if cf_scene_image(sh["image_prompt"], path, 1000 + sh["scene"]):
                done += 1; fresh.append(sh["id"]); print(f"   picture {done}/{len(shots)}  {sh['id']}")
            if len(fresh) >= 4:
                check_pictures_now(P, fresh, by_id); fresh = []
    finally:
        if fresh:
            try: check_pictures_now(P, fresh, by_id)
            except CFLimit: pass
    return done


def frames_per_shot(n_shots):
    """as smooth as possible (default 4 copies) but fitting the daily free pictures (STUDIO_DAILY_IMAGES, default 180)"""
    want = int(os.getenv("STUDIO_FRAMES", "0")); daily = int(os.getenv("STUDIO_DAILY_IMAGES", "40"))
    if want <= 0: return 0
    if os.getenv("STUDIO_FIT_ONE_DAY", "1") == "1":
        want = max(1, min(want, daily // max(1, n_shots) - 1))
    return want


def budget(n_shots, frames=None):
    frames = frames if frames is not None else frames_per_shot(n_shots)
    daily = int(os.getenv("STUDIO_DAILY_IMAGES", "40")); need = n_shots * (1 + frames)
    days = -(-need // daily)
    print(f"  PICTURE BUDGET: {n_shots} shots x (1 + {frames} flipbook copies) = {need} pictures  |  ~{daily}/day free -> {days} day(s)")
    return need, days


def stage_cf_frames(P, n=None):
    shots = P.load("shots.json"); n = frames_per_shot(len(shots)) if n is None else n; total = 0
    if n <= 0:
        print("  (flipbook copies off - every picture becomes a 'living picture' on this computer instead)"); return
    print(f"  Cloudflare: {n} flipbook frames per shot")
    for sh in shots:
        base = P.p("images", f"{sh['id']}.png")
        if os.getenv("STUDIO_FRAMES") == "0": break
        if os.path.exists(base) and not os.path.exists(P.p("clips", f"{sh['id']}.mp4")):
            got = cf_frames(base, sh, n, 1000 + sh["scene"]); total += got
    print(f"   flipbook frames ready: {total}")


def flipbook_input(P, sid):
    """concat list: base, f1, f2, f3, f2, f1 ... held 1/8 s each for 8 s (old-reel motion); None if no frames"""
    base = P.p("images", f"{sid}.png"); fr = sorted(glob.glob(P.p("images", f"{sid}_f*.png")))
    if not fr: return None
    seq = [base] + fr + fr[-2::-1] if len(fr) > 1 else [base, fr[0]]
    lst = P.p("work", f"{sid}_flip.txt"); lines = []; t = 0.0; i = 0
    while t < 8.0:
        hold = .5 if seq[i % len(seq)] == base else .25            # longer holds + blending = smooth, not jumpy
        lines.append(f"file '{os.path.abspath(seq[i % len(seq)])}'\nduration {hold}\n"); t += hold; i += 1
    lines.append(f"file '{os.path.abspath(seq[(i - 1) % len(seq)])}'\n")
    open(lst, "w").writelines(lines)
    return lst


# ------------------------------------------------------------------ QC + final
def ffmpeg():
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def probe(path):
    e = subprocess.run([ffmpeg(), "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", e); dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
    v = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", e); w, h = (int(v.group(1)), int(v.group(2))) if v else (0, 0)
    return dur, w, h, "Audio:" in e


def style_check(clip, start_img):
    """Gemini looks at the start picture and the middle of the clip: still 2D? same characters?"""
    key = os.getenv("GEMINI_API_KEY")
    if not key: return None
    import base64, requests
    mid = clip + ".mid.jpg"
    subprocess.run([ffmpeg(), "-y", "-v", "quiet", "-ss", "4", "-i", clip, "-frames:v", "1", "-vf", "scale=640:-2", mid])
    parts = []
    for f in (start_img, mid):
        if os.path.exists(f): parts.append({"inline_data": {"mime_type": "image/jpeg" if f.endswith("jpg") else "image/png", "data": base64.b64encode(open(f, "rb").read()).decode()}})
    parts.append({"text": 'Picture 1 is the approved 2D starting frame, picture 2 is from the animated clip. JSON only: '
                          '{"still_2d_cartoon": true/false, "same_characters": true/false, "problem": "short or empty"}'})
    try:
        r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent", headers={"x-goog-api-key": key},
                          json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}}, timeout=120)
        return parse(r.json()["candidates"][0]["content"]["parts"][0]["text"]) if r.status_code == 200 else None
    except Exception:
        return None
    finally:
        if os.path.exists(mid): os.remove(mid)


def qc(P):
    shots = P.load("shots.json"); rep, failed = [], []
    for s in shots:
        c = P.p("clips", f"{s['id']}.mp4")
        if not os.path.exists(c): rep.append(f"{s['id']}: MISSING"); continue
        dur, w, h, audio = probe(c); probs = []
        if not 7.0 <= dur <= 9.0: probs.append(f"length {dur:.1f}s (need 8)")
        if h and abs(w / h - 16 / 9) > .05: probs.append(f"not 16:9 ({w}x{h})")
        if s["kind"] == "dialogue" and not audio: probs.append("no sound for a dialogue clip")
        sc = style_check(c, P.p("images", f"{s['id']}.png"))
        if sc is not None:
            if not sc.get("still_2d_cartoon", True): probs.append("STYLE: not 2D cartoon any more -> STYLE FIX")
            if not sc.get("same_characters", True): probs.append("characters changed: " + str(sc.get("problem", "")))
        rep.append(f"{s['id']}: " + ("PASS" if not probs else "FAIL - " + "; ".join(probs)))
        if probs: failed.append(s["id"])
    P.save("qc_failed.json", failed)
    open(P.p("QC_REPORT.txt"), "w", encoding="utf-8").write("\n".join(rep) + f"\n\nFAILED: {len(failed)}  ->  python studio.py redo")
    print("\n".join(rep[-15:])); print(f"FAILED: {len(failed)}")


def emotion_params(base_rate, base_pitch, emotion):
    def add(a, b, unit):
        return f"{int(a.replace(unit, '').replace('+', '')) + int(b.replace(unit, '').replace('+', '')):+d}{unit}"
    r, p_, v, _ = EMOTIONS.get(emotion or "warm", EMOTIONS["warm"])
    return add(base_rate, r, "%"), add(base_pitch, p_, "Hz"), v


def narrator_audio(P, sid, text, emotion="warm"):
    out = P.p("audio", f"{sid}_narration.mp3")
    if os.path.exists(out) and os.path.getsize(out) > 2000: return out
    try:
        if gemini_voice_on(P) and gemini_tts(text, "narrator", emotion, out, P): return out
        import edge_tts
        v, rate, pitch = NARRATOR["edge"]; rate, pitch, vol = emotion_params(rate, pitch, emotion)
        asyncio.run(edge_tts.Communicate(text, v, rate=rate, pitch=pitch, volume=vol).save(out))
        if os.path.getsize(out) > 2000: return out
        raise RuntimeError("empty audio")
    except Exception as e:
        if os.path.exists(out): os.remove(out)                     # never keep a half-made file
        print(f"  ({sid}: narrator voice could not be made: {str(e)[:60]})"); return None


GEM_VOICES = {"narrator": "Charon", "male": ["Orus", "Fenrir", "Puck", "Iapetus"], "female": ["Kore", "Leda", "Aoede", "Callirrhoe"]}


def gemini_voice_on(P):
    """STUDIO_VOICE=gemini: Gemini acts every line (most natural). Decided once per project; if it fails at the start the
    whole video uses the Microsoft voices instead - the voice never switches in the middle."""
    if os.getenv("STUDIO_VOICE", "microsoft").lower() != "gemini" or not os.getenv("GEMINI_API_KEY"): return False
    st = P.load("voice_mode.json", {})
    return st.get("mode", "gemini") == "gemini"


def gemini_tts(text, who, emotion, out, P=None):
    import requests, base64, wave
    key = os.getenv("GEMINI_API_KEY"); feel = {"warm": "warmly", "suspense": "in a low, slow, suspenseful voice", "sad": "sadly, slowly",
            "joy": "happily", "angry": "angrily", "shock": "in shock", "wise": "calmly and wisely", "tension": "tensely"}.get(emotion, "warmly")
    if who == "narrator": voice, style = GEM_VOICES["narrator"], "a warm, natural Indian storyteller telling a village story to a family"
    else:
        vp = character_voice(P, who) if P else ("hi-IN-MadhurNeural", "", "")
        pool = GEM_VOICES["female" if "Swara" in vp[0] else "male"]; voice = pool[sum(map(ord, who)) % len(pool)]
        style = f"the character {who} in a Hindi village story"
    body = {"contents": [{"parts": [{"text": f"Speak this Hindi line as {style}, {feel}, natural and human, with natural pauses: {text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for model in ("gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"):
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=120)
            if r.status_code != 200: continue
            pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            wav = out + ".wav"
            with wave.open(wav, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            subprocess.run([ffmpeg(), "-y", "-v", "quiet", "-i", wav, out], check=True); os.remove(wav)
            return True
        except Exception:
            continue
    if P is not None or who == "narrator":                    # Gemini failed -> whole project switches to Microsoft voices
        if P is not None:
            P.save("voice_mode.json", {"mode": "microsoft"})
            for f in glob.glob(P.p("audio", "*.mp3")): os.remove(f)                          # remake every line in ONE voice family
        print("   (Gemini voice not available - the whole video uses the Microsoft voices)")
    return False


def character_voice(P, name):
    """(voice, rate, pitch) for a character: male -> Madhur, female -> Swara, child -> higher; each person a different pitch"""
    bible = P.load("bible.json") or {"characters": []}
    chars = bible.get("characters", []); c = next((x for x in chars if x.get("name") == name), {}); i = chars.index(c) if c in chars else 0
    v = c.get("voice", {}) if isinstance(c.get("voice"), dict) else {}
    info = " ".join(str(x) for x in (c.get("gender", ""), v.get("gender", ""), c.get("age", ""), v.get("age", ""), c.get("role", ""))).lower()
    female = any(w in info for w in ("female", "woman", "girl", "wife", "mother", "aunt", "महिला", "स्त्री", "लड़की", "माँ", "पत्नी"))
    child = any(w in info for w in ("child", "boy", "girl", "kid", "son", "बच्च", "बेटा", "बेटी")) or any(ch.isdigit() and int(ch) < 2 for ch in str(c.get("age", ""))[:1])
    shift = [0, 12, -10, 20, -18, 6][i % 6]
    if female: return ("hi-IN-SwaraNeural", "+0%", f"{(18 if child else 0) + shift:+d}Hz")
    return ("hi-IN-MadhurNeural", "+4%" if child else "+0%", f"{(30 if child else 0) + shift:+d}Hz")


def line_audio(P, s):
    """narration -> narrator; dialogue -> that character's voice. Returns the mp3 path or None"""
    said = s.get("spoken") or s["text"]; emo = s.get("emotion", "warm")
    if s["kind"] == "narration" or not s.get("speaker"):
        return narrator_audio(P, s["id"], said, emo)
    out = P.p("audio", f"{s['id']}_line.mp3")
    if os.path.exists(out) and os.path.getsize(out) > 2000: return out
    try:
        if gemini_voice_on(P) and gemini_tts(said, s["speaker"], emo, out, P): return out
        import edge_tts
        v, rate, pitch = character_voice(P, s["speaker"]); rate, pitch, vol = emotion_params(rate, pitch, emo)
        asyncio.run(edge_tts.Communicate(said, v, rate=rate, pitch=pitch, volume=vol).save(out))
        if os.path.getsize(out) > 2000: return out
        raise RuntimeError("empty audio")
    except Exception as e:
        if os.path.exists(out): os.remove(out)
        print(f"  ({s['id']}: voice could not be made: {str(e)[:60]})"); return None


def subtitle_png(P, sid, who, text):
    from PIL import Image, ImageDraw, ImageFont
    font = None
    for f in ("C:/Windows/Fonts/Nirmala.ttc", "C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/mangal.ttf",
              "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"):
        try: font = ImageFont.truetype(f, 36, layout_engine=ImageFont.Layout.RAQM); break
        except OSError: continue
    im = Image.new("RGBA", (1280, 720), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    tw = d.textlength(text, font=font); x = max(20, (1280 - tw) / 2)
    d.rounded_rectangle((x - 20, 640, min(1260, x + tw + 20), 700), 16, fill=(10, 10, 20, 170))
    d.text((x, 646), text, font=font, fill=(255, 255, 255))
    p = P.p("work", f"{sid}_sub.png"); im.save(p); return p


def burn_ass(P, shots, video, durations=None):
    """Hindi subtitles through ffmpeg/libass (HarfBuzz shaping) - used when Pillow cannot shape Hindi"""
    def ts(t): return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    font = "Nirmala UI" if os.name == "nt" else "Noto Sans Devanagari"
    fontsdir = "C:/Windows/Fonts" if os.name == "nt" else "/usr/share/fonts/truetype/noto"
    lines = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1280", "PlayResY: 720", "WrapStyle: 0", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
             f"Style: Default,{font},36,&H00FFFFFF,&H00000000,&H96000000,1,3,2,0,2,90,90,34", "", "[Events]",
             "Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Text"]
    t = 0.0
    for k, s in enumerate(shots):
        d = durations[k] if durations and k < len(durations) else 8.0
        who = "" if s["kind"] == "narration" or not s.get("speaker") else "{\\c&H4DD3FF&}" + s["speaker"] + ": {\\c&HFFFFFF&}"
        lines.append(f"Dialogue: 0,{ts(t + .15)},{ts(t + d - .15)},Default,0,0,0,{who}{s['text'].replace(chr(10), ' ')}"); t += d
    ass = P.p("work", "subs.ass"); open(ass, "w", encoding="utf-8").write("\n".join(lines))
    tmp = video.replace(".mp4", "_subs.mp4")
    esc = lambda p: p.replace("\\", "/").replace(":", "\\:")
    r = subprocess.run([ffmpeg(), "-y", "-v", "error", "-i", video, "-vf", f"ass='{esc(ass)}':fontsdir='{esc(fontsdir)}':shaping=complex",
                        "-c:v", "libx264", "-crf", "20", "-c:a", "copy", tmp], capture_output=True, text=True)
    if r.returncode == 0 and os.path.getsize(tmp) > 1000:
        os.replace(tmp, video); print("  Hindi subtitles added (ffmpeg)")
    else:
        print("  (subtitles could not be added:", (r.stderr or "")[-160:], ")")


def living_assets(P):
    """made once per project: a soft mask (bottom = foreground) and an 8-second floating-dust layer"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    mask = P.p("work", "parallax_mask.png")
    if not os.path.exists(mask):
        y = np.linspace(0, 1, 1440)[:, None]; m = np.clip((y - .42) / .25, 0, 1)
        Image.fromarray((np.repeat(m, 2560, 1) * 255).astype(np.uint8)).save(mask)
    dust = P.p("work", "dust.mov")
    if not os.path.exists(dust):
        import random
        rnd = random.Random(3); parts = [[rnd.uniform(0, 1280), rnd.uniform(0, 720), rnd.uniform(1.2, 3.2), rnd.uniform(-.25, .25),
                                          rnd.uniform(-.35, -.08), rnd.uniform(.5, 1)] for _ in range(70)]
        p = subprocess.Popen([ffmpeg(), "-y", "-v", "quiet", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "1280x720", "-r", "24", "-i", "-",
                              "-c:v", "qtrle", dust], stdin=subprocess.PIPE)
        for f in range(192):
            im = Image.new("RGBA", (1280, 720), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            for q in parts:
                x, yy = (q[0] + q[3] * f) % 1280, (q[1] + q[4] * f) % 720
                a = int(110 * q[5] * (0.6 + 0.4 * math.sin(f * .08 + q[0])))
                d.ellipse((x - q[2], yy - q[2], x + q[2], yy + q[2]), fill=(255, 240, 210, a))
            p.stdin.write(im.filter(ImageFilter.GaussianBlur(.8)).tobytes())
        p.stdin.close(); p.wait()
    return mask, dust


def hindi_ok():
    """Hindi needs a shaping engine (raqm) so matras join correctly; without it subtitles would look broken"""
    try:
        from PIL import features; return features.check("raqm")
    except Exception:
        return False


def picture_for(P, shots, i):
    """own picture, else the nearest shot's picture (same scene first) so the narration of every shot stays in the video"""
    own = P.p("images", f"{shots[i]['id']}.png")
    if os.path.exists(own): return own, False
    order = sorted(range(len(shots)), key=lambda j: (shots[j]["scene"] != shots[i]["scene"], abs(j - i)))
    for j in order:
        p = P.p("images", f"{shots[j]['id']}.png")
        if os.path.exists(p): return p, True
    return None, False


def final(P, subtitles=True, _again=False):
    shots = P.load("shots.json"); ff = ffmpeg(); parts = []; borrowed = 0; durations = []
    mode_at_start = P.load("voice_mode.json", {}).get("mode")
    ass_subs = False
    if subtitles and not hindi_ok():
        ass_subs = True; subtitles = False                     # burn them later with ffmpeg (it joins Hindi matras correctly)
    for idx, s in enumerate(shots):
        clip = P.p("clips", f"{s['id']}.mp4")
        img, reused = picture_for(P, shots, idx); borrowed += reused
        img = img or P.p("images", f"{s['id']}.png")
        print(f"  video part {idx + 1}/{len(shots)}  {s['id']}" + ("  (picture of a nearby shot)" if reused else ""), flush=True)
        part = P.p("work", f"{s['id']}_part.mp4")
        voice_file = None if os.path.exists(clip) else line_audio(P, s)
        for attempt in (1, 2):                                       # LIVE voice check
            if os.path.exists(clip) or audio_ok(voice_file): break
            live_log(P, f"{s['id']} voice missing/silent -> making it again (try {attempt})")
            for f in glob.glob(P.p("audio", f"{s['id']}_*.mp3")): os.remove(f)
            voice_file = line_audio(P, s)
        rest = EMOTIONS.get(s.get("emotion", "warm"), EMOTIONS["warm"])[3] * float(P.load("settings.json", {}).get("pause_scale", 1.0))
        D = 8.0 if os.path.exists(clip) else (min(13.0, max(1.8, probe(voice_file)[0] + 0.2 + rest)) if voice_file else
                                               min(8.0, max(3.0, 0.42 * len(s["text"].split()) + 0.8)))
        durations.append(D)
        flip = None if os.path.exists(clip) else flipbook_input(P, s["id"])
        src = ["-i", clip] if os.path.exists(clip) else (["-f", "concat", "-safe", "0", "-i", flip] if flip else
                                                          (["-loop", "1", "-t", f"{D:.2f}", "-i", img] if os.path.exists(img) else None))
        if not src: continue
        cmd = [ff, "-y", "-v", "quiet"] + src
        n = 1; vlast = "[v0]"
        if os.path.exists(clip):
            vf = "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=24,setsar=1[v0]"
        elif flip:                                                    # flipbook: frames blend smoothly + slow push-in
            vf = ("[0:v]scale=2560:1440:force_original_aspect_ratio=increase,crop=2560:1440,fps=8,"
                  "framerate=fps=24:interp_start=0:interp_end=255:scene=100,"
                  "zoompan=z='1+0.0006*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=24,setsar=1[v0]")
        else:                                                         # LIVING PICTURE: parallax layers + floating dust + soft fades
            mask, dust = living_assets(P)
            cmd += ["-i", dust]; n_dust = n; n += 1
            moves = [("1.02+0.0006*on", "iw/2-(iw/zoom/2)+on*0.5", "ih/2-(ih/zoom/2)"),           # push in, drift right
                     ("1.12-0.0005*on", "iw/2-(iw/zoom/2)-on*0.4", "ih/2-(ih/zoom/2)"),           # pull out, drift left
                     ("1.06", f"(iw-iw/zoom)*on/{int(D * 24)}", "ih/2-(ih/zoom/2)"),                        # slow pan left -> right
                     ("1.03+0.0005*on", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)-on*0.3")]           # push in, tilt up
            z, x, y = moves[sum(map(ord, s["id"])) % len(moves)]
            vf = ("[0:v]scale=2560:1440:force_original_aspect_ratio=increase,crop=2560:1440,fps=24,"
                  f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s=1280x720:fps=24[pm];"
                  f"[{n_dust}:v]format=rgba[du];[pm][du]overlay=0:0:format=auto,"
                  f"fade=t=in:st=0:d=0.3,fade=t=out:st={D - 0.3:.2f}:d=0.3,format=yuv420p,setsar=1[v0]")
        if subtitles:
            cmd += ["-i", subtitle_png(P, s["id"], s.get("speaker"), s["text"])]; vf += f";{vlast}[{n}:v]overlay=0:0[v1]"; vlast = "[v1]"; n += 1
        has_audio = os.path.exists(clip) and probe(clip)[3]
        nar = None if has_audio and s["kind"] == "dialogue" else line_audio(P, s)
        if nar:
            cmd += ["-i", nar]
            af = (f"[0:a]volume=0.35[a0];[a0][{n}:a]amix=inputs=2:duration=first[aout]" if has_audio else f"[{n}:a]apad[aout]")
            amap = "[aout]"
        elif has_audio:
            af, amap = "", "0:a"
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono"]; af, amap = "", f"{n}:a"
        fc = vf + (";" + af if af else "")
        cmd += ["-filter_complex", fc, "-map", vlast, "-map", amap, "-t", f"{D:.2f}", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-ar", "24000", "-ac", "1", part]
        if subprocess.run(cmd).returncode != 0:                       # one bad file must not stop the whole video
            print(f"  ({s['id']}: could not be joined - using the plain picture/clip instead)")
            simple = [ff, "-y", "-v", "quiet"] + src + ["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-map", "0:v", "-map", "1:a",
                      "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=24,setsar=1", "-t", f"{D:.2f}",
                      "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-ar", "24000", "-ac", "1", part]
            if subprocess.run(simple).returncode != 0: continue
        good, why = part_ok(part, D, bool(voice_file) or os.path.exists(clip))       # LIVE part check
        if not good:
            live_log(P, f"{s['id']} video part: {why} -> making this shot again")
            if subprocess.run(cmd).returncode != 0 or not part_ok(part, D, bool(voice_file) or os.path.exists(clip))[0]:
                live_log(P, f"{s['id']} still not right - kept, the Video Doctor will look again")
        parts.append(part)
    if P.load("voice_mode.json", {}).get("mode") != mode_at_start and not _again:
        print("  The voice family changed during the video - making it again so ONE narrator voice is used throughout")
        return final(P, subtitles, _again=True)
    if not parts:
        print("\n  No pictures yet, so there is nothing to put in a video. Run RUN_ALL.bat again (or tomorrow) - it continues.")
        return False
    lst = P.p("work", "parts.txt"); open(lst, "w").writelines(f"file '{os.path.abspath(x)}'\n" for x in parts)
    out = P.p("FINAL.mp4")
    subprocess.run([ff, "-y", "-v", "quiet", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
    if ass_subs:
        burn_ass(P, shots, out, durations)
    if borrowed: print(f"  {borrowed} shot(s) used a nearby picture (their own was not made - free limit)")
    made = sum(os.path.exists(P.p("clips", f"{s['id']}.mp4")) for s in shots)
    flips = sum(1 for s in shots if not os.path.exists(P.p("clips", f"{s['id']}.mp4")) and glob.glob(P.p("images", f"{s['id']}_f*.png")))
    print(f"FINAL -> {out}   ({len(parts)} shots: {made} Flow clips, {flips} flipbook, {len(parts) - made - flips} storybook)")


def status(P):
    shots = P.load("shots.json") or []; bible = P.load("bible.json") or {"characters": []}
    def n(folder, ext): return len(glob.glob(P.p(folder, "*" + ext)))
    print(f"PROJECT {P.dir}\n 1-3 story: {'OK' if P.load('story.json') else '-'}   characters: {len(bible['characters'])}\n"
          f" 4 sheets: {n('characters', '.png')}/{len(bible['characters'])}   5 images: {n('images', '.png')}/{len(shots)}   "
          f"6 clips: {n('clips', '.mp4')}/{len(shots)}   final: {'OK' if os.path.exists(P.p('FINAL.mp4')) else '-'}")


# ------------------------------------------------------------------ VIDEO DOCTOR: check the finished video, fix, re-make, report
LOOK_RULES = ("You check pictures for a Hindi 2D cartoon moral story set in a RURAL INDIAN VILLAGE. Characters: {bible}\n"
              "For each picture list only REAL problems: plain white/grey/empty background with no place visible, looks like a character "
              "sheet or people just standing for a design (not a story scene), heads or faces cut off by the picture edge, western/modern "
              "clothes (suit, tie, jeans), city or foreign setting, written text/letters/signs, broken anatomy (extra limbs, melted face), "
              "photo-realistic or 3D style instead of 2D cartoon. "
              'JSON only: {{"pictures": [{{"n": 1, "ok": true, "problems": []}}]}}')


def groq_look(pictures, bible_text):
    """AI eye with Groq's free vision model (up to 4 pictures per request); {} if no key / no answer"""
    import requests, base64, io
    key = os.getenv("GROQ_API_KEY")
    if not key or not pictures: return {}
    from PIL import Image
    out, answered = {}, False
    for k in range(0, len(pictures), 4):
        chunk = pictures[k:k + 4]; content = [{"type": "text", "text": LOOK_RULES.format(bible=bible_text[:1200])}]
        for i, pth in enumerate(chunk, 1):
            im = Image.open(pth).convert("RGB"); im.thumbnail((512, 512)); b = io.BytesIO(); im.save(b, "JPEG", quality=70)
            content += [{"type": "text", "text": f"Picture {i}:"},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()}}]
        for model in ("meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"):
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=120,
                                  json={"model": model, "messages": [{"role": "user", "content": content}], "temperature": 0.1,
                                        "response_format": {"type": "json_object"}})
                if r.status_code != 200: continue
                d = parse(r.json()["choices"][0]["message"]["content"]) or {}; answered = True
                for it in d.get("pictures", []) if isinstance(d, dict) else []:
                    if not isinstance(it, dict): continue
                    n = int(it.get("n", 0) or 0)
                    if 1 <= n <= len(chunk) and not it.get("ok", True) and it.get("problems"):
                        out[chunk[n - 1]] = [str(x) for x in it["problems"]][:3]
                break
            except Exception:
                continue
    return out if answered else None


def gemini_look(pictures, bible_text):
    """AI eye on the pictures: Groq first (free vision), Gemini only if Groq can't answer"""
    g = groq_look(pictures, bible_text)
    if g is not None: return g
    import requests, base64, io
    key = os.getenv("GEMINI_API_KEY")
    if not key or not pictures: return {}
    from PIL import Image
    out = {}
    for k in range(0, len(pictures), 6):
        chunk = pictures[k:k + 6]; parts = []
        for i, pth in enumerate(chunk, 1):
            im = Image.open(pth).convert("RGB"); im.thumbnail((512, 512)); b = io.BytesIO(); im.save(b, "JPEG", quality=70)
            parts += [{"text": f"Picture {i}:"}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}]
        parts.append({"text": LOOK_RULES.format(bible=bible_text[:1500])})
        for model in ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"):
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key},
                                  json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}}, timeout=120)
                if r.status_code != 200: continue
                d = parse(r.json()["candidates"][0]["content"]["parts"][0]["text"]) or {}
                for it in d.get("pictures", []):
                    n = int(it.get("n", 0))
                    if 1 <= n <= len(chunk) and not it.get("ok", True) and it.get("problems"):
                        out[chunk[n - 1]] = [str(x) for x in it["problems"]][:3]
                break
            except Exception:
                continue
    return out


def check_video(P):
    """returns a list of problems: (kind, shot_id, detail)"""
    shots = P.load("shots.json"); probs = []; ff = ffmpeg(); out = P.p("FINAL.mp4")
    if not os.path.exists(out): return [("video", "-", "FINAL.mp4 missing")]
    for s in shots:
        if not os.path.exists(P.p("clips", f"{s['id']}.mp4")):
            a = line_audio(P, s)
            if not a or probe(a)[0] < .5: probs.append(("voice", s["id"], "no voice for this line"))
            if not os.path.exists(P.p("images", f"{s['id']}.png")): probs.append(("picture", s["id"], "own picture missing (a nearby one was used)"))
    import numpy as np
    pcm = subprocess.run([ff, "-v", "quiet", "-i", out, "-f", "s16le", "-ac", "1", "-ar", "8000", "-"], capture_output=True).stdout
    a = np.frombuffer(pcm, np.int16).astype(float) / 32768; w = 4000
    lv = np.array([np.sqrt((a[i:i + w] ** 2).mean()) for i in range(0, max(0, len(a) - w), w)] or [0])
    share = float((lv > .01).mean()); quiet_run = 0; longest = 0; at = 0
    for k, x in enumerate(lv):
        quiet_run = quiet_run + 1 if x <= .01 else 0
        if quiet_run > longest: longest, at = quiet_run, k
    if share < .6: probs.append(("sound", "-", f"only {share:.0%} of the video has voice"))
    if longest * .5 > 2.5:
        t = (at - longest + 1) * .5
        probs.append(("silence", "-", f"{longest * .5:.1f} s of silence at {int(t // 60)}:{int(t % 60):02d}"))
    raw = subprocess.run([ff, "-v", "quiet", "-i", out, "-vf", "fps=2,scale=64:36,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 36, 64).astype(float) if raw else np.zeros((1, 36, 64))
    dark = (fr.mean(axis=(1, 2)) < 12); run = 0; worst = 0
    for x in dark:
        run = run + 1 if x else 0; worst = max(worst, run)
    if worst >= 3: probs.append(("black", "-", f"{worst / 2:.1f} s of black screen"))
    bible = P.load("bible.json") or {"characters": []}
    btxt = "; ".join(f"{c.get('name')}: {c.get('look', '')}" for c in bible.get("characters", []))
    pics = [P.p("images", f"{s['id']}.png") for s in shots if os.path.exists(P.p("images", f"{s['id']}.png"))]
    seen = P.load("checked_pictures.json", [])
    for pth, pr in gemini_look([x for x in pics if os.path.basename(x) not in seen], btxt).items():
        probs.append(("look", os.path.basename(pth)[:-4], "; ".join(pr)))
    P.save("checked_pictures.json", sorted(set(seen) | {os.path.basename(x) for x in pics}))
    return probs


def fix_video(P, probs):
    """fix what can be fixed; returns how many fixes were made"""
    shots = {s["id"]: s for s in P.load("shots.json")}; fixed = 0
    if any(k in ("silence", "sound") for k, _, _ in probs):
        st = P.load("settings.json", {}); old = float(st.get("pause_scale", 1.0))
        if old > .35:
            st["pause_scale"] = round(old * .6, 2); P.save("settings.json", st); fixed += 1
            print(f"   shorter pauses after lines (x{st['pause_scale']})")
    for kind, sid, detail in probs:
        s = shots.get(sid)
        if kind == "voice" and s:
            for f in glob.glob(P.p("audio", f"{sid}_*.mp3")): os.remove(f)
            if line_audio(P, s): fixed += 1
        elif kind in ("picture", "look") and s and cf_on():
            pth = P.p("images", f"{sid}.png"); old = pth + ".old.png"
            if os.path.exists(pth): os.replace(pth, old)
            try:
                extra = f" IMPORTANT, AVOID: {detail}." if kind == "look" else ""
                if cf_scene_image(s["image_prompt"] + extra, pth, 2000 + len(detail)):
                    fixed += 1; checked = set(P.load("checked_pictures.json", [])); checked.discard(f"{sid}.png"); P.save("checked_pictures.json", sorted(checked))
                    if os.path.exists(old): os.remove(old)
                elif os.path.exists(old): os.replace(old, pth)
            except CFLimit:
                if os.path.exists(old): os.replace(old, pth)
                print("   (Cloudflare limit - this picture is fixed tomorrow)"); break
    return fixed


def doctor(P, subtitles=True, rounds=2):
    """check -> fix -> make again, until clean (2 rounds); writes QC_REPORT.txt"""
    report = []
    for r in range(1, rounds + 2):
        probs = check_video(P)
        report.append(f"CHECK {r}: {len(probs)} problem(s)"); report += [f"   [{k}] {sid}: {d}" for k, sid, d in probs]
        print(f"  VIDEO DOCTOR check {r}: {len(probs)} problem(s)")
        for k, sid, d in probs[:8]: print(f"     - [{k}] {sid}: {d}")
        if not probs:
            report.append("RESULT: CORRECTED & COMPLETE"); break
        if r > rounds:
            report.append("RESULT: COMPLETE WITH NOTES (see above - nothing more could be fixed today)"); break
        n = fix_video(P, probs)
        report.append(f"   fixed: {n}")
        if n == 0:
            report.append("RESULT: COMPLETE WITH NOTES (problems could not be fixed automatically today)"); break
        print(f"  fixed {n} - making the video again"); final(P, subtitles)
    live = open(P.p("LIVE_QC.txt"), encoding="utf-8").read() if os.path.exists(P.p("LIVE_QC.txt")) else "(nothing needed fixing while making)\n"
    open(P.p("QC_REPORT.txt"), "w", encoding="utf-8").write("FIXED WHILE MAKING:\n" + live + "\nFINAL CHECK:\n" + "\n".join(report))
    print("\n  " + report[-1]); return report[-1]


def split_pack(P):
    """from a pack: IMAGE_PROMPTS.txt (all picture prompts, one under the other) + FULL_STORY.txt (whole story, no parts)
    + FULL_VOICE.mp3 (whole story in one narrator voice, parts joined with a natural short pause)"""
    pk = P.load("pack.json")
    if not pk: sys.exit("no pack.json in " + P.dir)
    parts = pk["parts"]
    clean = lambda t: re.sub(r"\s*,?\s*(with\s+)?(the\s+|a\s+)?(text|words?|caption|title|letters?)\s+(appearing|written|shown|showing)[^.,;]*?(:\s*['\"][^'\"]*['\"])?(?=[.,;])", "", str(t), flags=re.I)
    imgs = [f"{pk.get('title', '')} - IMAGE PROMPTS ({len(parts)})", "=" * 60, ""]
    for k, x in enumerate(parts, 1):
        imgs += [f"IMAGE {k:02d}", clean(x.get("image_prompt", "")).replace("..", "."), ""]
    open(P.p("IMAGE_PROMPTS.txt"), "w", encoding="utf-8").write("\n".join(imgs))
    story = [pk.get("title", ""), ""] + [str(x["narration"]).strip() for x in parts] + ["", f"सीख: {pk.get('moral', '')}"]
    open(P.p("FULL_STORY.txt"), "w", encoding="utf-8").write("\n\n".join(story))
    # one voice for the whole story: the part voices joined with a 0.6 s breath (made if missing)
    ff = ffmpeg(); files = []
    for k, x in enumerate(parts, 1):
        a = P.p("audio", f"part_{k:02d}.mp3")
        if not (os.path.exists(a) and os.path.getsize(a) > 2000):
            try:
                import edge_tts
                v, rate, pitch = NARRATOR["edge"]; rate, pitch, vol = emotion_params(rate, pitch, x.get("emotion", "warm"))
                asyncio.run(edge_tts.Communicate(str(x["narration"]), v, rate=rate, pitch=pitch, volume=vol).save(a))
            except Exception as e:
                print(f"  (part {k}: voice not made: {str(e)[:50]})"); continue
        files.append(a)
    if files:
        gap = P.p("work", "gap.wav")
        subprocess.run([ff, "-y", "-v", "quiet", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.6", gap])
        lst = P.p("work", "voice_list.txt")
        open(lst, "w", encoding="utf-8").writelines(f"file '{os.path.abspath(f)}'\nfile '{os.path.abspath(gap)}'\n" for f in files)
        out = P.p("FULL_VOICE.mp3")
        subprocess.run([ff, "-y", "-v", "quiet", "-f", "concat", "-safe", "0", "-i", lst, "-ar", "24000", "-ac", "1", "-b:a", "128k", out])
        print(f"  FULL_VOICE.mp3  ({probe(out)[0] / 60:.1f} min)")
    print(f"  IMAGE_PROMPTS.txt + FULL_STORY.txt ready in {P.dir}")
    if os.name == "nt" and os.getenv("STUDIO_UNATTENDED") != "1": os.startfile(P.dir)


def latest_pack():
    packs = sorted(glob.glob(os.path.join(HERE, "projects", "*_pack")))
    if not packs: sys.exit("No pack yet - run MAKE_8MIN_PACK.bat first")
    return Project(packs[-1])


def pack_images(P=None):
    """Gemini opens; the helper copies each picture prompt; you paste + download; each picture is saved as part_XX.png"""
    P = P or latest_pack(); pk = P.load("pack.json")
    items = [{"title": f"PICTURE {k:02d} of {len(pk['parts'])}", "prompt": x["image_prompt"], "dest": P.p("images", f"part_{k:02d}.png")}
             for k, x in enumerate(pk["parts"], 1)]
    helper(items, GEMINI_URL, "image")
    have = len(glob.glob(P.p("images", "part_*.png"))); print(f"  pictures ready: {have} of {len(items)}")


def pack_video(P=None, subtitles=True):
    """storybook video from the pack: every part = its picture with a smooth camera move + dust + fades, its voice, Hindi subtitles"""
    P = P or latest_pack(); pk = P.load("pack.json"); parts = pk["parts"]
    if not glob.glob(P.p("images", "part_*.png")): sys.exit("No pictures yet - run PACK_IMAGES.bat first")
    shots = []
    for k, x in enumerate(parts, 1):
        img = P.p("images", f"part_{k:02d}.png")
        if os.path.exists(img):                                     # pictures from Gemini come in any size -> clean 16:9
            from PIL import Image as _I
            im = _I.open(img)
            if im.size != (1280, 720):
                import io as _io; b = _io.BytesIO(); im.convert("RGB").save(b, "PNG"); clean_frame(b.getvalue(), img)
        sid = f"S{(k - 1) // 4 + 1:02d}_SH{k:02d}"
        a = P.p("audio", f"part_{k:02d}.mp3"); b = P.p("audio", f"{sid}_narration.mp3")
        if os.path.exists(a) and not os.path.exists(b): shutil.copy(a, b)
        if os.path.exists(img) and not os.path.exists(P.p("images", f"{sid}.png")): shutil.copy(img, P.p("images", f"{sid}.png"))
        shots.append({"id": sid, "kind": "narration", "speaker": None, "scene": (k - 1) // 4 + 1, "text": str(x["narration"]),
                      "emotion": x.get("emotion", "warm"), "image_prompt": x.get("image_prompt", "")})
    P.save("shots.json", shots)
    if not P.load("bible.json"): P.save("bible.json", {"characters": pk.get("characters", [])})
    res = final(P, subtitles)
    if res is not False: doctor(P, subtitles)
    if os.name == "nt" and os.getenv("STUDIO_UNATTENDED") != "1": os.startfile(P.dir)


# ------------------------------------------------------------------ 30-SECOND PACK: story in 30-second parts + one picture prompt each
def make_pack(minutes=8.0, seg=30, voices=True):
    """best story -> N parts of `seg` seconds (narration ~2.3 words/s) -> one picture prompt + motion prompt per part ->
    PACK.txt (+ narration mp3 per part). For making each part yourself in any image-to-video tool."""
    P = Project(os.path.join(HERE, "projects", time.strftime("%Y%m%d_%H%M") + "_pack"))
    stage1(P, True); idea = P.load("chosen.json")
    n = int(round(minutes * 60 / seg)); words = int(seg * 2.3)
    d = ask(f"""Write the Hindi moral story "{idea['title']}" ({json.dumps(idea, ensure_ascii=False)}) for a {minutes:.0f}-minute narrated 2D
cartoon video, as EXACTLY {n} consecutive parts of {seg} seconds each. The story flows from part 1 to part {n}: strong hook in part 1,
characters and village, conflict, rising tension, emotional turn, satisfying ending with the moral in the last part.
Each part: narration of {words - 8} to {words + 8} Hindi words (natural spoken Hindi, Devanagari, storyteller voice, may include a short
line of dialogue in quotes), ONE clear picture moment that matches it, which characters are in it, and continuity to carry forward.
JSON only: {{"title": "...", "moral": "...", "characters": [{{"name": "...", "look": "ONE fixed 2D cartoon design in English: age, body,
face, hair/moustache, exact traditional Indian village clothes with colours (never suits)"}}],
"parts": [{{"n": 1, "narration": "...", "emotion": "warm|suspense|sad|joy|angry|shock|wise|tension", "picture": "English: place, time of day,
what is happening, who is where, expressions", "characters": ["name"], "motion": "English: small movement + camera move for 30 s",
"continuity": "English: what must stay the same in the next part"}}]}}""")
    parts = [x for x in d.get("parts", []) if isinstance(x, dict) and x.get("narration")][:n]
    for x in parts:                                            # each part must really fill its seconds
        c = len(str(x["narration"]).split())
        if not (words - 15 <= c <= words + 15):
            try:
                fix = ask(f'Rewrite this Hindi narration to {words} words (same meaning, natural storyteller Hindi). JSON only: {{"narration": "..."}}\n{x["narration"]}')
                if isinstance(fix, dict) and fix.get("narration"): x["narration"] = fix["narration"]
            except SystemExit:
                pass
    chars = [c for c in d.get("characters", []) if isinstance(c, dict) and c.get("name")]
    looks = {c["name"]: c.get("look", "") for c in chars}
    lines = [f"{d.get('title', idea['title'])}   ({len(parts)} parts x {seg} s = {len(parts) * seg / 60:.1f} min)", "=" * 70,
             "CHARACTERS (same in every picture):"] + [f"  - {k}: {v}" for k, v in looks.items()] + [""]
    for x in parts:
        k = int(x.get("n", parts.index(x) + 1)); t0 = (k - 1) * seg
        who = "; ".join(f"person {i + 1}: {looks.get(nm, '')}" for i, nm in enumerate(x.get("characters", [])) if nm in looks) or "no people"
        x["image_prompt"] = (f"Wide 16:9 cinematic scene from a 2D cartoon movie, full background visible: {x.get('picture', '')}. "
                             f"Rural Indian village, detailed painted background. Characters (full body, whole head inside the frame): {who}. "
                             f"Traditional Indian village clothes only. Continuity from the previous part: {x.get('continuity', '')}. "
                             f"Style: {STYLE_BIBLE} NOT a character sheet, NOT a plain background. No text, no letters.")
        x["video_prompt"] = (f"Animate this 2D cartoon picture for {seg} seconds: {x.get('motion', 'gentle natural movement, slow camera push-in')}. "
                             "Keep characters, faces, clothes and style exactly the same. No new characters, no text.")
        lines += [f"---------------- PART {k:02d}   {t0 // 60}:{t0 % 60:02d} - {(t0 + seg) // 60}:{(t0 + seg) % 60:02d}   [{x.get('emotion', 'warm')}] ----------------",
                  f"NARRATION ({len(str(x['narration']).split())} words):", str(x["narration"]), "",
                  "IMAGE PROMPT:", x["image_prompt"], "", "VIDEO (motion) PROMPT:", x["video_prompt"], ""]
        if voices:
            out = P.p("audio", f"part_{k:02d}.mp3")
            try:
                import edge_tts
                v, rate, pitch = NARRATOR["edge"]; rate, pitch, vol = emotion_params(rate, pitch, x.get("emotion", "warm"))
                asyncio.run(edge_tts.Communicate(str(x["narration"]), v, rate=rate, pitch=pitch, volume=vol).save(out))
                lines.insert(len(lines) - 1, f"VOICE FILE: audio\\part_{k:02d}.mp3  ({probe(out)[0]:.0f} s)")
            except Exception as e:
                print(f"  (part {k}: voice file not made: {str(e)[:50]})")
    lines += ["", f"सीख: {d.get('moral', idea.get('moral', ''))}"]
    P.save("pack.json", {"title": d.get("title"), "moral": d.get("moral"), "characters": chars, "parts": parts})
    open(P.p("PACK.txt"), "w", encoding="utf-8").write("\n".join(lines))
    print(f"\nPACK READY -> {P.p('PACK.txt')}   ({len(parts)} parts)")
    split_pack(P)
    if os.name == "nt" and os.getenv("STUDIO_UNATTENDED") != "1": os.startfile(P.p("PACK.txt"))
    return P


def ask_user(question, default="n"):
    if os.getenv("STUDIO_UNATTENDED") == "1":
        print(question + f" -> {default} (automatic mode)"); return default
    return input(question).strip().lower()


def daily():
    """ROZ AUTOMATIC: for every Cloudflare account (yours = video 1, second = video 2): continue its unfinished story or start a
    new one -> video -> live checks + Video Doctor -> upload if CORRECTED & COMPLETE. Log: daily_log.txt"""
    import argparse as _ap
    os.environ["STUDIO_UNATTENDED"] = "1"
    accounts = [(os.getenv("CLOUDFLARE_ACCOUNT_ID"), os.getenv("CLOUDFLARE_API_TOKEN"))]
    if os.getenv("CLOUDFLARE2_ACCOUNT_ID"): accounts.append((os.getenv("CLOUDFLARE2_ACCOUNT_ID"), os.getenv("CLOUDFLARE2_API_TOKEN")))
    log = open(os.path.join(HERE, "daily_log.txt"), "a", encoding="utf-8")
    def note(x): print(x); log.write(time.strftime("%Y-%m-%d %H:%M ") + x + "\n"); log.flush()
    for slot, (acc, tok) in enumerate(accounts):
        if not acc: continue
        os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"] = acc, tok
        open_ones = [d for d in sorted(glob.glob(os.path.join(HERE, "projects", "*")))
                     if not os.path.exists(os.path.join(d, "FINAL_DONE")) and (Project(d).load("slot.json", {}) or {}).get("slot") == slot]
        a = _ap.Namespace(project=open_ones[-1] if open_ones else None, new=not open_ones, minutes=float(os.getenv("STUDIO_MINUTES", "5")),
                          all=False, no_subtitles=False)
        note(f"VIDEO {slot + 1}: " + (f"continuing {os.path.basename(a.project)}" if a.project else "new story"))
        try:
            run_all(a, slot=slot)
        except SystemExit as e:
            note(f"VIDEO {slot + 1}: stopped - {e}"); continue
        except Exception as e:
            note(f"VIDEO {slot + 1}: ERROR {str(e)[:200]}"); continue
        P = Project(latest_project_for(slot))
        if os.path.exists(P.p("FINAL_DONE")) and os.getenv("STUDIO_AUTO_UPLOAD", "1") == "1":
            try:
                import upload as U
                info = U.upload(P.dir, slot)
                note(f"VIDEO {slot + 1}: " + (f"uploaded {info['url']} ({info['mode']})" if info else "not uploaded (QC not clean)"))
            except SystemExit as e:
                note(f"VIDEO {slot + 1}: upload skipped - {e}")
            except Exception as e:
                note(f"VIDEO {slot + 1}: upload ERROR {str(e)[:200]}")
        else:
            note(f"VIDEO {slot + 1}: not finished today (it continues tomorrow)")
    log.close()


def latest_project_for(slot):
    ds = [d for d in sorted(glob.glob(os.path.join(HERE, "projects", "*"))) if (Project(d).load("slot.json", {}) or {}).get("slot") == slot]
    return ds[-1] if ds else latest_project()


def run_all(a, slot=None):
    """ONE RUN: story -> sheets -> images -> Flow clips -> QC (+ redo once) -> final. Stop any time; run again to continue."""
    folder = a.project or latest_project()
    fresh = a.new or not folder or os.path.exists(os.path.join(folder, "FINAL_DONE"))
    if fresh:
        P = Project(os.path.join(HERE, "projects", time.strftime("%Y%m%d_%H%M") + (f"_v{slot + 1}" if slot is not None else "")))
        if slot is not None: P.save("slot.json", {"slot": slot})
        print("\n=== STEP 1-3: story, characters, voices, shot plan ===")
        stage1(P, True); stage2(P, a.minutes); stage3(P); plan_shots(P)
    else:
        P = Project(folder); print(f"\nContinuing project {P.dir}")
    bible, shots = P.load("bible.json"), P.load("shots.json")
    def count(sub, ext): return len(glob.glob(P.p(sub, "*" + ext)))
    def ask_go(what, have, need):
        if have >= need: return True
        ans = ask_user(f"\n{what}: {have} of {need} done. Continue with the next step anyway? (y = yes, n = stop here): ", "n")
        if ans != "y": print("Stopped. Double-click RUN_ALL.bat again to continue from here."); return False
        return True
    if cf_on():
        complete = True
        try:
            budget(len(P.load("shots.json")))
            print("\n=== STEP 4-5: scene pictures (Cloudflare, automatic) ===")
            pics = stage_cf_images(P)
            print("\n=== STEP 6: flipbook motion frames (Cloudflare, automatic) ===")
            stage_cf_frames(P)
        except CFLimit:
            have = len([f for f in os.listdir(P.p("images")) if "_f" not in f and f.endswith(".png")])
            need = int(os.getenv("STUDIO_MIN_IMAGES", "20"))
            print(f"\nToday's FREE Cloudflare limit is used up. Pictures ready: {have} of {len(P.load('shots.json'))}.")
            if have >= need:
                print(f"  {have} pictures are enough (minimum {need}) -> making the FULL video now; shots without a picture borrow a nearby one.")
            else:
                complete = False
                print(f"  Fewer than {need} pictures. Run RUN_ALL.bat again tomorrow - it continues this story.")
                if ask_user("Make a preview now anyway? (y/n): ", "n") != "y": return
        print("\n=== STEP 9: final video ===")
        if final(P, not a.no_subtitles) is False: return
        print("\n=== STEP 10: VIDEO DOCTOR (check, fix, make again) ===")
        result = doctor(P, not a.no_subtitles)
        if complete:
            open(P.p("FINAL_DONE"), "w").write(time.strftime("%Y-%m-%d %H:%M")); print(f"\nALL DONE -> {P.p('FINAL.mp4')}")
        else:
            print(f"\nPREVIEW made -> {P.p('FINAL.mp4')}  (not finished: run RUN_ALL.bat tomorrow to complete this same story)")
        if os.name == "nt" and os.getenv("STUDIO_UNATTENDED") != "1": os.startfile(P.dir)
        return
    print("\n=== STEP 4: character sheets (Gemini) ===");  stage4(P)
    if not ask_go("Character sheets", count("characters", ".png"), len(bible["characters"])): return
    print("\n=== STEP 5: scene images (Gemini) ===");      stage5(P)
    if not ask_go("Scene images", count("images", ".png"), len(shots)): return
    print("\n=== STEP 6: key Flow clips ===");             stage6(P, all_shots=a.all)
    keys = [s for s in P.load("shots.json") if s.get("key") or a.all]
    made = sum(os.path.exists(P.p("clips", f"{s['id']}.mp4")) for s in keys)
    if not ask_go("Flow clips", made, len(keys)): return
    print("\n=== STEP 7: quality check ===");             qc(P)
    if P.load("qc_failed.json", []):
        print("\n=== STEP 8: redo the failed clips ===");  stage6(P, only=set(P.load("qc_failed.json", []))); qc(P)
    print("\n=== STEP 9: final video ===");               final(P, not a.no_subtitles)
    print("\n=== STEP 10: VIDEO DOCTOR ===");             doctor(P, not a.no_subtitles)
    open(P.p("FINAL_DONE"), "w").write(time.strftime("%Y-%m-%d %H:%M"))
    print(f"\nALL DONE -> {P.p('FINAL.mp4')}")
    if os.name == "nt" and os.getenv("STUDIO_UNATTENDED") != "1": os.startfile(P.dir)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["packimages", "packvideo", "split", "pack", "daily", "upload", "check", "budget", "all", "new", "sheets", "images", "clips", "qc", "redo", "final", "status", "plan"])
    ap.add_argument("--new", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--minutes", type=float, default=5); ap.add_argument("--project"); ap.add_argument("--auto", action="store_true")
    ap.add_argument("--no-subtitles", action="store_true"); a = ap.parse_args()
    if a.cmd == "all":
        run_all(a); return
    if a.cmd == "daily":
        daily(); return
    if a.cmd == "packimages":
        pack_images(); return
    if a.cmd == "packvideo":
        pack_video(subtitles=not a.no_subtitles); return
    if a.cmd == "split":
        packs = sorted(glob.glob(os.path.join(HERE, "projects", "*_pack")))
        if not packs and not a.project: sys.exit("no pack project yet")
        split_pack(Project(a.project or packs[-1])); return
    if a.cmd == "pack":
        make_pack(a.minutes if a.minutes != 5 else 8.0, int(os.getenv("STUDIO_PART_SECONDS", "30"))); return
    if a.cmd == "upload":
        import upload as U; U.upload(a.project or latest_project()); return
    if a.cmd == "budget":
        daily = int(os.getenv("STUDIO_DAILY_IMAGES", "40"))
        print(f"Free pictures per day (STUDIO_DAILY_IMAGES): {daily}\n")
        print("  video     shots   2 copies   3 copies   4 copies   days with 4 copies")
        for m in (3, 5, 8, 10, 15, 20):
            n = int(m * 60 / 8)
            print(f"  {m:>2} min   {n:>5}   {n * 3:>8}   {n * 4:>8}   {n * 5:>8}   {-(-n * 5 // daily):>6}")
        return
    if a.cmd == "new":
        P = Project(a.project or os.path.join(HERE, "projects", time.strftime("%Y%m%d_%H%M")))
        stage1(P, a.auto or os.getenv("STUDIO_AUTO") == "1"); stage2(P, a.minutes); stage3(P); plan_shots(P)
        print(f"\nStages 1-3 done + shot plan. Read 2_STORY.txt and 3_CHARACTERS.txt in {P.dir}\nNext:  python studio.py sheets"); return
    folder = a.project or latest_project()
    if not folder: sys.exit("no project yet - run: python studio.py new")
    P = Project(folder)
    {"sheets": lambda: stage4(P), "images": lambda: stage5(P), "clips": lambda: stage6(P, all_shots=a.all), "qc": lambda: qc(P),
     "redo": lambda: stage6(P, only=set(P.load("qc_failed.json", []))), "final": lambda: (final(P, not a.no_subtitles) is not False) and doctor(P, not a.no_subtitles),
     "status": lambda: status(P), "plan": lambda: plan_shots(P), "check": lambda: doctor(P, not a.no_subtitles)}[a.cmd]()


if __name__ == "__main__":
    main()
