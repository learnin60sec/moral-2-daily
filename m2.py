"""
MORAL 2 - flipbook storybook videos.
  python m2.py story [--minutes 4]   best story -> ONE prompt file for all pictures (paste once in Gemini) + ONE smooth voice
  python m2.py pictures              helper: copies each FULL picture prompt, saves each download as 001.png, 002.png ...
  python m2.py import                (other way) take the downloaded pictures (in download order) -> pictures\\001.png ... and link them to the story
  python m2.py video                 pictures follow the voice word by word, soft crossfades + camera, Hindi subtitles -> FINAL.mp4
Picture every ~3 s (setx M2_SECONDS_PER_PICTURE 3). Voice: Microsoft (one take, no breaks) or setx STUDIO_VOICE gemini.
"""
import os, math, sys, re, json, time, glob, shutil, asyncio, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import studio as S

SEC_PER_PIC = float(os.getenv("M2_SECONDS_PER_PICTURE", "4"))
WORDS_PER_SEC = 2.3


def pics_dir(P):
    """the folder that holds this story's pictures (normally 'pictures'; a new one if Windows had the old one locked)"""
    return (P.load("dirs.json", {}) or {}).get("pictures", "pictures")


def fresh_pics_dir(P):
    """empty the pictures folder; if Windows keeps a file locked (open in another program), use a NEW folder instead of crashing"""
    d = P.p(pics_dir(P)); os.makedirs(d, exist_ok=True)
    try:
        for f in glob.glob(os.path.join(d, "*.png")): os.remove(f)
        return d
    except PermissionError as e:
        new = "pictures_" + time.strftime("%H%M%S"); P.save("dirs.json", {"pictures": new}); os.makedirs(P.p(new), exist_ok=True)
        say(f"  (a picture is open in another program: {os.path.basename(str(e.filename or ''))} - using a new folder '{new}')")
        return P.p(new)


def latest():
    ps = sorted(glob.glob(os.path.join(HERE, "projects", "*")))
    if not ps: sys.exit("No story yet - run 1_STORY.bat first")
    return S.Project(ps[-1])


# ------------------------------------------------------------------ 1) story + one prompt file + one voice
def _scripts_of(d):
    """the list of clip scripts (strings) inside whatever JSON the AI returned"""
    if isinstance(d, list): d = {"items": d}
    if not isinstance(d, dict): return []
    cands = [d.get("scripts")] + [v for v in d.values() if isinstance(v, list)]
    for v in cands:
        if isinstance(v, list) and v:
            out = [x if isinstance(x, str) else next((str(y) for y in x.values() if isinstance(y, str) and len(y) > 80), "") for x in v if isinstance(x, (str, dict))]
            out = [o.strip() for o in out if o and len(o.strip()) > 80]
            if out: return out
    return []


def trim_words(text, limit):
    """cut at `limit` words, going back to the end of a sentence if that costs less than 30 words"""
    w = str(text).split()
    if len(w) <= limit: return " ".join(w)
    cut = " ".join(w[:limit]); i = max(cut.rfind(". "), cut.rfind("; "))
    return cut[:i + 1] if i > len(cut) - 30 * 6 and i > 0 else cut


def detail_scripts(beats, looks, pics, english):
    """ONE writer call per story part: every picture gets a very detailed English clip script (Wan reads at most 512 tokens = about 330 words, so the
    script gets M2_SCRIPT_WORDS = 270 and the rest is kept for the consistency line, the 'continue' sentence and the retry wording)"""
    from concurrent.futures import ThreadPoolExecutor
    maxw = int(os.getenv("M2_SCRIPT_WORDS", "270"))
    by_beat = {}
    for i, pc in enumerate(pics): by_beat.setdefault(pc["beat"], []).append(i)
    cast = "\n".join(f"- {n}: {l}" for n, l in looks.items())
    def one(bi, idxs):
        lines = "\n".join(f"{k + 1}. what is seen: {pics[i]['action']} | idea of the movement: {pics[i].get('motion', '')} | characters: {', '.join(pics[i]['characters'])}" for k, i in enumerate(idxs))
        prompt = f"""You write prompts for the Wan 2.2 image-to-video model. It turns ONE 2D cartoon picture into a 5-second clip, so the prompt must describe the picture and its movement in COMPLETE DETAIL.
Place of this story part: {beats[bi].get('place', '')}. It has {len(idxs)} pictures, in this order.
Narration of this part (Hindi - understand it, do not copy it): {str(beats[bi]['narration'])[:700]}
Characters (use ONLY these English names, never Hindi letters):
{cast}
Pictures:
{lines}
For EACH picture write ONE English paragraph of {maxw - 40} to {maxw} words (NEVER more than {maxw}) containing, in this order:
(1) the shot: wide or medium, time of day, light direction and colours, 2D cartoon style;
(2) every character in the frame: name, exact look from the list, position (left / centre / right, foreground / background), posture, facial expression;
(3) the setting in detail: the objects, buildings, plants, sky and light sources that are in the picture;
(4) the 5 seconds second by second ("0-1 s: ..., 1-2 s: ..., 2-3 s: ..., 3-4 s: ..., 4-5 s: ..."): clear actions, gestures, head and eye movements, expression changes, how every other character reacts;
(5) movement of the surroundings: flame flicker, mist, smoke, leaves, water, dust, cloth in the wind;
(6) camera locked static (or a very slow push-in), no cut, no new people, faces, clothes and colours never change, the last second ends in a calm pose.
Describe ONLY what is in that picture. English letters only.
JSON only: {{"scripts": ["paragraph for picture 1", "paragraph for picture 2"]}} with EXACTLY {len(idxs)} paragraphs."""
        try: d = S.ask_writer(prompt, temperature=0.6, check=lambda x: len(_scripts_of(x)) >= len(idxs))
        except SystemExit: d = None
        return bi, idxs, _scripts_of(d)[:len(idxs)]
    say(f"  writing the detailed clip scripts: {len(by_beat)} parts, up to {maxw} words per picture ...")
    done = 0
    with ThreadPoolExecutor(max_workers=int(os.getenv("M2_SCRIPT_THREADS", "3"))) as ex:
        for bi, idxs, outs in ex.map(lambda kv: one(*kv), list(by_beat.items())):
            for i, sc in zip(idxs, outs):
                sc = trim_words(english(sc), maxw)
                if len(sc.split()) >= 60: pics[i]["script"] = sc; done += 1
    words = [len(pc.get("script", "").split()) for pc in pics if pc.get("script")]
    say(f"  clip scripts: {done} of {len(pics)} pictures" + (f", {min(words)}-{max(words)} words each" if words else "") + ("" if done == len(pics) else " (the others keep the short movement text)"))


def story(minutes=4.0):
    """story first -> voice -> REAL length of every part -> pictures per part = its seconds / M2_SECONDS_PER_PICTURE -> prompts"""
    base = os.path.join(HERE, "projects", time.strftime("%Y%m%d_%H%M%S")); folder, k = base, 1
    while os.path.exists(folder): k += 1; folder = f"{base}_{k}"           # never reuse a folder of another story
    P = S.Project(folder)
    S.stage1(P, True); idea = P.load("chosen.json")
    n_beats = max(6, int(round(minutes * 3))); words = int(minutes * 60 * WORDS_PER_SEC)
    say(f"\n  writing the story (~{minutes:g} min, {n_beats} parts) ...")
    kind = ("Hindi MYSTERY story (rahasya): a strange happening in an Indian village or small town, clues, rising suspense, a clever surprising "
            "reveal at the end and one short lesson. Family-friendly suspense only: no gore, no horror, no violence shown, nothing too scary for children"
            if MYSTERY else "Hindi moral story")
    look_txt = "realistic cinematic" if REALISTIC else "2D cartoon"
    d = S.ask_writer(f"""Write the {kind} "{idea['title']}" ({json.dumps(idea, ensure_ascii=False)}) for a {minutes:g}-minute narrated
{look_txt} video told by ONE storyteller{' with a gripping, suspenseful voice' if MYSTERY else ' with a warm voice'}. About {words} Hindi words in total, split into EXACTLY {n_beats} consecutive parts.
Write it to be READ ALOUD in one smooth take: flowing sentences, natural Hindi, feelings shown through the words and punctuation
(! ? , and dialogue in quotes) - never use '...' or line breaks inside a part.
JSON only: {{"title": "...", "moral": "one short Hindi sentence", "moral_tone": "happy|sad|serious",
"hook": "Hindi, 1-2 short spoken sentences (max 22 words) for the first seconds of the video: the strangest or most exciting moment as a gripping question that makes people stay. NEVER reveal the answer or the ending.",
"hook_part": "number of the part (0 = first) where that moment happens - never one of the last two parts",
"characters": [{{"name": "the character's name in ENGLISH LETTERS only, e.g. Aarav, Malti Nani, Jaggu - never Hindi script", "look": "ONE fixed {'realistic appearance' if REALISTIC else '2D cartoon design'} in English: age, body, face, hair, skin tone, exact clothes with colours"}}],
"beats": [{{"narration": "Hindi text of this part", "place": "English: place + time of day + light{' (mysterious mood)' if MYSTERY else ''}"}}]}}""", check=lambda x: len(S.beats_from(x)) >= 3)
    d = d if isinstance(d, dict) else {}
    beats = S.beats_from(d)
    if not beats: raise SystemExit("STOPPED: no AI could write the story today (see the lines above) - try again later")
    if beats and os.getenv("M2_STORY_EDITOR", "1") == "1":           # a second pass by an "editor" makes the story clearly better
        say("  story editor: hook, clues, logic, natural Hindi ...")
        try:
            e = S.ask_writer(f"""You are the chief editor of a hit Hindi {'children-and-family MYSTERY' if MYSTERY else 'family moral story'} YouTube channel.
Improve this story so families watch till the end. Rules:
1. The FIRST part must hook in the first two sentences (a question, a strange event or a surprise).
2. Every part must move the story forward; cut repetition and filler; vivid, simple, natural spoken Hindi with short dialogues in quotes.
3. {'Plant 3 fair clues the viewer can notice before the reveal, include one false suspect, and make the reveal surprising but LOGICAL (no real ghosts or magic).' if MYSTERY else 'Clear conflict, emotional turning point and a satisfying ending.'}
   KEEP PEOPLE WATCHING: end EVERY part (except the last) with a small cliffhanger or question that makes the viewer need the next part;
   hold the big answer back until the last two parts; short sentences; one light funny moment; one warm emotional moment; no slow parts.
4. Keep the SAME title, characters (names and looks), places and EXACTLY {len(beats)} parts. LENGTH IS FIXED: part lengths in characters must stay
   close to {[len(b["narration"]) for b in beats]} (each part within plus or minus 20 percent) because the voice and pictures are planned for this length.
   Improve the words, do not add more. No '...', no line breaks.
5. Family-friendly: no horror, no gore, no violence shown.
Return the improved story in EXACTLY the same JSON shape.
6. Make the "hook" irresistible: max 22 words, a question about the strangest moment, never the answer.
STORY: {json.dumps({"title": d.get("title"), "moral": d.get("moral"), "moral_tone": d.get("moral_tone"), "hook": d.get("hook"), "hook_part": d.get("hook_part"), "characters": d.get("characters"), "beats": beats}, ensure_ascii=False)}""", temperature=0.7, check=lambda x: len(S.beats_from(x)) >= 1)
            e = e if isinstance(e, dict) else {}                         # no answer at all -> the first version is kept
            eb = S.beats_from(e)
            old_len = sum(len(b["narration"]) for b in beats); new_len = sum(len(b["narration"]) for b in eb)
            if len(eb) == len(beats) and 0.75 * old_len <= new_len <= 1.5 * old_len:
                for ob, nb in zip(beats, eb): nb.setdefault("place", ob.get("place", ""))
                beats = eb; d["moral"] = e.get("moral") or d.get("moral"); d["hook"] = e.get("hook") or d.get("hook")
                say("  story editor: improved version used")
            else:
                say(f"  story editor: answer did not keep the shape ({len(eb)} parts, length {new_len} vs {old_len}) - first version kept")
        except SystemExit:
            say("  story editor: no answer - first version kept")
    for b in beats:
        t = re.sub(r"\s*(\.{2,}|…)\s*", ", ", str(b["narration"]))          # '...' makes the voice stop -> comma
        b["narration"] = re.sub(r"\s+", " ", t).replace(", ,", ",").strip()
    looks = {c["name"]: c.get("look", "") for c in d.get("characters", []) if isinstance(c, dict) and c.get("name")}
    _dev = re.compile(r"[\u0900-\u097F]+")
    rename = {n: f"Character {chr(65 + i)}" for i, n in enumerate(list(looks)) if _dev.search(n)}
    if rename: say(f"  character names were in Hindi script -> {rename} (picture and video prompts must stay in English letters)")
    looks = {rename.get(n, n): re.sub(r"\s+", " ", _dev.sub("", v)).strip() for n, v in looks.items()}
    def english(txt):                                              # no Hindi letters in any prompt: known names are swapped, the rest removed
        txt = str(txt or "")
        for hn, en in rename.items(): txt = txt.replace(hn, en)
        return re.sub(r"\s+", " ", _dev.sub("", txt)).strip()
    title = d.get("title", idea["title"])
    hook = re.sub(r"\s+", " ", str(d.get("hook") or "")).replace("...", ",").replace("…", ",").strip()
    if not hook:                                                    # no hook from the AI -> the first sentence of the story as a question
        first = re.split(r"[।!?]", beats[0]["narration"])[0].strip()
        hook = (first + "। आख़िर इसका राज़ क्या था?") if first else ""
    try: hook_part = max(0, min(int(d.get("hook_part", 0)), max(0, len(beats) - 3)))
    except Exception: hook_part = 0
    st = {"title": title, "search_phrase": str(idea.get("search_phrase") or "").strip(), "moral": d.get("moral", ""), "moral_tone": d.get("moral_tone", "happy"), "hook": hook, "hook_part": hook_part,
          "characters": looks, "beats": beats, "pictures": []}
    cap = float(os.getenv("M2_MAX_MINUTES", "0") or 0)                # the longest story Kaggle can animate today (0 = no limit)
    for attempt in range(3):
        st["beats"] = beats; P.save("story.json", st)
        text = " ".join(b["narration"].strip() for b in beats)
        open(P.p("FULL_STORY.txt"), "w", encoding="utf-8").write(f"{title}\n\n" + "\n\n".join(b["narration"] for b in beats) + f"\n\nसीख: {d.get('moral', '')}")
        say("  making the voice (one take) and measuring every part ...")
        voice(P, text)
        total = S.probe(P.p("FULL_VOICE.mp3"))[0]
        if not (cap >= 1.5 and total / 60 > cap * 1.03 and attempt < 2): break
        ratio = cap * 60 * 0.97 / total; targets = [max(40, int(len(b["narration"]) * ratio)) for b in beats]
        say(f"  the voice is {total / 60:.1f} min but only {cap:g} min can get moving clips today -> shortening the story to about {ratio * 100:.0f}% (try {attempt + 1})")
        try:
            e = S.ask_writer(f"""You are the chief editor of a hit Hindi YouTube story channel. This story is too long for today's video: SHORTEN it.
Every part must get about {int(ratio * 100)} percent of its present length. Target length of each part in characters: {targets} (each within plus or minus 12 percent).
Keep EXACTLY {len(beats)} parts, the same title, characters, places and order. Keep the hook, the clues, the cliffhanger at the end of each part,
the surprising reveal near the end and the moral. Cut repetition, filler and long descriptions; short sentences. No '...', no line breaks. Hindi only.
Return the shortened story in EXACTLY this JSON shape: {{"moral": "...", "beats": [{{"narration": "..."}}]}}
STORY: {json.dumps({"moral": d.get("moral"), "beats": [{"narration": b["narration"]} for b in beats]}, ensure_ascii=False)}""", temperature=0.5, check=lambda x: len(S.beats_from(x)) >= 1)
            e = e if isinstance(e, dict) else {}
            eb = S.beats_from(e)
            new_len = sum(len(b["narration"]) for b in eb)
            if len(eb) == len(beats) and 0.8 * sum(targets) <= new_len <= 1.15 * sum(targets):
                for ob, nb in zip(beats, eb):
                    nb["place"] = ob.get("place", ""); nb["narration"] = re.sub(r"\s+", " ", re.sub(r"\s*(\.{2,}|…)\s*", ", ", str(nb["narration"]))).strip()
                beats = eb; d["moral"] = e.get("moral") or d.get("moral"); st["moral"] = d["moral"]
                say(f"  story shortened: {sum(len(b['narration']) for b in eb)} characters")
            else:
                say(f"  shortening did not keep the shape ({len(eb)} parts, {new_len} characters, wanted {sum(targets)}) - this length is kept"); break
        except SystemExit:
            say("  shortening: no AI answered - this length is kept"); break
    bt = beat_times(P, st, total)
    SEC_MAXP = float(os.getenv("M2_MAX_PAGE_SECONDS", "6.4"))          # a clip is 5 s (slowed to at most 0.62x = 8 s): a page must never be longer
    counts = [max(1, int(round((bt[i + 1] - bt[i]) / SEC_PER_PIC)), int(math.ceil((bt[i + 1] - bt[i]) / SEC_MAXP))) for i in range(len(beats))]
    say(f"  video length {total / 60:.1f} min -> {sum(counts)} pictures (one every ~{SEC_PER_PIC:.0f} s, never longer than {SEC_MAXP:g} s), parts get: {counts}")
    plan = "\n".join(f"{i}: [{counts[i]} pictures, {bt[i + 1] - bt[i]:.0f} s] {b['place']} - {b['narration'][:220]}" for i, b in enumerate(beats))
    m = S.ask(f"""For this Hindi story, write the picture moments of every part, like a flip book: same place and characters inside a part,
the action moving forward a little in each picture, following what the narration says in that order. Give EXACTLY the number of
pictures written in [ ] for each part. Characters: {', '.join(looks)}.
{plan}
For EVERY picture also write "motion": a CLIP SCRIPT of 55-90 English words for the video model, in this order:
(1) who is in the frame - use ONLY these English names: {', '.join(looks)} - where each one stands and what he or she holds;
(2) what happens in 3 beats during the 5 seconds ("first ..., then ..., finally ..."): a CLEAR visible action of the main character (steps forward, turns the head,
points, lifts the lantern, hugs, laughs, cries), the facial expression changing, and the reaction of every other person in the frame;
(3) movement of the surroundings (mist drifts, a flame flickers, leaves sway, water ripples, smoke rises);
(4) the last second settles into a calm pose from which the next picture of the same part can continue.
Describe ONLY things that are in this picture. No camera movement, no new people, no scene change. English letters only.
JSON only: {{"parts": [{{"index": 0, "pictures": [{{"action": "English: exactly what is seen", "motion": "English: what moves", "characters": ["name"]}}]}}]}}""")
    got = {int(x.get("index", -1)): x.get("pictures", []) for x in (m.get("parts", []) if isinstance(m, dict) else []) if isinstance(x, dict)}
    pics = []
    for bi, b in enumerate(beats):
        lst = [x for x in got.get(bi, []) if isinstance(x, dict) and x.get("action")]
        if not lst: lst = [{"action": f"scene of: {b['place']}", "characters": list(looks)[:2]}]
        while len(lst) < counts[bi]: lst.append(dict(lst[-1], action=lst[-1]["action"] + " (a moment later, slightly different pose)"))
        for pc in lst[:counts[bi]]:
            pics.append({"beat": bi, "action": english(pc["action"]), "motion": english(pc.get("motion")), "place": english(b.get("place", "")), "characters": [n for n in pc.get("characters", []) if n in looks] or list(looks)[:1]})
    if os.getenv("M2_DETAIL_SCRIPTS", "1") == "1": detail_scripts(beats, looks, pics, english)
    for i, p in enumerate(pics, 1):
        p["prompt"] = full_prompt(p, looks, i)
    st["pictures"] = pics; P.save("story.json", st)
    cast = "\n".join(f"- {k}: {v}" for k, v in looks.items())
    lines = [f"Create {len(pics)} pictures for my 2D cartoon story, ONE picture for each numbered line below, strictly in this order.",
             "Make 4 pictures per reply (in order), then stop and wait until I type NEXT.", "SAME CHARACTERS IN EVERY PICTURE:", cast, "", "PICTURES:"]
    for i, p in enumerate(pics, 1):
        lines.append(f"{i}. {p['place']} - {p['action']} (in the picture: {', '.join(p['characters']) or 'no people'})")
    open(P.p("ALL_PROMPTS_PASTE_IN_GEMINI.txt"), "w", encoding="utf-8").write("\n".join(lines))
    open(P.p("FULL_PROMPTS_ONE_BY_ONE.txt"), "w", encoding="utf-8").write("\n\n".join(f"===== PICTURE {i:03d} =====\n{p['prompt']}" for i, p in enumerate(pics, 1)))
    trojan_prompts(P)
    n_ch = (len(pics) + PER_CHAPTER - 1) // PER_CHAPTER
    say(f"\nREADY in {P.dir}\n  VIDEO {total / 60:.1f} min  ->  {len(pics)} PICTURES  ->  {n_ch} CHAPTERS of {PER_CHAPTER} (PROMPTS_CHAPTERS.txt)\n"
        f"  FULL_STORY.txt, FULL_VOICE.mp3")
    if os.name == "nt" and os.getenv("STUDIO_UNATTENDED") != "1": os.startfile(P.dir)
    return P



STYLE_PACK = os.getenv("M2_STYLE", "2d_moral").lower()
REALISTIC = STYLE_PACK.startswith("realistic"); MYSTERY = "mystery" in STYLE_PACK
STYLE_REAL = ("Style: cinematic photorealistic film still, shot on a 35mm cinema camera, realistic Indian people and real locations, natural skin "
              "texture, dramatic moody lighting with soft shadows, shallow depth of field, subtle film grain, rich but natural colours, high detail. "
              "Wide 16:9 landscape frame filling the whole picture edge to edge (no black bars, no letterbox, no border), the whole head of every "
              "person inside the frame. No text, no letters, no numbers, no captions, no watermark. "
              "Not a cartoon, not anime, not an illustration, not a painting.")
STYLE_FULL = ("Picture fills the whole frame edge to edge, no black bars, no letterbox, no border. "
              "Style: richly detailed storybook illustration in premium hand-drawn 2D cartoon style, fine ink linework, textured hand-painted backgrounds with lots of small details (grass blades, soil, leaves, wood grain, cloth folds), warm natural light, "
              "premium hand-drawn 2D cartoon illustration for an Indian village moral story, clean ink outlines, flat painted colours, "
              "soft cel shading, expressive cartoon faces, detailed illustrated rural Indian village background, warm cinematic light. "
              "Wide 16:9 landscape frame, characters full body with the whole head inside the frame. "
              "No text, no letters, no numbers, no captions, no speech bubbles. Not 3D, not photo-realistic.")


def full_prompt(p, looks, roll=None):
    who = [f"{n} ({looks[n]})" for n in p.get("characters", []) if n in looks]
    if REALISTIC:
        return ((f"ROLL {roll:03d}. (the roll number is only for me - never draw it) " if roll else "") + f"Create one picture. Place: {p.get('place', '')}. "
                f"What is happening: {p['action']}. " + (f"People in the picture, looking exactly like this every time: {'; '.join(who)}. " if who else
                "No people in this picture. ") + STYLE_REAL)
    return ((f"ROLL {roll:03d}. (the roll number is only for me - never draw it) " if roll else "") + f"Create one picture. Place: {p.get('place', '')}. What is happening: {p['action']}. "
            + (f"Characters in the picture, drawn exactly like this every time: {'; '.join(who)}. " if who else "No people in this picture. ")
            + "Traditional Indian village clothes only. " + STYLE_FULL)


PER_CHAPTER = int(os.getenv("M2_PER_CHAPTER", "4"))


def master_prompt(st):
    cast = "\n".join(f"- {k}: {v}" for k, v in st.get("characters", {}).items())
    return (f"We are making an illustrated 2D cartoon story book \"{st.get('title', '')}\" with {len(st['pictures'])} pages. "
            f"I will send the pages in chapters of {PER_CHAPTER}. For every page generate ONE landscape 16:9 illustration. "
            "Do not ask questions, do not summarize, just generate the images, in page order.\n\n"
            "STYLE (identical on every page): premium hand-drawn 2D cartoon, clean ink outlines, flat painted colours, soft cel shading, "
            "expressive cartoon faces, detailed illustrated rural Indian village backgrounds, warm cinematic light, family-friendly.\n\n"
            "CHARACTER DESIGN (keep EXACTLY the same on every page - same face, hair, body and clothes):\n" + cast + "\n\n"
            "RULES: absolutely NO text, letters, numbers, captions or speech bubbles inside any image. Characters full body with the whole "
            "head inside the frame. Not 3D, not photo-realistic. Reply only \"Ready\" now.")


def chapter_prompts(st):
    pics, out = st["pictures"], []
    for c in range(0, len(pics), PER_CHAPTER):
        part = pics[c:c + PER_CHAPTER]
        lines = [f"ROLLS {c + 1:03d}-{c + len(part):03d}. (roll numbers are only for me - never draw them)",
                 f"Generate these {len(part)} pages, one image each, in this order, same style and same characters:"]
        for j, p in enumerate(part):
            who = ", ".join(p.get("characters", [])) or "no people"
            lines.append(f"Page {c + j + 1}: {p.get('place', '')} - {p['action']} (characters: {who})")
        out.append({"first": c + 1, "last": c + len(part), "text": "\n".join(lines)})
    return out


def trojan_prompts(P):
    st = P.load("story.json"); ch = chapter_prompts(st)
    lines = [f"{st.get('title', '')} - {len(st['pictures'])} PAGE PROMPT PACK", "=" * 50, "",
             "KAISE USE KARNA HAI", "1) Gemini (ya ChatGPT) mein NAYI chat kholo.", "2) MASTER PROMPT ek baar paste karo. Wo bas 'Ready' bolega.",
             f"3) Phir ek-ek CHAPTER ({PER_CHAPTER} pages) paste karo, aur tasveerein ORDER mein download karo (Page 1, 2, 3 ...).",
             "4) Beech mein ruk jaye to likho: continue with the next page", "5) Characters badalne lagein to pehli achhi tasveer upload karke likho: "
             "use exactly the same style and characters as this image", "   (2_PICTURES.bat ka helper ye sab copy aur number khud karta hai)", "",
             "=" * 50, "MASTER PROMPT (sirf ek baar)", "=" * 50, master_prompt(st), ""]
    for k, c in enumerate(ch, 1):
        lines += ["=" * 50, f"CHAPTER {k}  (Pages {c['first']}-{c['last']})", "=" * 50, c["text"], ""]
    open(P.p("PROMPTS_CHAPTERS.txt"), "w", encoding="utf-8").write("\n".join(lines))


def _with_timeout(fn, seconds):
    """run fn() in a background thread; None if it does not finish in time (a hung network call never blocks the day)"""
    import threading
    box = {}
    def run():
        try: box["v"] = fn()
        except Exception as e: box["e"] = e
    th = threading.Thread(target=run, daemon=True); th.start(); th.join(seconds)
    if th.is_alive(): return None
    if "e" in box: raise box["e"]
    return box.get("v")


def azure_tts(text, out, rate="+0%", pitch="+0Hz", volume="+0%", want_marks=True, limit=240):
    """Microsoft's OFFICIAL speech service (Azure, free F0 tier). Returns word marks (list) or None if not set up / failed."""
    key, region = os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION", "centralindia")
    if not key: return None
    try:
        import azure.cognitiveservices.speech as sdk
    except ImportError:
        os.system(f'"{sys.executable}" -m pip install -q azure-cognitiveservices-speech')
        try: import azure.cognitiveservices.speech as sdk
        except ImportError: say("  (Azure speech package could not be installed)"); return None
    from xml.sax.saxutils import escape
    voice_name = os.getenv("M2_AZURE_VOICE", "hi-IN-MadhurNeural")
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="hi-IN"><voice name="{voice_name}">'
            f'<prosody rate="{rate}" pitch="{pitch}" volume="{volume}">{escape(text)}</prosody></voice></speak>')
    def run():
        cfg = sdk.SpeechConfig(subscription=key, region=region)
        cfg.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
        syn = sdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        marks = []
        if want_marks:
            syn.synthesis_word_boundary.connect(lambda e: marks.append({"t": e.audio_offset / 1e7, "d": e.duration.total_seconds(),
                                                                         "text": e.text, "kind": "WordBoundary"}))
        r = syn.speak_ssml_async(ssml).get()
        if r.reason == sdk.ResultReason.SynthesizingAudioCompleted:
            data = bytes(r.audio_data or b"")
            if len(data) < 2000:                                      # the documented way to read the finished audio
                try:
                    tmp_ = out + ".azure"; sdk.AudioDataStream(r).save_to_wav_file(tmp_); data = open(tmp_, "rb").read(); os.remove(tmp_)
                except Exception as e:
                    say(f"  (Azure audio stream: {str(e)[:80]})")
            if len(data) > 2000:
                open(out, "wb").write(data); return marks
            raise RuntimeError(f"audio finished but only {len(data)} bytes came back")
        det = getattr(r, "cancellation_details", None)
        raise RuntimeError(f"{r.reason} {getattr(det, 'error_details', '')}"[:200])
    try:
        res = _with_timeout(run, limit)
        if res is None: say(f"  (Azure voice: no answer in {limit} s)")
        else: return res
    except Exception as e:
        say(f"  (Azure voice failed: {str(e)[:150]})")
    # the plain web way (no SDK): Azure returns the finished mp3 directly (no word times)
    try:
        import requests
        r = requests.post(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"), timeout=limit,
                          headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                                   "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "moral-story-club"})
        if r.status_code == 200 and len(r.content) > 2000:
            open(out, "wb").write(r.content); say(f"  (Azure voice by web request: {len(r.content) // 1024} KB, no word times)"); return []
        say(f"  (Azure web request: {r.status_code} {r.text[:120]})")
    except Exception as e:
        say(f"  (Azure web request failed: {str(e)[:120]})")
    return None


def voice(P, text):
    """ONE take for the whole story (no breaks). Saves word timings so pictures can follow the voice exactly.
    Microsoft voice with a time limit and 3 tries; then Gemini voice; then a clear error (never hangs for hours)."""
    out = P.p("FULL_VOICE.mp3")
    if os.getenv("STUDIO_VOICE", "microsoft").lower() == "gemini" and S.gemini_tts(text, "narrator", "warm", out, P):
        P.save("voice_marks.json", []); return out
    v, rate, pitch = S.NARRATOR["edge"]
    marks = azure_tts(text, out, rate, pitch)                        # 1st: Azure (official, free 500k characters/month)
    if marks is not None:
        P.save("voice_marks.json", marks)
        say(f"  voice (Azure): {S.probe(out)[0] / 60:.1f} min, {os.path.getsize(out) // 1024} KB, {len(marks)} timing marks"); return out
    import edge_tts                                                  # 2nd: Edge voice   3rd: Gemini voice
    limit = float(os.getenv("M2_VOICE_SECONDS", "90"))
    def one_take():
        marks, data = [], bytearray()
        try:
            com = edge_tts.Communicate(text, v, rate=rate, pitch=pitch, boundary="WordBoundary")
        except TypeError:
            com = edge_tts.Communicate(text, v, rate=rate, pitch=pitch)
        for ch in com.stream_sync():
            if ch["type"] == "audio": data.extend(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                marks.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "text": ch["text"], "kind": ch["type"]})
        return bytes(data), marks
    for attempt in range(1, 3):
        try:
            res = _with_timeout(one_take, limit)
        except Exception as e:
            res = None; say(f"  voice try {attempt}: error {str(e)[:120]}")
        if res and len(res[0]) > 5000:
            open(out, "wb").write(res[0]); P.save("voice_marks.json", res[1])
            say(f"  voice: {S.probe(out)[0] / 60:.1f} min, {len(res[1])} timing marks"); return out
        say(f"  voice try {attempt}: no answer in {int(limit)} s - trying again"); time.sleep(10)
    if os.getenv("GEMINI_API_KEY") and _with_timeout(lambda: S.gemini_tts(text, "narrator", "warm", out, P), limit):
        P.save("voice_marks.json", []); say("  voice made with Gemini (Microsoft voice did not answer)"); return out
    raise SystemExit("VOICE FAILED: Azure, Edge and Gemini voices all failed (see the lines above). Try again later.")


# ------------------------------------------------------------------ 2) import the downloaded pictures in download order
def import_pictures(folder=None):
    P = latest(); st = P.load("story.json"); need = len(st["pictures"])
    since = os.path.getmtime(P.p("story.json")) - 60
    dirs = [folder] if folder else S.download_dirs()
    found = []
    for d in dirs:
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and os.path.getmtime(p) >= since: found.append(p)
    def natural(name):
        return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", os.path.basename(name))]
    found.sort(key=lambda p: (int(os.path.getmtime(p)), natural(p)))   # download order; same second (batch/zip) -> by number in the name
    os.makedirs(P.p(pics_dir(P)), exist_ok=True)
    for i, p in enumerate(found[:need], 1):
        from PIL import Image
        import io as _io
        b = _io.BytesIO(); Image.open(p).convert("RGB").save(b, "PNG"); S.clean_frame(b.getvalue(), P.p(pics_dir(P), f"{i:03d}.png"))
    have = len(glob.glob(P.p(pics_dir(P), "*.png")))
    print(f"  pictures linked to the story: {have} of {need}" + ("" if have >= need else
          f"  (missing {need - have}: the last ones reuse the picture before them; or download the rest and run 2_IMPORT again)"))
    sheet = order_sheet(P, st)
    print(f"  CHECK the order by eye: {sheet}")
    bad = ai_order_check(P, st)
    if bad: print("  AI thinks these numbers do NOT match their story moment:", ", ".join(str(b) for b in bad),
                  "\n  -> open CHECK_ORDER.jpg; to fix, replace pictures\\NNN.png with the right picture (same name)")
    elif bad == []: print("  AI check: every picture matches its story moment")
    if os.name == "nt": os.startfile(sheet)
    return have


def order_sheet(P, st):
    """all pictures on one sheet with their number and what they should show"""
    from PIL import Image, ImageDraw, ImageFont
    files = sorted(glob.glob(P.p(pics_dir(P), "*.png"))); cols = 5; tw, th = 320, 180; cap = 34
    rows = max(1, math.ceil(len(files) / cols)); sheet = Image.new("RGB", (cols * tw, rows * (th + cap)), (25, 25, 30)); d = ImageDraw.Draw(sheet)
    try: f = ImageFont.truetype("arial.ttf", 14)
    except OSError: f = ImageFont.load_default()
    for i, fp in enumerate(files):
        x, y = (i % cols) * tw, (i // cols) * (th + cap)
        sheet.paste(Image.open(fp).convert("RGB").resize((tw - 6, th - 6)), (x + 3, y + 3))
        act = st["pictures"][i]["action"] if i < len(st["pictures"]) else "-"
        d.rectangle((x + 3, y + 3, x + 46, y + 26), fill=(255, 210, 60)); d.text((x + 8, y + 7), f"{i + 1:03d}", fill=(0, 0, 0), font=f)
        d.text((x + 6, y + th + 2), act[:44], fill=(230, 230, 230), font=f)
    out = P.p("CHECK_ORDER.jpg"); sheet.save(out, quality=85); return out


def duplicate_pictures(P):
    """numbers whose picture is (almost) the same as the picture before it -> probably downloaded twice"""
    import numpy as np
    from PIL import Image
    files = sorted(glob.glob(P.p(pics_dir(P), "*.png"))); prev, dup = None, []
    for f in files:
        a = np.asarray(Image.open(f).convert("L").resize((96, 54))).astype(float)
        if prev is not None and np.abs(a - prev).mean() < 0.3: dup.append(int(os.path.basename(f)[:3]))   # truly identical only
        prev = a
    return dup


def ai_order_check(P, st, budget=None):
    """Groq (Gemini backup) checks pictures against their story moment - at most `budget` seconds (default 90), with progress.
    Returns suspicious page numbers, [] if all fine, None if skipped/no AI. setx M2_AI_CHECK 0 to switch it off."""
    if os.getenv("M2_AI_CHECK", "1") == "0": return None
    files = sorted(glob.glob(P.p(pics_dir(P), "*.png")))
    if not files or not (os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")): return None
    budget = budget or float(os.getenv("M2_AI_CHECK_SECONDS", "90")); t0 = time.time()
    import requests as _rq
    real_post = _rq.post
    def quick_post(*a, **k):                                      # no single answer may take longer than 25 s
        k["timeout"] = min(25, k.get("timeout", 25)); return real_post(*a, **k)
    _rq.post = quick_post
    bad, answered, old_rules = [], False, S.LOOK_RULES
    try:
        for k in range(0, len(files), 4):
            if time.time() - t0 > budget:
                print(f"  AI check stopped after {int(time.time() - t0)} s (checked {k} of {len(files)}) - going on with the video"); break
            chunk = files[k:k + 4]
            wanted = "; ".join(f"Picture {j + 1} should show: {st['pictures'][k + j]['action']}" for j in range(len(chunk)) if k + j < len(st["pictures"]))
            S.LOOK_RULES = ("You check if each picture shows the moment it should. " + wanted.replace("{", "(").replace("}", ")") +
                            " Characters: {bible}. Report a picture ONLY if it clearly shows a different moment or a different scene. "
                            'JSON only: {{"pictures": [{{"n": 1, "ok": true, "problems": []}}]}}')
            res = S.groq_look(chunk, json.dumps(st.get("characters", {}), ensure_ascii=False))   # Groq only: fast, no long Gemini fallback
            if res is None:
                if not answered: print("  AI check: no answer from the AI - skipped"); break
                continue
            answered = True
            for pth in res: bad.append(int(os.path.basename(pth)[:3]))
            print(f"  AI check {min(k + 4, len(files))}/{len(files)}", flush=True)
    finally:
        S.LOOK_RULES = old_rules; _rq.post = real_post
    return sorted(bad) if answered else None

def pictures_helper():
    """helper window: copies the FULL prompt of picture 1, you paste + download, it is saved as pictures\\001.png, then picture 2 ..."""
    P = latest(); st = P.load("story.json"); os.makedirs(P.p(pics_dir(P)), exist_ok=True)
    looks = st.get("characters", {})
    items = [{"title": f"PICTURE {i:03d} of {len(st['pictures']):03d}", "prompt": p.get("prompt") or full_prompt(p, looks),
              "dest": P.p(pics_dir(P), f"{i:03d}.png")} for i, p in enumerate(st["pictures"], 1)]
    site = os.getenv("M2_SITE", "gemini").lower()
    S.helper(items, SITES.get(site, SITES["gemini"]), "image")
    have = len(glob.glob(P.p(pics_dir(P), "*.png")))
    print(f"  pictures saved: {have} of {len(items)}" + ("" if have >= len(items) else "  - run 2_PICTURES.bat again to continue from the next one"))
    if have:
        dup = duplicate_pictures(P)
        if dup: print("  WARNING: these numbers have the SAME picture as the one before (downloaded twice?):", dup,
                      "\n  -> delete pictures\\NNN.png for those numbers and run 2_PICTURES.bat again (it asks only for the missing ones)")
        bad = ai_order_check(P, st)
        if bad: print("  AI: these numbers do not match their story moment:", bad, "-> delete them and run 2_PICTURES.bat again")
        sheet = order_sheet(P, st); print("  check by eye:", sheet)
        if os.name == "nt": os.startfile(sheet)


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
TEMP_EXT = (".crdownload", ".tmp", ".part", ".download")


def watch_dirs():
    d = [os.getenv("M2_DOWNLOADS", "")] + S.download_dirs()
    return [x for x in dict.fromkeys(d) if x and os.path.isdir(x)]


def snapshot():
    """what is already in the download folders (name -> size, mtime)"""
    snap = {}
    for d in watch_dirs():
        try:
            for f in os.listdir(d):
                p = os.path.join(d, f)
                try: snap[p] = (os.path.getsize(p), os.path.getmtime(p))
                except OSError: pass
        except OSError:
            pass
    return snap


def new_pictures(snap, taken):
    """finished NEW picture files (not in the snapshot, not taken yet, size stable), oldest first"""
    out = []
    for d in watch_dirs():
        try: names = os.listdir(d)
        except OSError: continue
        for f in names:
            p = os.path.join(d, f)
            if p in taken or not f.lower().endswith(IMG_EXT) or f.lower().endswith(TEMP_EXT): continue
            try:
                size, mt = os.path.getsize(p), os.path.getmtime(p)
            except OSError:
                continue                                          # file is being renamed right now - next round
            if snap.get(p) == (size, mt) or size < 2000: continue
            out.append((mt, p, size))
    ready = []
    for mt, p, size in sorted(out):
        time.sleep(0.3)
        try:
            if os.path.getsize(p) == size: ready.append(p)     # size no longer changing = download finished
        except OSError:
            pass
    return ready


def latest_picture_download():
    best = None
    for d in watch_dirs():
        try:
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if f.lower().endswith(IMG_EXT) and not f.lower().endswith(TEMP_EXT):
                    mt = os.path.getmtime(p)
                    if not best or mt > best[0]: best = (mt, p)
        except OSError:
            pass
    return best[1] if best else None


def chapters_helper():
    """MASTER once, then CHAPTER 1 (pages 1-4): the next downloads are saved as 001..004, then CHAPTER 2 is copied by itself ..."""
    import tkinter as tk, webbrowser
    P = latest(); st = P.load("story.json"); os.makedirs(P.p(pics_dir(P)), exist_ok=True)
    ch = chapter_prompts(st); need = len(st["pictures"])
    def missing(): return [i for i in range(1, need + 1) if not os.path.exists(P.p(pics_dir(P), f"{i:03d}.png"))]
    if not missing(): print("  all pictures are already saved"); return
    webbrowser.open(SITES.get(os.getenv("M2_SITE", "gemini").lower(), SITES["gemini"]))
    taken, st8 = set(), {"since": time.time()}
    root = tk.Tk(); root.title("Story pictures"); root.attributes("-topmost", True); root.geometry("+20+20"); root.configure(bg="#1f2a44")
    head = tk.Label(root, fg="#ffd34d", bg="#1f2a44", font=("Segoe UI", 12, "bold")); head.pack(padx=10, pady=(8, 2))
    info = tk.Label(root, fg="white", bg="#1f2a44", wraplength=330, justify="left"); info.pack(padx=10, pady=4)
    def current():
        m = missing()
        if not m: return None
        return next(c for c in ch if c["first"] <= m[0] <= c["last"])
    def show():
        c = current()
        if not c:
            info.config(text="ALL PICTURES SAVED. Close this window."); head.config(text="Done"); return
        got = sum(os.path.exists(P.p(pics_dir(P), f"{i:03d}.png")) for i in range(c["first"], c["last"] + 1))
        head.config(text=f"CHAPTER pages {c['first']}-{c['last']}   saved {got}/{c['last'] - c['first'] + 1}   (all: {need - len(missing())}/{need})")
        info.config(text="First time in a new chat: 1) Copy MASTER -> Ctrl+V -> Enter (wait for 'Ready').\n"
                         "Then: 2) Copy CHAPTER -> Ctrl+V -> Enter -> download the pictures IN PAGE ORDER.")
    def copy_master(): S.copy_text(master_prompt(st)); info.config(text="MASTER copied - paste in a NEW chat, wait for 'Ready', then Copy CHAPTER.")
    def copy_chapter():
        c = current()
        if c: S.copy_text(c["text"]); st8["since"] = time.time(); info.config(text=f"Chapter (pages {c['first']}-{c['last']}) copied - paste, Enter, then download in order.")
    def redo():
        c = current()
        if not c: return
        for i in range(c["first"], c["last"] + 1):
            f = P.p(pics_dir(P), f"{i:03d}.png")
            if os.path.exists(f): os.remove(f)
        show()
    tk.Button(root, text="1) Copy MASTER (once)", width=26, bg="#7fd1ff", font=("Segoe UI", 11, "bold"), command=copy_master).pack(pady=2)
    tk.Button(root, text="2) Copy CHAPTER", width=26, bg="#ffd34d", font=("Segoe UI", 11, "bold"), command=copy_chapter).pack(pady=2)
    tk.Button(root, text="Redo this chapter", command=redo, bg="#ccc").pack(pady=2)
    tk.Button(root, text="Stop (continue later)", command=root.destroy, bg="#888").pack(pady=(2, 8))
    snap = {"files": snapshot()}
    last = tk.Label(root, fg="#9fe6a0", bg="#1f2a44", wraplength=330, justify="left",
                    text="Watching: " + " | ".join(watch_dirs()) if watch_dirs() else "NO download folder found! setx M2_DOWNLOADS <folder>")
    last.pack(padx=10, pady=(0, 6))
    def save_next(p):
        m = missing()
        if not m: return
        n = m[0]; c_before = current()
        shutil.copy(p, P.p(pics_dir(P), f"{n:03d}.png")); taken.add(p); print(f"  saved page {n:03d} <- {os.path.basename(p)}")
        last.config(text=f"Last saved: page {n:03d}  <-  {os.path.basename(p)}")
        nc = current(); show()
        if nc and c_before and nc["first"] != c_before["first"]:   # chapter finished -> next chapter copied by itself
            S.copy_text(nc["text"])
            info.config(text=f"Chapter done! NEXT chapter (pages {nc['first']}-{nc['last']}) is copied - paste, Enter, download in order.")
    def take_latest():
        p = latest_picture_download()
        if p and p not in taken: save_next(p)
        else: last.config(text="No new picture found in the download folder.")
    tk.Button(root, text="Take latest download (if it was missed)", command=take_latest, bg="#9fe6a0").pack(pady=2)
    def watch():
        try:
            if missing():
                for p in new_pictures(snap["files"], taken):
                    save_next(p)
                    if not missing(): break
        except Exception as e:                                    # never stop watching because of one odd file
            print("  (watch:", str(e)[:80], ")")
        root.after(1200, watch)
    show(); root.after(1200, watch); root.mainloop()
    dup = duplicate_pictures(P); bad = ai_order_check(P, st)
    if dup: print("  WARNING same picture twice at:", dup, "-> delete those pictures\\NNN.png and run 2_PICTURES.bat again")
    if bad: print("  AI: these pages do not match their story moment:", bad)
    sheet = order_sheet(P, st); print("  check by eye:", sheet)
    if os.name == "nt": os.startfile(sheet)


FROM_FOLDER = None
INTAKE = {}


def intake_report(clean_count, total_count):
    z = INTAKE.get("zips", {})
    lines = [f"  INTAKE: {total_count} picture files  ->  {clean_count} different pictures"]
    for name, n in z.items(): lines.append(f"     zip {name}: {n} pictures")
    if INTAKE.get("loose"): lines.append(f"     single pictures: {INTAKE['loose']}")
    if total_count > clean_count: lines.append(f"     duplicates removed (exactly the same picture twice): {total_count - clean_count}")
    if INTAKE.get("old"): lines.append(f"     ignored (older than this story): {INTAKE['old']}")
    for n, why in INTAKE.get("skipped", [])[:10]: lines.append(f"     skipped: {n[:50]} ({why})")
    for l in lines: say(l)


def pull_from_downloads(P):
    """pictures (and zips) that arrived in Downloads AFTER this story was made are copied into my_pics (record), so the
    user never has to move anything. Repeats (same file) are skipped."""
    import hashlib
    mp = os.path.join(HERE, "my_pics"); os.makedirs(mp, exist_ok=True)
    since = os.path.getmtime(P.p("story.json")) - 60
    have = set()
    for f in os.listdir(mp):
        p = os.path.join(mp, f)
        if os.path.isfile(p):
            try: have.add(hashlib.md5(open(p, "rb").read()).hexdigest())
            except OSError: pass
    got = 0
    for d in [x for x in S.download_dirs() + [os.getenv("M2_DOWNLOADS", "")] if x and os.path.isdir(x) and os.path.normpath(x) != os.path.normpath(mp)]:
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if not f.lower().endswith(IMG_EXT + (".zip",)) or f.lower().endswith(TEMP_EXT): continue
            try:
                if os.path.getmtime(p) < since or os.path.getsize(p) < 2000: continue
                h = hashlib.md5(open(p, "rb").read()).hexdigest()
            except OSError:
                continue
            if h in have: continue
            dst = os.path.join(mp, f)
            if os.path.exists(dst): dst = os.path.join(mp, f"{os.path.splitext(f)[0]}_{h[:6]}{os.path.splitext(f)[1]}")
            shutil.copy2(p, dst); have.add(h); got += 1
    if got: say(f"  {got} new pictures/zips taken from Downloads into my_pics")
    return got


def candidates(P):
    if FROM_FOLDER and os.path.basename(os.path.normpath(FROM_FOLDER)).lower() == "my_pics":
        try: pull_from_downloads(P)
        except Exception as e: say(f"  (Downloads not read: {str(e)[:60]})")
    """every picture that arrived after the story was made: loose pictures in the download folders AND pictures inside new zip
    files (unpacked into the project). Oldest first; inside a zip by the number in the file name."""
    import zipfile
    since = -1 if FROM_FOLDER else os.path.getmtime(P.p("story.json")) - 60
    if FROM_FOLDER and os.path.basename(os.path.normpath(FROM_FOLDER)).lower() == "my_pics":
        since = -1
    def natural(n): return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", os.path.basename(n))]
    out = []; global INTAKE
    INTAKE = {"zips": {}, "loose": 0, "skipped": [], "old": 0}
    unz = P.p("candidates"); os.makedirs(unz, exist_ok=True)
    for d in ([FROM_FOLDER] if FROM_FOLDER else watch_dirs()):
        try: names = os.listdir(d)
        except OSError: continue
        for f in names:
            p = os.path.join(d, f)
            try: mt = os.path.getmtime(p)
            except OSError: continue
            if mt < since:
                if f.lower().endswith(IMG_EXT + (".zip",)): INTAKE["old"] += 1
                continue
            if os.path.isdir(p): continue
            if f.lower().endswith(IMG_EXT): out.append((mt, natural(p), p)); INTAKE["loose"] += 1
            elif not f.lower().endswith(".zip") and not f.lower().endswith(".txt"): INTAKE["skipped"].append((f, "not a picture"))
            elif f.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(p) as z:
                        allnames = [n for n in z.namelist() if not n.endswith("/")]
                        imgs = [n for n in allnames if n.lower().endswith(IMG_EXT)]
                        INTAKE["zips"][f] = len(imgs)
                        for n in allnames:
                            if n not in imgs: INTAKE["skipped"].append((f"{f} > {n}", "not a picture"))
                        for k, n in enumerate(sorted(imgs, key=natural)):
                            dst = os.path.join(unz, re.sub(r"[^\w.]+", "_", os.path.splitext(f)[0]) + f"__{k:03d}__" + re.sub(r"[^\w.]+", "_", os.path.basename(n)))
                            if not os.path.exists(dst):
                                with z.open(n) as src, open(dst, "wb") as o: o.write(src.read())
                            out.append((mt + k * 1e-3, natural(n), dst))
                except zipfile.BadZipFile:
                    INTAKE["skipped"].append((f, "broken zip (download again)"))
    out.sort(key=lambda x: (x[0], x[1]))
    return [p for _, _, p in out]


def picker():
    """YOU click the right picture for each page; it is saved as that page number. Works with zips and many options."""
    import tkinter as tk
    from PIL import Image, ImageTk
    P = latest(); st = P.load("story.json"); os.makedirs(P.p(pics_dir(P)), exist_ok=True); need = len(st["pictures"])
    used = set(P.load("picked.json", {}).values())
    pool = [c for c in candidates(P) if c not in used]
    if not pool:
        print("  No pictures found after the story time. For older pictures:  python m2.py pick --from \"C:\\folder\""); return
    state = {"page": next((i for i in range(1, need + 1) if not os.path.exists(P.p(pics_dir(P), f"{i:03d}.png"))), need), "thumbs": []}
    print(f"  {len(pool)} pictures found - opening the picker window (it stays on top) ...", flush=True)
    root = tk.Tk(); root.title("Pick the picture for each page"); root.configure(bg="#1f2a44"); root.geometry("1180x720+20+20")
    root.attributes("-topmost", True); root.lift(); root.focus_force()
    root.after(2500, lambda: root.attributes("-topmost", False))   # on top at the start, then normal
    head = tk.Label(root, fg="#ffd34d", bg="#1f2a44", font=("Segoe UI", 14, "bold"), wraplength=1100, justify="left"); head.pack(padx=10, pady=8)
    canvas = tk.Canvas(root, bg="#1f2a44", highlightthickness=0); bar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
    grid = tk.Frame(canvas, bg="#1f2a44"); canvas.create_window((0, 0), window=grid, anchor="nw"); canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side="left", fill="both", expand=True, padx=10); bar.pack(side="right", fill="y")
    grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    nav = tk.Frame(root, bg="#1f2a44"); nav.place(relx=1.0, rely=0.0, anchor="ne", x=-30, y=8)
    def refresh():
        for w in grid.winfo_children(): w.destroy()
        state["thumbs"] = []
        pg = state["page"]
        if pg > need:
            head.config(text="ALL PAGES DONE - close this window and run 3_MAKE_VIDEO.bat"); return
        act = st["pictures"][pg - 1]["action"]; have = os.path.exists(P.p(pics_dir(P), f"{pg:03d}.png"))
        head.config(text=f"PAGE {pg:03d} of {need:03d}{'  (already has a picture - click another to replace)' if have else ''}\nShould show: {act}")
        for i, c in enumerate(pool):
            if i >= 60: break                                       # show 60 at a time (fast); the next ones appear as you pick
            try:
                im = Image.open(c); im.draft("RGB", (540, 320)); im = im.convert("RGB"); im.thumbnail((270, 160)); ph = ImageTk.PhotoImage(im)
            except Exception:
                continue
            state["thumbs"].append(ph)
            b = tk.Button(grid, image=ph, command=lambda c=c: choose(c), bd=3, bg="#33415c", activebackground="#ffd34d")
            b.grid(row=i // 4, column=i % 4, padx=6, pady=6)
            tk.Label(grid, text=os.path.basename(c)[-28:], fg="#aab", bg="#1f2a44", font=("Segoe UI", 8)).grid(row=i // 4, column=i % 4, sticky="s")
    def choose(c):
        pg = state["page"]; shutil.copy(c, P.p(pics_dir(P), f"{pg:03d}.png"))
        picked = P.load("picked.json", {}); picked[f"{pg:03d}"] = c; P.save("picked.json", picked)
        pool.remove(c); print(f"  page {pg:03d} <- {os.path.basename(c)}"); state["page"] += 1; refresh()
    def back():
        if state["page"] > 1:
            state["page"] -= 1; picked = P.load("picked.json", {}); prev = picked.pop(f"{state['page']:03d}", None)
            if prev and prev not in pool: pool.insert(0, prev)
            P.save("picked.json", picked); refresh()
    def skip():
        state["page"] += 1; refresh()
    tk.Button(nav, text="◀ Back", command=back, bg="#ccc").pack(side="left", padx=3)
    tk.Button(nav, text="Skip ▶", command=skip, bg="#ccc").pack(side="left", padx=3)
    refresh(); root.mainloop()
    have = len(glob.glob(P.p(pics_dir(P), "*.png"))); print(f"  pictures for pages: {have} of {need}")
    if have: sheet = order_sheet(P, st); print("  check:", sheet); os.name == "nt" and os.startfile(sheet)


def same_picture(a, b):
    """ONLY the very same file (downloaded twice). Flip-book pictures are meant to look almost alike - never removed."""
    import hashlib
    try:
        return hashlib.md5(open(a, "rb").read()).digest() == hashlib.md5(open(b, "rb").read()).digest()
    except OSError:
        return False


def remake(P=None):
    """same story again: take the pictures from my_pics into THIS story and make the video. Never starts a new story."""
    global FROM_FOLDER
    P = P or latest(); st = P.load("story.json")
    if not st: sys.exit("This folder has no story.json")
    FROM_FOLDER = FROM_FOLDER or os.path.join(HERE, "my_pics"); need = len(st["pictures"])
    say("=" * 64 + f"\n REMAKE: {st.get('title', '')}  ({need} pages)  -  pictures from {FROM_FOLDER}\n" + "=" * 64)
    import hashlib
    clean, seen = [], set()
    for c in candidates(P):
        try: h = hashlib.md5(open(c, "rb").read()).hexdigest()
        except OSError: continue
        if h not in seen: seen.add(h); clean.append(c)
    say(f"  found {len(clean)} pictures -> {min(len(clean), need)} of {need} pages")
    if len(clean) < need * 0.5:
        sys.exit(f"  STOP: only {len(clean)} pictures in {FROM_FOLDER}. Put this story's pictures there first.")
    fresh_pics_dir(P)
    from PIL import Image
    import io as _io
    chosen, how = match_pages(P, st, clean); numbered = None
    for i, c in sorted(chosen.items()):
        with Image.open(c) as _im:
            b = _io.BytesIO(); _im.convert("RGB").save(b, "PNG")
        S.clean_frame(b.getvalue(), P.p(pics_dir(P), f"{i:03d}.png"))
    gaps = [i for i in range(1, need + 1) if i not in chosen]
    say(f"  saved {len(chosen)} pictures on their pages ({how})"
        + (f" | pages without a picture: {gaps[:15]}" if gaps else ""))
    video(True)


def newstory(minutes=4.0):
    """close the current story, move my_pics pictures to my_pics\\old_<date>, make a NEW story (my_pics is empty for it)"""
    ps = sorted(glob.glob(os.path.join(HERE, "projects", "*")))
    if ps and os.path.exists(os.path.join(ps[-1], "story.json")):
        open(os.path.join(ps[-1], "FINAL_DONE"), "w").write(time.strftime("%Y-%m-%d %H:%M"))
        say(f"  closed the old story: {os.path.basename(ps[-1])}")
    mp = os.path.join(HERE, "my_pics"); os.makedirs(mp, exist_ok=True)
    olds = [f for f in os.listdir(mp) if f.lower().endswith(IMG_EXT + (".zip",))]
    if olds:
        dst = os.path.join(mp, "old_" + time.strftime("%Y%m%d_%H%M")); os.makedirs(dst, exist_ok=True)
        for f in olds: shutil.move(os.path.join(mp, f), os.path.join(dst, f))
        say(f"  {len(olds)} old pictures moved to {dst}")
    say("=" * 64 + "\n NEW STORY\n" + "=" * 64); story(minutes)
    say("\n NEXT: FLOW_BOT_RUN.bat (or make the pictures yourself into my_pics), then ONE_CLICK.bat")


def recover():
    """undo the accident: delete the half-made NEW story, put the moved pictures back into my_pics, re-open the old story"""
    ps = sorted(glob.glob(os.path.join(HERE, "projects", "*")))
    newest = ps[-1] if ps else None
    if newest and not os.path.exists(os.path.join(newest, "FINAL.mp4")) and not glob.glob(os.path.join(newest, "pictures*", "*.png")) \
            and time.time() - os.path.getmtime(newest) < 24 * 3600 and len(ps) > 1:
        shutil.rmtree(newest, ignore_errors=True); say(f"  removed the half-made new story: {os.path.basename(newest)}")
    mp = os.path.join(HERE, "my_pics"); olds = sorted(glob.glob(os.path.join(mp, "old_*")))
    if olds:
        moved = 0
        for f in os.listdir(olds[-1]):
            src, dst = os.path.join(olds[-1], f), os.path.join(mp, f)
            if not os.path.exists(dst): shutil.move(src, dst); moved += 1
        say(f"  {moved} pictures moved back from {os.path.basename(olds[-1])} to my_pics")
        try: os.rmdir(olds[-1])
        except OSError: pass
    P = latest(); fd = P.p("FINAL_DONE")
    if os.path.exists(fd): os.remove(fd)
    say(f"  story re-opened: {P.load('story.json').get('title', '')}  ({os.path.basename(P.dir)})\n  now: python m2.py video")


def vision_ask(image_path, text):
    """ask Groq (vision) - Gemini as backup - about one picture; returns parsed JSON or None"""
    import requests, base64, io
    from PIL import Image
    with Image.open(image_path) as im:
        im = im.convert("RGB"); im.thumbnail((640, 640)); b = io.BytesIO(); im.save(b, "JPEG", quality=75)
    data = base64.b64encode(b.getvalue()).decode()
    gk = os.getenv("GROQ_API_KEY")
    if gk:
        for model in ("meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"):
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {gk}"}, timeout=40,
                                  json={"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                                        "messages": [{"role": "user", "content": [{"type": "text", "text": text},
                                                     {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}}]}]})
                if r.status_code == 200: return S.parse(r.json()["choices"][0]["message"]["content"])
                if r.status_code == 429: time.sleep(3)
            except Exception:
                pass
    key = os.getenv("GEMINI_API_KEY")
    if key:
        for model in ("gemini-flash-latest", "gemini-flash-lite-latest"):
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, timeout=40,
                                  json={"contents": [{"parts": [{"text": text}, {"inline_data": {"mime_type": "image/jpeg", "data": data}}]}],
                                        "generationConfig": {"responseMimeType": "application/json"}})
                if r.status_code == 200: return S.parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            except Exception:
                pass
    return None


def match_pages(P, st, files):
    """page for every picture: names with page numbers -> exact; else AI looks at 4 pictures per call (max M2_MATCH_SECONDS,
    default 240 s); slow/no AI -> download order for the rest. Cached per picture."""
    import hashlib, requests, base64, io
    from PIL import Image
    pics = st["pictures"]; need = len(pics); cache = P.load("match.json", {}) or {}
    numbered = {}
    for c in files:
        mm = re.match(r"(?:pic|page|p)[ _-]?0*(\d+)\.", os.path.basename(c).lower())
        if mm and 1 <= int(mm.group(1)) <= need: numbered.setdefault(int(mm.group(1)), c)
    if len(numbered) >= len(files) * 0.8: return numbered, "page numbers in the file names"
    order = {c: min(need, k + 1) for k, c in enumerate(files)}
    gk = os.getenv("GROQ_API_KEY")
    if not gk or os.getenv("M2_AI_MATCH", "1") == "0":
        return {i: c for i, c in enumerate(files[:need], 1)}, "download order"
    budget = float(os.getenv("M2_MATCH_SECONDS", "240")); t0 = time.time(); votes, fails = {}, 0
    hashes = {c: hashlib.md5(open(c, "rb").read()).hexdigest() for c in files}
    todo = [c for c in files if hashes[c] not in cache]
    for c in files:
        if hashes[c] in cache: votes[c] = tuple(cache[hashes[c]])
    for k in range(0, len(todo), 4):
        if time.time() - t0 > budget or fails >= 2:
            say(f"  AI matching stopped after {int(time.time() - t0)} s - the rest goes by download order"); break
        chunk = todo[k:k + 4]; lo = max(1, min(order[c] for c in chunk) - 8); hi = min(need, max(order[c] for c in chunk) + 8)
        content = [{"type": "text", "text": "Each picture belongs to one page of an illustrated story. For EACH picture say which page it shows "
                    "(look at the action, people and place). Pages:\n" + "\n".join(f"{i}: {pics[i - 1].get('place', '')} - {pics[i - 1]['action']}" for i in range(lo, hi + 1))
                    + '\nJSON only: {"pictures": [{"n": 1, "page": number, "confidence": 0-100}]}'}]
        for j, c in enumerate(chunk, 1):
            with Image.open(c) as im:
                im = im.convert("RGB"); im.thumbnail((512, 512)); b = io.BytesIO(); im.save(b, "JPEG", quality=70)
            content += [{"type": "text", "text": f"Picture {j}:"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()}}]
        ans = None
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {gk}"}, timeout=30,
                              json={"model": "meta-llama/llama-4-scout-17b-16e-instruct", "temperature": 0, "response_format": {"type": "json_object"},
                                    "messages": [{"role": "user", "content": content}]})
            if r.status_code == 200: ans = S.parse(r.json()["choices"][0]["message"]["content"])
        except Exception:
            pass
        if not ans: fails += 1; continue
        fails = 0
        for it in ans.get("pictures", []) if isinstance(ans, dict) else []:
            try: n, pg, cf = int(it.get("n")), int(it.get("page")), int(it.get("confidence", 0))
            except (TypeError, ValueError): continue
            if 1 <= n <= len(chunk) and lo <= pg <= hi:
                votes[chunk[n - 1]] = (pg, cf); cache[hashes[chunk[n - 1]]] = [pg, cf]
        say(f"  AI matched {min(k + 4, len(todo))} of {len(todo)} pictures ({int(time.time() - t0)} s)")
    P.save("match.json", cache)
    for c in files:
        votes.setdefault(c, (order[c], 0))                         # not seen by the AI -> download order
    chosen = {}
    for c, (pg, cf) in sorted(votes.items(), key=lambda kv: -kv[1][1]):
        if pg in chosen:
            free = [q for q in range(1, need + 1) if q not in chosen]
            if not free: break
            pg = min(free, key=lambda q: abs(q - pg))
        chosen[pg] = c
    return chosen, "AI looked at the pictures" + ("" if all(v[1] for v in votes.values()) else " (some by download order)")

def missing_prompts(P, st, gaps):
    """open the FULL prompts of the missing pages in Notepad, ready to copy"""
    looks = st.get("characters", {})
    txt = [f"MISSING PAGES: {len(gaps)}  -  make these pictures, save them into my_pics, then press ENTER in the black window", ""]
    for g in gaps:
        p = st["pictures"][g - 1]
        txt += [f"===== PAGE {g:03d} =====  ({p['action']})", p.get("prompt") or full_prompt(p, looks), ""]
    f = P.p("MISSING_PROMPTS.txt"); open(f, "w", encoding="utf-8").write("\n".join(txt))
    if os.name == "nt": os.startfile(f)
    return f


def roll_watcher():
    """copy ANY prompt (it starts with ROLL 007 or ROLLS 005-008) -> the next download(s) are saved as my_pics\\pic_007.png ..."""
    try:
        import pyperclip
    except ImportError:
        os.system(f'"{sys.executable}" -m pip install pyperclip'); import pyperclip
    mp = os.path.join(HERE, "my_pics"); os.makedirs(mp, exist_ok=True)
    P = latest(); st = P.load("story.json"); need = len(st["pictures"]) if st else 999
    say("=" * 64 + f"\n ROLL WATCHER  -  story: {(st or {}).get('title', '')}  ({need} pages)\n"
        " Copy any prompt -> Gemini -> download. Each download gets the roll number of the prompt you copied.\n"
        " Keep this window open. Ctrl+C to stop.\n" + "=" * 64)
    snap, taken = snapshot(), set(); queue, last_clip = [], ""
    def have(): return sorted(int(f[4:7]) for f in os.listdir(mp) if f.startswith("pic_") and f[4:7].isdigit())
    try:
        while True:
            try: clip = pyperclip.paste() or ""
            except Exception: clip = ""
            if clip != last_clip:
                last_clip = clip
                m1 = re.search(r"ROLLS\s+0*(\d+)\s*-\s*0*(\d+)", clip); m0 = re.search(r"ROLL\s+0*(\d+)", clip)
                if m1: queue = list(range(int(m1.group(1)), int(m1.group(2)) + 1))
                elif m0: queue = [int(m0.group(1))]
                if m1 or m0: say(f"  copied prompt -> next download(s) will be roll {', '.join(f'{q:03d}' for q in queue)}")
            for f in new_pictures(snap, taken):
                taken.add(f)
                if not queue: say(f"  (download {os.path.basename(f)} ignored - copy a ROLL prompt first)"); continue
                r = queue.pop(0); dst = os.path.join(mp, f"pic_{r:03d}.png")
                if os.path.exists(dst): say(f"  roll {r:03d} already had a picture - replaced with the new one")
                shutil.copy(f, dst); got = have()
                say(f"  saved roll {r:03d}  <-  {os.path.basename(f)}   |   done {len(got)} of {need}")
                if len(got) >= need: say("\n  ALL ROLLS SAVED -> now ONE_CLICK.bat")
            time.sleep(0.7)
    except KeyboardInterrupt:
        missing = [i for i in range(1, need + 1) if i not in have()]
        say(f"\n  stopped. missing rolls: {missing[:30]}{' ...' if len(missing) > 30 else ''}")


def auto(minutes=4.0, unattended=False):
    """ONE CLICK. No open story -> new story. Open story -> pictures -> (missing? wait + re-check) -> video with checks -> doctor."""
    ps = sorted(glob.glob(os.path.join(HERE, "projects", "*")))
    P = S.Project(ps[-1]) if ps else None
    if P is None or os.path.exists(P.p("FINAL_DONE")) or not P.load("story.json"):
        say("=" * 64 + "\n STEP A - NEW STORY (automatic)\n" + "=" * 64)
        if FROM_FOLDER and os.path.isdir(FROM_FOLDER):          # pictures of the previous story -> my_pics\old_<date>
            olds = [f for f in os.listdir(FROM_FOLDER) if f.lower().endswith(IMG_EXT + (".zip",))]
            if olds:
                dst = os.path.join(FROM_FOLDER, "old_" + time.strftime("%Y%m%d_%H%M")); os.makedirs(dst, exist_ok=True)
                for f in olds: shutil.move(os.path.join(FROM_FOLDER, f), os.path.join(dst, f))
                say(f"  {len(olds)} pictures of the previous story moved to {dst} (my_pics is empty for the new story)")
        story(minutes)
        if not unattended:
            P = S.Project(sorted(glob.glob(os.path.join(HERE, "projects", "*")))[-1])
            if os.name == "nt": os.startfile(P.p("PROMPTS_CHAPTERS.txt"))
            say("\n" + "=" * 64 + "\n YOUR TURN: PROMPTS_CHAPTERS.txt is open.\n  Make the pictures in Gemini/Flow and download them (png or zip, any order).\n"
                "  They can stay in Downloads - this window takes them from there.\n" + "=" * 64)
            input("  When the pictures are downloaded, press ENTER ... ")
            return auto(minutes, unattended)
        say("\n" + "=" * 64 + "\n YOUR TURN:\n  1. Open PROMPTS_CHAPTERS.txt (in the folder that just opened)\n"
            "  2. Gemini: paste MASTER once, then each CHAPTER; download the pictures in page order (png or zip)\n"
            "  3. Put ALL of them in the folder  my_pics  (next to ONE_CLICK.bat)\n"
            "  4. Click ONE_CLICK.bat again\n" + "=" * 64); return
    st = P.load("story.json"); need = len(st["pictures"])
    src = FROM_FOLDER or " + ".join(watch_dirs())
    say("=" * 64 + f"\n STORY: {st.get('title', '')}   ({need} pages)\n STEP B - PICTURES from: {src}\n" + "=" * 64)
    import hashlib
    while True:
        cand = candidates(P); clean, seen = [], set()
        for c in cand:
            try: h = hashlib.md5(open(c, "rb").read()).hexdigest()
            except OSError: continue
            if h not in seen: seen.add(h); clean.append(c)
        from PIL import Image as _I
        ok_files, broken = [], []
        for c in clean:
            try:
                with _I.open(c) as _im: _im.verify()
                ok_files.append(c)
            except Exception:
                broken.append(os.path.basename(c))
        if broken: say(f"  BROKEN picture files (not used, download them again): {broken[:10]}")
        clean = ok_files
        if not clean:
            if unattended: say("  No pictures yet."); return
            missing_prompts(P, st, list(range(1, need + 1)))
            input("  No pictures yet. Make them (prompts are open), put them in my_pics, then press ENTER ... "); continue
        intake_report(len(clean), len(cand)); say("  finding the right page for each picture ...")
        chosen, how = match_pages(P, st, clean)
        gaps = [i for i in range(1, need + 1) if i not in chosen]
        say(f"  placed {len(chosen)} of {need} pages ({how})")
        say(f"  CHECK: {len(chosen)} of {need} pages have a picture" + ("  - ALL PRESENT" if not gaps else f" - {len(gaps)} missing"))
        if not gaps or unattended: break
        f = missing_prompts(P, st, gaps)
        say(f"\n  MISSING pages: {gaps[:20]}{' ...' if len(gaps) > 20 else ''}\n  Their full prompts are open in Notepad: {f}")
        ans = input("  Make them, download them (Downloads is fine), then press ENTER to check again  (or V + ENTER = video now): ").strip().lower()
        if ans == "v": break
    fresh_pics_dir(P)
    from PIL import Image
    import io as _io
    for i, c in sorted(chosen.items()):
        with Image.open(c) as _im:
            b = _io.BytesIO(); _im.convert("RGB").save(b, "PNG")
        S.clean_frame(b.getvalue(), P.p(pics_dir(P), f"{i:03d}.png"))
    say(f"  saved {len(chosen)} pictures on their pages" + (f" | still missing (they show the page before): {gaps[:15]}" if gaps else ""))
    sheet = order_sheet(P, st); say(f"  order sheet: {sheet}")
    say("\n STEP C - AI CHECK of the pictures (max 90 s, Groq) ...")
    bad = ai_order_check(P, st)
    if bad: say(f"  AI thinks these pages may not match their moment: {bad}  (see CHECK_ORDER.jpg; video continues)")
    elif bad == []: say("  AI: all checked pictures match their story moment")
    say("\n STEP D - VIDEO")
    video(True)
    open(P.p("FINAL_DONE"), "w").write(time.strftime("%Y-%m-%d %H:%M"))
    if os.getenv("M2_AUTO_UPLOAD", "1") == "1" and os.path.exists(os.path.join(HERE, "youtube_token.json")):
        say("\n STEP E - YOUTUBE UPLOAD")
        try:
            import upload as U
            info = U.upload_m2(P)
            say(f"  {'UPLOADED ' + info['url'] + ' (' + info['mode'] + ')' if info else 'not uploaded (see above)'}")
        except SystemExit as e: say(f"  upload skipped: {e}")
        except Exception as e: say(f"  upload ERROR: {str(e)[:200]}")
    elif os.getenv("M2_AUTO_UPLOAD", "1") == "1":
        say("\n  (YouTube upload is off: run YOUTUBE_LOGIN.bat once to switch it on)")

# ------------------------------------------------------------------ 3) video: pictures follow the voice
def word_starts(P, st, total, TI=0.0):
    """for every part: list of (start time of each word, the word) inside the one voice; None if the voice gave no word times"""
    marks = [m for m in P.load("voice_marks.json", []) if m.get("kind") == "WordBoundary"]
    lens = [len(b["narration"].split()) for b in st["beats"]]
    if not marks or len(marks) < sum(lens) * 0.8: return None
    out, k = [], 0
    for bi, b in enumerate(st["beats"]):
        ws = b["narration"].split(); out.append([(marks[min(k + j, len(marks) - 1)]["t"] + TI, ws[j]) for j in range(len(ws))]); k += len(ws)
    return out


def synced_slots(words, a, b, n, min_len, max_len=None):
    """split one part into n picture slots, evenly in TIME, each cut at the moment the narrator reaches a word (preferably right after a , । ! ?
    within 1.2 s of the ideal time). Slots are never shorter than min_len and, if max_len is given, never longer (else plain even slots)."""
    if not words or n <= 1: return [(a, b)]
    n = max(1, min(n, int((b - a) // min_len)))
    if n <= 1: return [(a, b)]
    times = [w[0] for w in words]; W = len(words); cuts = []
    for k in range(1, n):
        ideal = a + (b - a) * k / n
        cand = [j for j in range(1, W) if abs(times[j] - ideal) <= 1.2] or [min(range(1, W), key=lambda j: abs(times[j] - ideal))]
        pool = [j for j in cand if words[j - 1][1][-1:] in ",।!?;"] or cand
        cuts.append(min(pool, key=lambda j: abs(times[j] - ideal)))
    cuts = sorted(set(c for c in cuts if 0 < c < W))
    starts = [a] + [max(a, times[c] - 0.25) for c in cuts]           # change a moment BEFORE the word (the dissolve lands on it)
    slots = [(starts[i], starts[i + 1] if i + 1 < len(starts) else b) for i in range(len(starts))]
    merged = []                                                      # never shorter than min_len
    for s0, s1 in slots:
        if merged and s1 - s0 < min_len: merged[-1] = (merged[-1][0], s1)
        else: merged.append((s0, s1))
    if len(merged) > 1 and merged[-1][1] - merged[-1][0] < min_len: merged[-2] = (merged[-2][0], merged[-1][1]); merged.pop()
    if max_len and any(s1 - s0 > max_len for s0, s1 in merged):     # snapping made one too long -> plain even slots in time
        merged = [(a + (b - a) * k / n, a + (b - a) * (k + 1) / n) for k in range(n)]
    return merged


def beat_times(P, st, total):
    """start time of every beat inside the one continuous voice (word timings; else by length of text)"""
    marks = [m for m in P.load("voice_marks.json", []) if m.get("kind") == "WordBoundary"]
    lens = [len(b["narration"].split()) for b in st["beats"]]
    starts = []
    if marks and len(marks) >= sum(lens) * 0.8:
        k = 0
        for n in lens:
            starts.append(marks[min(k, len(marks) - 1)]["t"]); k += n
    else:
        chars = [len(b["narration"]) for b in st["beats"]]; acc = 0
        for c in chars:
            starts.append(total * acc / sum(chars)); acc += c
    return starts + [total]


TONES = {"happy": ("+3%", "+4Hz", "+3%"), "sad": ("-10%", "-6Hz", "-6%"), "serious": ("-6%", "-3Hz", "+0%")}


def short_voice(P, name, text, tone):
    """a short separate line (title at the start, moral at the end) spoken with the right feeling"""
    out = P.p(f"{name}.mp3")
    if os.path.exists(out) and os.path.getsize(out) > 2000: return out
    try:
        v, rate, pitch = S.NARRATOR["edge"]; r2, p2, vol = TONES.get(tone, TONES["happy"])
        add0 = lambda a, b, u: f"{int(a.replace(u, '').replace('+', '')) + int(b.replace(u, '').replace('+', '')):+d}{u}"
        if azure_tts(text, out, add0(rate, r2, "%"), add0(pitch, p2, "Hz"), vol, want_marks=False, limit=90) is not None and os.path.getsize(out) > 2000:
            return out
        import edge_tts
        add = lambda a, b, u: f"{int(a.replace(u, '').replace('+', '')) + int(b.replace(u, '').replace('+', '')):+d}{u}"
        com = edge_tts.Communicate(text, v, rate=add(rate, r2, "%"), pitch=add(pitch, p2, "Hz"), volume=vol)
        data = _with_timeout(lambda: b"".join(ch["data"] for ch in com.stream_sync() if ch["type"] == "audio"), 90)
        if not data: say(f"  ({name} voice: no answer in 90 s - skipped)"); return None
        open(out, "wb").write(data)
        return out if os.path.getsize(out) > 2000 else None
    except Exception as e:
        print(f"  ({name} voice not made: {str(e)[:60]})"); return None


def moral_tone(st):
    if MYSTERY: return "serious"
    t = str(st.get("moral_tone", "")).lower()
    if t in TONES: return t
    m = str(st.get("moral", ""))
    return "sad" if any(w in m for w in ("दुख", "पछता", "नुकसान", "विनाश", "बर्बाद")) else "happy"


def main_character_picture(P, st, pics):
    from collections import Counter
    cnt = Counter(n for p in st["pictures"] for n in p.get("characters", []))
    hero = cnt.most_common(1)[0][0] if cnt else None
    for i, p in enumerate(st["pictures"], 1):
        f = P.p(pics_dir(P), f"{i:03d}.png")
        if hero in p.get("characters", []) and os.path.exists(f): return f
    return pics[0]


def make_music(path, seconds, tone="happy", sr=24000):
    """our own soft village-style background music (no copyright): warm pad chords + gentle flute-like melody + echo"""
    import numpy as np
    rng = np.random.default_rng(7)
    minor = tone == "sad"
    root = 220.0 * (2 ** (-2 / 12) if minor else 1)                     # A3 (G3 for sad)
    scale = [0, 2, 3, 5, 7, 8, 10] if minor else [0, 2, 4, 5, 7, 9, 11]
    prog = [[0, 3, 5], [5, 0, 3], [3, 5, 0], [4, 6, 1]] if minor else [[0, 2, 4], [4, 6, 1], [5, 0, 2], [3, 5, 0]]   # I-V-vi-IV / i-VI-iv-v
    bar = 4.0 if not minor else 5.0
    n = int(seconds * sr); t = np.arange(n) / sr; out = np.zeros(n)
    def note(deg, octave=0):
        return root * 2 ** ((scale[deg % 7] + 12 * (deg // 7) + 12 * octave) / 12)
    for b in range(int(seconds / bar) + 1):                             # pad: soft triangle-like chords, slow fade in/out
        s0, s1 = int(b * bar * sr), min(n, int((b + 1) * bar * sr) + int(0.8 * sr))
        if s0 >= n: break
        tt = t[s0:s1] - b * bar; env = np.minimum(1, tt / 1.2) * np.minimum(1, np.maximum(0, (bar + 0.8 - tt) / 1.2))
        for deg in prog[b % 4]:
            f = note(deg, -1)
            out[s0:s1] += 0.10 * env * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt) + 0.08 * np.sin(6 * np.pi * f * tt))
    step = bar / 2 if not minor else bar                                 # melody: a few soft notes per bar (flute-like)
    k = 0; tm = 1.0
    while tm < seconds - 1:
        deg = prog[int(tm / bar) % 4][rng.integers(0, 3)] + 7 * int(rng.integers(0, 2)); f = note(deg)
        s0, s1 = int(tm * sr), min(n, int((tm + step * 0.95) * sr)); tt = t[s0:s1] - tm
        env = np.minimum(1, tt / 0.15) * np.exp(-tt / (step * 0.6))
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5 * tt)
        out[s0:s1] += 0.07 * env * (np.sin(2 * np.pi * f * vib * tt) + 0.15 * np.sin(4 * np.pi * f * vib * tt))
        tm += step * (1 if rng.random() > 0.3 else 2); k += 1
    d = int(0.33 * sr); echo = np.zeros(n); echo[d:] = out[:-d] * 0.35; out = out + echo   # soft echo
    fade = int(2.5 * sr); out[:fade] *= np.linspace(0, 1, fade); out[-fade:] *= np.linspace(1, 0, fade)
    out = out / (np.abs(out).max() + 1e-9) * 0.6
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((out * 32767).astype(np.int16).tobytes())
    return path


def pick_music(P, seconds, tone):
    """an mp3 from the music folder (mood word in the name preferred), otherwise our own music"""
    md = os.path.join(HERE, "music"); files = sorted(glob.glob(os.path.join(md, "*.mp3")) + glob.glob(os.path.join(md, "*.wav")))
    if not files: files = sorted(glob.glob(os.path.join(HERE, "*.mp3")))          # flat GitHub repo: music next to m2.py
    if files:
        words = {"happy": ("happy", "joy", "bright", "khush"), "sad": ("sad", "emotional", "slow", "dukh"), "serious": ("calm", "soft", "serious")}[tone]
        if MYSTERY: words = ("mystery", "suspense", "dark") + words
        groups = ([("mystery", "suspense", "dark")] if MYSTERY else []) + [words]      # the first group that has a file wins
        good = next((g for g in ([f for f in files if any(w in os.path.basename(f).lower() for w in grp)] for grp in groups) if g), files)
        return good[hash(P.dir) % len(good)], "from the music folder"
    return make_music(P.p("work_music.wav"), seconds, tone), "made by the script (no copyright)"


def autopilot(minutes=4.0, every=120):
    """background loop: story ready? pictures complete (or 80%+ and no new picture for M2_WAIT_MINUTES)? -> video -> upload -> next story"""
    global FROM_FOLDER
    FROM_FOLDER = FROM_FOLDER or os.path.join(HERE, "my_pics"); os.makedirs(FROM_FOLDER, exist_ok=True)
    wait_min = float(os.getenv("M2_WAIT_MINUTES", "45"))
    log = os.path.join(HERE, "autopilot_log.txt")
    def note(x):
        say(time.strftime("%H:%M ") + x); open(log, "a", encoding="utf-8").write(time.strftime("%Y-%m-%d %H:%M ") + x + "\n")
    note("AUTOPILOT started - watching " + FROM_FOLDER)
    last_count, last_change = -1, time.time()
    while True:
        try:
            ps = sorted(glob.glob(os.path.join(HERE, "projects", "*")))
            P = S.Project(ps[-1]) if ps else None
            if P is None or os.path.exists(P.p("FINAL_DONE")) or not P.load("story.json"):
                note("no open story -> making a new one"); auto(minutes, unattended=True)
                P = S.Project(sorted(glob.glob(os.path.join(HERE, "projects", "*")))[-1])
                note(f"NEW STORY ready: {P.load('story.json').get('title', '')} - make the pictures (PROMPTS_CHAPTERS.txt) into my_pics")
                last_count, last_change = -1, time.time()
            st = P.load("story.json"); need = len(st["pictures"])
            n = len(candidates(P))
            if n != last_count:
                if n > 0: note(f"pictures in my_pics: {n} of {need}")
                last_count, last_change = n, time.time()
            idle = (time.time() - last_change) / 60
            if n >= need or (n >= 0.8 * need and idle >= wait_min):
                note(f"making the video ({n}/{need} pictures)"); auto(minutes, unattended=True)
                note("video done" + (" + uploaded" if os.path.exists(P.p("UPLOADED.json")) else ""))
                last_count, last_change = -1, time.time()
                continue
        except KeyboardInterrupt:
            note("AUTOPILOT stopped"); return
        except Exception as e:
            note(f"ERROR (will try again): {str(e)[:200]}")
        try:
            time.sleep(every)
        except KeyboardInterrupt:
            note("AUTOPILOT stopped"); return


ATMO_WORDS = {
    "birds":   ("field", "village", "sky", "sunrise", "morning", "evening", "sunset", "farm", "river", "tree", "outside", "road", "path"),
    "leaves":  ("tree", "banyan", "field", "village", "garden", "forest", "farm", "path", "autumn", "wind"),
    "glow":    ("sunrise", "sunset", "morning", "evening", "dawn", "dusk", "golden", "sun"),
    "fireflies": ("night", "moon", "dark", "stars", "lamp"),
    "rain":    ("rain", "storm", "monsoon", "flood", "thunder"),
    "smoke":   ("kitchen", "chulha", "stove", "fire", "cooking", "hearth", "lamp"),
}


def atmosphere_for(place):
    if REALISTIC: return {"fog"} if MYSTERY else set()                 # real footage: no drawn birds/leaves, only a soft mist for mystery
    pl = (place or "").lower()
    fx = {k for k, words in ATMO_WORDS.items() if any(w in pl for w in words)}
    if "rain" in fx: fx -= {"birds", "glow", "fireflies"}
    if "fireflies" in fx: fx -= {"birds", "glow"}
    return fx or {"leaves"}


class Atmosphere:
    """gentle living details drawn over the picture: birds, falling leaves, warm sun glow, fireflies, rain, smoke"""
    def __init__(self, seed=5):
        import random
        r = random.Random(seed)
        self.birds = [[r.uniform(-300, 1280), r.uniform(40, 220), r.uniform(25, 45), r.uniform(0, 6.28), r.uniform(.7, 1.2)] for _ in range(5)]
        self.leaves = [[r.uniform(0, 1280), r.uniform(-720, 0), r.uniform(18, 35), r.uniform(0, 6.28), r.uniform(.6, 1.3)] for _ in range(9)]
        self.flies = [[r.uniform(0, 1280), r.uniform(200, 700), r.uniform(0, 6.28)] for _ in range(26)]
        self.drops = [[r.uniform(0, 1400), r.uniform(0, 720), r.uniform(500, 800)] for _ in range(160)]
    def draw(self, img, t, fx, strength=1.0):
        from PIL import Image, ImageDraw, ImageFilter
        import numpy as np
        if not fx or strength <= 0: return img
        layer = Image.new("RGBA", (1280, 720), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        a = int(255 * strength)
        if "birds" in fx:
            for b in self.birds:
                x = (b[0] + b[2] * t) % 1700 - 200; y = b[1] + 8 * math.sin(t * .6 + b[3]); w = 9 * b[4]
                flap = 4 * math.sin(t * 7 + b[3])
                d.line([(x - w, y - flap), (x, y), (x + w, y - flap)], fill=(40, 35, 45, int(a * .8)), width=2)
        if "leaves" in fx:
            for lf in self.leaves:
                y = (lf[1] + lf[2] * t) % 900 - 100; x = lf[0] + 40 * math.sin(t * .8 + lf[3]); ang = t * 1.5 + lf[3]
                pts = [(x + 7 * lf[4] * math.cos(ang + k * math.pi / 2) * (1.8 if k % 2 == 0 else .7), y + 7 * lf[4] * math.sin(ang + k * math.pi / 2) * (1.8 if k % 2 == 0 else .7)) for k in range(4)]
                d.polygon(pts, fill=(170, 120, 40, int(a * .75)))
        if "fireflies" in fx:
            for f in self.flies:
                x = f[0] + 30 * math.sin(t * .5 + f[2]); y = f[1] + 20 * math.cos(t * .4 + f[2]); g = int(a * (.4 + .6 * max(0, math.sin(t * 2.2 + f[2]))))
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 240, 140, g))
        if "rain" in fx:
            for r_ in self.drops:
                y = (r_[1] + r_[2] * t) % 760 - 40; x = (r_[0] - .35 * r_[2] * t) % 1400 - 60
                d.line([(x, y), (x - 6, y + 18)], fill=(210, 220, 235, int(a * .55)), width=1)
        if "fog" in fx:                                              # slow drifting mist
            for k in range(6):
                ph = (t * 0.03 + k / 6) % 1; x = -300 + ph * 1900; y = 430 + 120 * math.sin(k * 1.7 + t * 0.2); rr = 260 + 60 * math.sin(k)
                d.ellipse((x - rr, y - rr * 0.35, x + rr, y + rr * 0.35), fill=(225, 230, 240, int(a * 0.10)))
        if "smoke" in fx:
            for k in range(7):
                ph = (t * .12 + k / 7) % 1; x = 640 + 60 * math.sin(t * .7 + k) + ph * 40; y = 640 - ph * 420; rr = 18 + ph * 60
                d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(235, 235, 235, int(a * .18 * (1 - ph))))
        layer = layer.filter(ImageFilter.GaussianBlur(1.1))
        base = Image.fromarray(img.clip(0, 255).astype("uint8")).convert("RGBA"); base.alpha_composite(layer)
        out = np.asarray(base.convert("RGB")).astype("float32")
        if "glow" in fx:                                         # warm sun glow, slowly breathing, top of the picture
            yy, xx = np.mgrid[0:720:8, 0:1280:8]
            g = np.exp(-(((xx - 980) / 420.0) ** 2 + ((yy - 90) / 260.0) ** 2)) * (0.16 + 0.05 * math.sin(t * .9)) * strength
            g = np.kron(g, np.ones((8, 8)))[:720, :1280, None]
            out = out * (1 - g) + np.array([255, 214, 150], "float32") * g
        if "rain" in fx: out = out * (1 - .12 * strength)
        return out


def corner_logo():
    """the channel logo for the top-right corner (CORNER_LOGO.png next to m2.py); None if missing or switched off"""
    if os.getenv("M2_LOGO", "1") == "0": return None
    f = os.path.join(HERE, "CORNER_LOGO.png")
    if not os.path.exists(f): return None
    import numpy as np
    from PIL import Image
    w = int(os.getenv("M2_LOGO_WIDTH", "180")); op = float(os.getenv("M2_LOGO_OPACITY", "0.9"))   # small, tucked in the corner
    with Image.open(f) as im:
        im = im.convert("RGBA"); im = im.resize((w, max(1, int(w * im.size[1] / im.size[0]))), Image.LANCZOS)
    a = np.asarray(im).astype("float32"); alpha = a[..., 3:4] / 255.0 * op
    x0, y0 = 1280 - w - 14, 12                                   # 14 px from the right edge, 12 px from the top
    return (x0, y0, a[..., :3], alpha)


class ClipFrames:
    """frames of an AI clip (clips/NNN.mp4) for the page that is being shown. The decoded frames live in a temporary file on the DISK
    (memory-mapped), not in RAM - a 5-s clip would otherwise need 415 MB (twice while two clips melt into each other)."""
    def __init__(self):
        self.path, self.frames, self._tmp = None, [], None
    def _drop(self):
        self.frames = []
        if self._tmp:
            try: os.remove(self._tmp)
            except OSError: pass
            self._tmp = None
    def _load(self, path):
        import numpy as np, tempfile
        if path == self.path: return
        self._drop(); self.path = path
        fd, tmp = tempfile.mkstemp(suffix=".raw", prefix="m2clip_"); os.close(fd)
        import atexit; atexit.register(lambda t=tmp: os.path.exists(t) and os.remove(t))      # never leave the big temp file behind, even if the run stops
        subprocess.run([S.ffmpeg(), "-y", "-v", "quiet", "-i", path, "-vf", "scale=1280:720:flags=lanczos,fps=30", "-f", "rawvideo", "-pix_fmt", "rgb24", tmp])
        n = os.path.getsize(tmp) // (1280 * 720 * 3)
        if n < 1: os.remove(tmp); return
        self._tmp = tmp; self.frames = np.memmap(tmp, dtype=np.uint8, mode="r", shape=(n, 720, 1280, 3))
    def get(self, path, k):
        import numpy as np
        self._load(path); n = len(self.frames)
        if not n: return None
        return np.asarray(self.frames[max(0, min(k, n - 1))]).astype("float32")      # never plays backwards; the last frame is held
    def get_f(self, path, pos):
        """the frame at a fractional position (30 frames per second): the two neighbours are blended, so slow motion stays smooth"""
        import numpy as np
        self._load(path); n = len(self.frames)
        if not n: return None
        pos = max(0.0, min(float(pos), n - 1.0)); i = int(pos); f = pos - i
        a_ = np.asarray(self.frames[i]).astype("float32")
        if f < 0.02 or i + 1 >= n: return a_
        return a_ * (1 - f) + np.asarray(self.frames[i + 1]).astype("float32") * f
    def __del__(self):
        try: self._drop()
        except Exception: pass


def clip_for(P, picture_path):
    """clips/NNN.mp4 for picture NNN.png (made by Kaggle), if it is there and plays"""
    c = P.p("clips", os.path.splitext(os.path.basename(picture_path))[0] + ".mp4")
    return c if os.path.exists(c) and os.path.getsize(c) > 5000 else None


def say(msg):
    print(msg, flush=True)


def video(subtitles=True):
    P = latest(); st = P.load("story.json"); ff = S.ffmpeg()
    say("\n[VIDEO 1/5] Reading the voice and the pictures ...")
    vo = P.p("FULL_VOICE.mp3")
    if not os.path.exists(vo): sys.exit("  FULL_VOICE.mp3 missing - make the story again (ONE_CLICK.bat)")
    if not S.audio_ok(vo):                                       # FIX AT ONCE: broken/silent story voice -> make it again
        say("  [fixed] FULL_VOICE.mp3 was silent/broken - making the voice again")
        voice(P, " ".join(b["narration"].strip() for b in st["beats"]))
    total = S.probe(vo)[0] + 0.8
    pics = sorted(glob.glob(P.p(pics_dir(P), "*.png")))
    if not pics: sys.exit("  No pictures - run ONE_CLICK.bat first")
    from PIL import Image
    import numpy as np, io as _io
    broken = []
    for f in pics:                                              # LIVE CHECK 1: every picture opens and is 16:9
        try:
            with Image.open(f) as im:
                size = im.size; data = None
                if size != (1280, 720):
                    b = _io.BytesIO(); im.convert("RGB").save(b, "PNG"); data = b.getvalue()
            if data: S.clean_frame(data, f)
        except Exception:
            broken.append(os.path.basename(f))
    say(f"  voice {total / 60:.1f} min | pictures {len(pics)} of {len(st['pictures'])}" + (f" | BROKEN files: {broken}" if broken else ""))
    if len(pics) < len(st["pictures"]) * 0.5:
        sys.exit(f"\n  STOP: only {len(pics)} of {len(st['pictures'])} pictures - a video now would show the same picture again and again.\n"
                 f"  Put the pictures in my_pics and run ONE_CLICK.bat (it takes them from there).")
    pics = [f for f in pics if os.path.basename(f) not in broken]
    have = {int(os.path.basename(f)[:3]): f for f in pics}
    beat_of = {i + 1: p_.get("beat") for i, p_ in enumerate(st["pictures"])}
    miss_ = [i for i in range(1, len(st["pictures"]) + 1) if i not in have]
    if miss_: say(f"  WARNING: {len(miss_)} pages have no picture of their own: {miss_[:20]}")
    def pic_for(n):                                             # page without a picture -> nearest picture of the same part, else the nearest earlier one
        if n in have: return have[n]
        same = [k for k in have if beat_of.get(k) == beat_of.get(n)]
        if same: return have[min(same, key=lambda k: abs(k - n))]
        for k in range(n, 0, -1):
            if k in have: return have[k]
        return pics[0]
    say("[VIDEO 2/5] Title card + moral card + every picture timed to its spoken words ...")
    tone = moral_tone(st)
    hook = st.get("hook", "") if os.getenv("M2_HOOK", "1") == "1" else ""
    intro_text = (f"{hook} आज की कहानी: {st.get('title', '')}।" if hook else f"आज की कहानी है, {st.get('title', '')}।")
    intro_v = short_voice(P, "INTRO_VOICE", intro_text, "serious" if (hook and MYSTERY) else "happy")
    if hook: say(f"  HOOK opening: {hook}")
    outro_v = short_voice(P, "MORAL_VOICE", f"तो दोस्तों, इस कहानी से हमें यह सीख मिलती है, {st.get('moral', '')}", tone)
    TI = (S.probe(intro_v)[0] + 1.2) if intro_v else 3.5
    TO = (S.probe(outro_v)[0] + 1.5) if outro_v else 4.0
    story_len = total; total = TI + story_len + TO
    bt = [x + TI for x in beat_times(P, st, story_len)]
    P.save("timeline.json", {"intro": TI, "story": story_len, "outro": TO, "total": total, "beat_times": bt, "hook_part": st.get("hook_part", 0)})   # for the Short
    marks = len([m for m in P.load("voice_marks.json", []) if m.get("kind") == "WordBoundary"])
    say(f"  title card {TI:.1f} s | story {story_len:.0f} s | moral card {TO:.1f} s ({tone} voice)")
    say(f"  {len(st['beats'])} story parts timed " + ("word-by-word from the voice" if marks else "by text length (voice gave no word times)"))
    hook_pic = None
    if hook:                                                        # the strangest moment's own (moving) clip opens the video
        hp = int(st.get("hook_part", 0)); idx = [i + 1 for i, p_ in enumerate(st["pictures"]) if p_.get("beat") == hp]
        if idx: hook_pic = pic_for(idx[0])
    plan = [(0.0, TI, hook_pic or main_character_picture(P, st, pics), -1)]
    ws = word_starts(P, st, story_len, TI)
    flip = os.getenv("M2_STYLE", "story").lower() == "flip"        # old fast flip-book only if asked for
    HOLD = float(os.getenv("M2_FLIP_SECONDS", "1.2"))
    for bi in range(len(st["beats"])):
        mine = [pic_for(i + 1) for i, p in enumerate(st["pictures"]) if p["beat"] == bi] or [pics[0]]
        a, b = bt[bi], bt[bi + 1]
        if flip:
            seq = mine + mine[-2:0:-1] if len(mine) > 2 else mine; t = a; k = 0
            while t < b - 0.05:
                plan.append((t, min(b, t + HOLD), seq[k % len(seq)], bi)); t += HOLD; k += 1
        else:                                                    # VOICE-SYNCED: a picture appears when its words are spoken
            MIN = float(os.getenv("M2_MIN_SECONDS", "3.5"))
            slots = synced_slots(ws[bi] if ws else None, a, b, len(mine), MIN, float(os.getenv("M2_MAX_PAGE_SECONDS", "6.4")) + 0.8) if ws else None
            if not slots:
                fit = max(1, min(len(mine), int((b - a) // MIN))); slots = [(a + (b - a) * j / fit, a + (b - a) * (j + 1) / fit) for j in range(fit)]
            use = [mine[round(k * (len(mine) - 1) / max(1, len(slots) - 1))] for k in range(len(slots))] if len(slots) < len(mine) else mine
            for cf in [f for f in mine if clip_for(P, f)]:          # a page with an AI clip is never left out
                if cf not in use and use:
                    ci = mine.index(cf); j = min(range(len(use)), key=lambda q: abs(mine.index(use[q]) - ci) + (99 if clip_for(P, use[q]) else 0))
                    use[j] = cf
            use = sorted(dict.fromkeys(use), key=mine.index) + [use[-1]] * (len(slots) - len(dict.fromkeys(use)))
            for (s0, s1), f in zip(slots, use):
                plan.append((s0, s1, f, bi))
    plan.append((TI + story_len, total, pic_for(len(st["pictures"])), -2))
    avg = (story_len / max(1, len(plan) - 2))
    say(f"  {len(plan)} pictures planned, in story order" + (", each one appears when its words are spoken" if ws else "") +
        f", about {avg:.1f} s each, soft melts (1 s between clips, one continuous camera)")
    cache = {}
    healed = []
    def big(path):
        if path not in cache:
            if len(cache) > 24: cache.pop(next(iter(cache)))
            try:
                with Image.open(path) as _im: cache[path] = _im.convert("RGB").resize((1408, 792), Image.LANCZOS)
            except Exception:                                   # FIX AT ONCE: use the last good picture
                good = next((v for v in reversed(list(cache.values()))), None) or Image.new("RGB", (1408, 792), (40, 40, 40))
                cache[path] = good; healed.append(os.path.basename(path)); say(f"  [fixed] {os.path.basename(path)} would not open - using the picture before it")
        return cache[path]
    def cam(path, t):                                           # ONE slow camera path for the whole film - never jumps
        z = 0.03 + 0.02 * math.sin(2 * math.pi * t / 83.0)        # very slow breathing zoom
        w, h = 1408 / (1 + z), 792 / (1 + z)
        cx = 0.5 + 0.25 * math.sin(2 * math.pi * t / 97.0); cy = 0.45 + 0.10 * math.sin(2 * math.pi * t / 113.0)
        x = (1408 - w) * cx; y = (792 - h) * cy
        return np.asarray(big(path).crop((int(x), int(y), int(x + w), int(y + h))).resize((1280, 720), Image.BILINEAR)).astype(np.float32)
    say("[VIDEO 3/5] Drawing the video (progress every 15 s of film) ...")
    out_v = P.p("work_video.mp4"); fps = int(os.getenv("M2_FPS", "30")); n = int(total * fps)
    enc = subprocess.Popen([ff, "-y", "-v", "quiet", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1280x720", "-r", str(fps), "-i", "-",
                            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", "-preset", "fast", out_v], stdin=subprocess.PIPE)
    pi, dark, t_start = 0, 0, time.time()
    logo = None if os.getenv("M2_1080", "1") == "1" else corner_logo()   # at 1080p the logo is added later, sharp, at full size
    if logo is not None: say("  channel logo in the top-right corner")
    clipper, clipper2 = ClipFrames(), ClipFrames()
    n_clips = len({os.path.basename(f) for _, _, f, _ in plan if clip_for(P, f)})
    if n_clips: say(f"  {n_clips} pages play a real AI clip (characters move), the others are living pictures")
    try: chained = set(json.load(open(P.p("clips", "chained.json"))))   # clips made from the last frame of the clip before (Kaggle chains)
    except Exception: chained = set()
    if chained: say(f"  {len(chained)} clips continue the clip before them -> no cut there (one continuous shot)")
    def seamless(f, nf):
        return bool(nf and os.path.basename(nf) in chained and clip_for(P, f) and clip_for(P, nf))
    def xf_of(i):
        """melt length between plan[i] and plan[i+1] (same rules as the drawing loop)"""
        a_, b_, f_, _ = plan[i]; nf_ = plan[i + 1][2] if i + 1 < len(plan) else None
        if not nf_ or nf_ == f_: return 0.0
        near = bool(clip_for(P, f_) or clip_for(P, nf_))
        return min(float(os.getenv("M2_CLIP_MELT", "2.0")) if near else 1.2, (b_ - a_) * 0.45)   # slow, soft 2-s change (like the picture videos)
    LEAD = [0.0] + [(xf_of(i) if clip_for(P, plan[i + 1][2]) else 0.0) for i in range(len(plan) - 1)]   # the incoming clip already PLAYS during the melt
    def clip_speed(n_, span, ends):
        if not n_ or span <= 0: return 1.0
        return min(1.0, max(float(os.getenv("M2_CLIP_MIN_SPEED", "0.62")), (n_ / 30.0) / span))   # never faster than real speed; down to 0.62x so a clip covers a page up to 8 s
    def frame_for(f, t, a, b=None, ends=False, lead=0.0):
        c = clip_for(P, f)
        if c:
            fr_ = (clipper if c == clipper.path or clipper.path is None or c != clipper2.path else clipper2)
            fr_.get(c, 0); n_ = len(fr_.frames)
            speed = clip_speed(n_, (b - a) + lead, ends) if b else 1.0          # longer page -> a little slower; chain -> reach the last frame at the join
            img_ = fr_.get_f(c, ((t - a) + lead) * 30 * speed)
            if img_ is not None: return clip_camera(img_, t)
        return cam(f, t)
    def clip_camera(img_, t):
        """the same slow camera for every clip, running through the cuts (gentle breathing zoom + drift) -> clips feel like one film"""
        if os.getenv("M2_CLIP_CAMERA", "1") != "1": return img_
        from PIL import Image as _I
        import numpy as _np
        z = 1.045 + 0.025 * math.sin(2 * math.pi * t / 23.0)            # 1.02 .. 1.07, one slow breath every 23 s
        dx = 0.5 + 0.18 * math.sin(2 * math.pi * t / 31.0); dy = 0.5 + 0.12 * math.sin(2 * math.pi * t / 37.0 + 1.0)
        cw, ch = 1280 / z, 720 / z; x0 = (1280 - cw) * dx; y0 = (720 - ch) * dy
        im_ = _I.fromarray(img_.clip(0, 255).astype("uint8")).resize((1280, 720), _I.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))
        return _np.asarray(im_).astype("float32")
    atmo = Atmosphere(); fxs = [atmosphere_for(b.get("place", "") or (st["pictures"][0].get("place", "") if st["pictures"] else "")) for b in st["beats"]]
    for bi_, fx_ in enumerate(fxs[:6]): say(f"  part {bi_ + 1} living details: {', '.join(sorted(fx_))}")
    for fr in range(n):
        t = fr / fps
        while pi < len(plan) - 1 and t >= plan[pi][1]: pi += 1
        a, b, f, bi = plan[pi]
        nf_ = plan[pi + 1][2] if pi + 1 < len(plan) else None
        img = frame_for(f, t, a, b, ends=seamless(f, nf_), lead=LEAD[pi])
        if pi + 1 < len(plan) and plan[pi + 1][2] != f:         # LONG dissolve: the picture melts into the next one
            XF = xf_of(pi)                                              # the same slow 2-s change everywhere
            if t > b - XF:
                w = (t - (b - XF)) / XF; w = w * w * w * (w * (w * 6 - 15) + 10)   # smoother-step: starts and ends very softly
                nf = plan[pi + 1][2]; nc = clip_for(P, nf)
                nxt = None
                if nc:                                                   # the next clip is already PLAYING during the melt (never a frozen first frame)
                    clipper2.get(nc, 0); a2, b2 = plan[pi + 1][0], plan[pi + 1][1]
                    nf2 = plan[pi + 2][2] if pi + 2 < len(plan) else None
                    sp2 = clip_speed(len(clipper2.frames), (b2 - a2) + XF, seamless(nf, nf2))
                    nxt = clipper2.get_f(nc, (t - (b - XF)) * 30 * sp2)
                if nxt is not None: nxt = clip_camera(nxt, t)            # the incoming clip gets the same camera -> no jump when the melt ends
                img = img * (1 - w) + (nxt if nxt is not None else cam(nf, t)) * w
        if os.getenv("M2_ATMOSPHERE", "1") != "0" and bi >= 0:   # living details of this part's place
            img = atmo.draw(img, t, fxs[bi], float(os.getenv("M2_ATMOSPHERE_STRENGTH", "1.0")))
        if logo is not None:                                     # channel logo, always in the top-right corner
            lx, ly, lrgb, la = logo; h_, w_ = la.shape[:2]
            img[ly:ly + h_, lx:lx + w_] = img[ly:ly + h_, lx:lx + w_] * (1 - la) + lrgb * la
        if fr % fps == 0 and img.mean() < 10: dark += 1         # LIVE CHECK 2: black picture
        enc.stdin.write(img.clip(0, 255).astype(np.uint8).tobytes())
        if fr % (fps * 15) == 0 and fr:
            where = "title card" if bi == -1 else ("moral card" if bi == -2 else f"part {bi + 1}/{len(st['beats'])}")
            say(f"  ... {int(t)} s of {int(total)} s done  ({where}, picture {os.path.basename(f)}, {time.time() - t_start:.0f} s so far)")
    enc.stdin.close(); enc.wait()
    say("[VIDEO 4/5] Adding the voice" + (" and Hindi subtitles" if subtitles else "") + " ...")
    out = P.p("FINAL.mp4"); full_a = P.p("work_audio.wav"); ins, flt = [], []
    for path, delay in ([(intro_v, 0.4)] if intro_v else []) + [(vo, TI)] + ([(outro_v, TI + story_len + 0.5)] if outro_v else []):
        k = len(ins) // 2; ins += ["-i", path]; flt.append(f"[{k}:a]aresample=24000,adelay={int(delay * 1000)}:all=1[a{k}]")
    n_in = len(ins) // 2
    music_on = os.getenv("M2_MUSIC", "1") != "0"
    if music_on:
        mfile, mfrom = pick_music(P, total, tone); say(f"  background music: {os.path.basename(mfile)} ({mfrom})")
        ins += ["-stream_loop", "-1", "-i", mfile]; mi = n_in
        vol = float(os.getenv("M2_MUSIC_VOLUME", "0.18"))
        fc = (";".join(flt) + ";" + "".join(f"[a{i}]" for i in range(n_in)) + f"amix=inputs={n_in}:normalize=0,apad,asplit=2[voice][key];"
              f"[{mi}:a]aresample=24000,aformat=channel_layouts=mono,volume={vol},afade=t=in:d=2,afade=t=out:st={max(0, total - 3):.2f}:d=3[mus];"
              f"[mus][key]sidechaincompress=threshold=0.03:ratio=5:attack=30:release=600[duck];"
              f"[voice][duck]amix=inputs=2:normalize=0[aout]")
    else:
        fc = ";".join(flt) + ";" + "".join(f"[a{i}]" for i in range(n_in)) + f"amix=inputs={n_in}:normalize=0,apad[aout]"
    subprocess.run([ff, "-y", "-v", "quiet"] + ins + ["-filter_complex", fc, "-map", "[aout]", "-t", f"{total:.2f}", "-ac", "1", full_a], check=True)
    import numpy as _np                                          # CHECK: is the voice clearly louder than the music?
    def _rms(path, t0, t1):
        pcm = subprocess.run([ff, "-v", "quiet", "-ss", f"{t0:.2f}", "-t", f"{t1 - t0:.2f}", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "8000", "-"], capture_output=True).stdout
        a_ = _np.frombuffer(pcm, _np.int16).astype(float) / 32768; return float(_np.sqrt((a_ ** 2).mean())) if len(a_) else 0
    if music_on:
        v_only = _rms(vo, 2, min(story_len, 30)); mixed = _rms(full_a, TI + 2, TI + min(story_len, 30))
        if v_only > 0 and mixed > v_only * 1.8:                  # music much louder than the voice -> FIX: make it again, softer
            say("  [fixed] music was too loud for the voice - mixing again with softer music")
            fc = fc.replace(f"volume={vol}", f"volume={vol / 2:.3f}")
            subprocess.run([ff, "-y", "-v", "quiet"] + ins + ["-filter_complex", fc, "-map", "[aout]", "-t", f"{total:.2f}", "-ac", "1", full_a], check=True)
    look = os.getenv("M2_FILM_LOOK", "none").lower(); hd = os.getenv("M2_1080", "1") == "1"
    chain = []
    if look == "90s":                                             # classic 90s TV cartoon feel: on twos, warm faded colours, grain, flicker, vignette
        say("  film look: 90s classic")
        chain.append("fps=12,fps=" + str(fps) + ",eq=eval=frame:saturation=1.12:contrast=0.93:gamma=1.04:brightness='0.012*sin(17*t)+0.008*sin(5*t)',"
                     "colorbalance=rs=0.06:gs=0.02:bs=-0.07:rm=0.04:bm=-0.05,gblur=sigma=0.7,"
                     "crop=w=iw-8:h=ih-8:x='4+2*sin(9*t)':y='4+2*cos(7*t)',scale=1280:720,noise=alls=10:allf=t+u,vignette=angle=PI/4.5")
    logo_png = os.path.join(HERE, "CORNER_LOGO.png")
    if hd:                                                        # YouTube keeps much more detail from a 1080p upload
        chain.append("scale=1920:1080:flags=lanczos,unsharp=5:5:0.55:5:5:0.0")
        say("  output: 1080p (sharp scaling)" + (" + sharp channel logo" if os.path.exists(logo_png) and os.getenv("M2_LOGO", "1") != "0" else ""))
    vin = ["-i", out_v]; n_in = 1; parts = [f"[0:v]{','.join(chain) if chain else 'null'}[b0]"]; cur = "b0"
    if hd and os.path.exists(logo_png) and os.getenv("M2_LOGO", "1") != "0":
        lw = int(float(os.getenv("M2_LOGO_WIDTH", "180")) * 1.5); op_ = float(os.getenv("M2_LOGO_OPACITY", "0.9"))
        vin += ["-i", logo_png]
        parts.append(f"[{n_in}:v]scale={lw}:-1:flags=lanczos,format=rgba,colorchannelmixer=aa={op_}[lg];[{cur}][lg]overlay=W-w-21:18[b1]"); cur = "b1"; n_in += 1
    badge = os.path.join(HERE, "SUBSCRIBE_BADGE.png")
    if hd and os.path.exists(badge) and os.getenv("M2_SUB_BADGE", "1") == "1":
        t0 = TI + 2.0; t1 = min(TI + float(os.getenv("M2_SUB_BADGE_SECONDS", "60")), total - 6)
        if t1 > t0 + 5:
            say(f"  subscribe button: {t0:.0f}-{t1:.0f} s, bottom right")
            vin += ["-loop", "1", "-t", f"{total:.2f}", "-i", badge]
            parts.append(f"[{n_in}:v]scale=300:-1:flags=lanczos,format=rgba,fade=t=in:st={t0:.2f}:d=0.6:alpha=1,fade=t=out:st={t1 - 0.6:.2f}:d=0.6:alpha=1[sb];"
                         f"[{cur}][sb]overlay=x=W-w-34:y='H-h-150-8*abs(sin(2*PI*t/1.6))':enable='between(t,{t0:.2f},{t1:.2f})':eval=frame[b2]"); cur = "b2"; n_in += 1
    fc_v = ";".join(parts) + f";[{cur}]format=yuv420p[v]"; vmap = "[v]"
    if not chain and n_in == 1: fc_v = None; vmap = "0:v"
    vcodec = ["-c:v", "copy"] if not fc_v else ["-filter_complex", fc_v, "-c:v", "libx264", "-preset", "medium", "-crf", "17"]
    ai = n_in
    subprocess.run([ff, "-y", "-v", "quiet"] + vin + ["-i", full_a] + vcodec + ["-map", vmap, "-map", f"{ai}:a", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", out], check=True)
    os.remove(full_a)
    os.remove(out_v)
    if subtitles: burn_subs(P, st, bt, out, TI, story_len, TO)
    say("[VIDEO 5/5] DOCTOR CHECK ...")
    probs = []
    miss = [i for i in range(1, len(st["pictures"]) + 1) if i not in have]
    if miss: probs.append(f"{len(miss)} pages had no picture (used the picture before): {miss[:20]}{' ...' if len(miss) > 20 else ''}")
    if broken: probs.append(f"broken picture files skipped: {broken}")
    if dark: probs.append(f"{dark} s of black picture")
    if not S.audio_ok(out): probs.append("NO VOICE in the video")
    dur = S.probe(out)[0]
    if abs(dur - total) > 3: probs.append(f"video {dur:.0f} s but planned {total:.0f} s")
    dup = duplicate_pictures(P)
    if dup: probs.append(f"same picture twice at pages {dup}")
    for x in ("voice in the video", "length matches the voice", "no black screens", "every picture opened"):
        ok = not any(k in " ".join(probs) for k in {"voice in the video": ["NO VOICE"], "length matches the voice": ["video "],
                                                    "no black screens": ["black"], "every picture opened": ["broken"]}[x])
        say(f"  {'OK ' if ok else 'XX '} {x}")
    fixable = [p_ for p_ in probs if p_.startswith(("NO VOICE", "video ")) or "black picture" in p_]
    if fixable and not getattr(video, "_again", False):
        say("  [fixing] " + "; ".join(fixable) + " -> making the video once more")
        video._again = True
        try: return video(subtitles)
        finally: video._again = False
    rep = "CORRECTED & COMPLETE" if not probs else "COMPLETE WITH NOTES:\n  - " + "\n  - ".join(probs)
    open(P.p("QC_REPORT.txt"), "w", encoding="utf-8").write(rep)
    say(f"\n  RESULT: {rep}\n  FINAL VIDEO: {out}  ({dur / 60:.1f} min)")
    if os.name == "nt": os.startfile(P.dir)

def burn_subs(P, st, bt, video_path, TI=0.0, story_len=None, TO=0.0):
    """big Hindi title on the first card, the story sentence by sentence, the moral on the last card (ffmpeg/libass)"""
    def ts(t): return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    font = "Nirmala UI" if os.name == "nt" else "Noto Sans Devanagari"
    fontsdir = "C:/Windows/Fonts" if os.name == "nt" else "/usr/share/fonts/truetype/noto"
    L = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1280", "PlayResY: 720", "WrapStyle: 0", "", "[V4+ Styles]",
         "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
         f"Style: Sub,{font},36,&H00FFFFFF,&H00000000,&H96000000,1,3,2,0,2,90,90,34",
         f"Style: Title,{font},78,&H0000E1FF,&H00000000,&H64000000,1,1,6,3,5,80,80,0",
         f"Style: Moral,{font},50,&H00FFFFFF,&H00000000,&HA0000000,1,3,4,0,5,110,110,0",
         f"Style: Hook,{font},50,&H0000E1FF,&H00000000,&HB4000000,1,3,4,0,2,90,90,70", "", "[Events]",
         "Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Text"]
    hk = st.get("hook", "") if os.getenv("M2_HOOK", "1") == "1" else ""
    if TI and hk and TI > 5.5:
        L.append(f"Dialogue: 0,{ts(0.4)},{ts(TI - 3.0)},Hook,0,0,0,{{\\fad(400,300)}}{hk}")
        L.append(f"Dialogue: 0,{ts(TI - 2.8)},{ts(TI - 0.2)},Title,0,0,0,{{\\fad(400,400)}}{st.get('title', '')}")
    elif TI: L.append(f"Dialogue: 0,{ts(0.3)},{ts(TI - 0.2)},Title,0,0,0,{{\\fad(500,400)}}{st.get('title', '')}")
    for bi, b in enumerate(st["beats"]):
        sents = [x for x in re.split(r"(?<=[।!?])\s+", b["narration"].strip()) if x]
        span = bt[bi + 1] - bt[bi]; tot = sum(len(x) for x in sents) or 1; t = bt[bi]
        for x in sents:
            d = span * len(x) / tot; L.append(f"Dialogue: 0,{ts(t + .05)},{ts(t + d - .05)},Sub,0,0,0,{x}"); t += d
    if TO and story_len is not None:
        a = TI + story_len
        L.append(f"Dialogue: 0,{ts(a + 0.3)},{ts(a + TO - 0.2)},Moral,0,0,0,{{\\fad(500,500)}}सीख: {st.get('moral', '')}")
    ass = P.p("subs.ass"); open(ass, "w", encoding="utf-8").write("\n".join(L))
    tmp = video_path.replace(".mp4", "_s.mp4"); esc = lambda p: p.replace("\\", "/").replace(":", "\\:")
    r = subprocess.run([S.ffmpeg(), "-y", "-v", "error", "-i", video_path, "-vf", f"ass='{esc(ass)}':fontsdir='{esc(fontsdir)}':shaping=complex",
                        "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-c:a", "copy", tmp], capture_output=True, text=True)
    if r.returncode != 0:                                        # FIX AT ONCE: try again without the font folder
        say("  [fixed] subtitles failed once - trying again")
        r = subprocess.run([S.ffmpeg(), "-y", "-v", "error", "-i", video_path, "-vf", f"ass='{esc(ass)}':shaping=complex",
                            "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-c:a", "copy", tmp], capture_output=True, text=True)
    if r.returncode == 0: os.replace(tmp, video_path); say("  title, Hindi subtitles and moral written on the video")
    else: say("  (subtitles could not be added: " + (r.stderr or "")[-150:] + ")")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    mins = float(sys.argv[sys.argv.index("--minutes") + 1]) if "--minutes" in sys.argv else 4.0
    if "--from" in sys.argv:
        FROM_FOLDER = sys.argv[sys.argv.index("--from") + 1].strip('"')
        os.makedirs(FROM_FOLDER, exist_ok=True)
    if cmd == "rolls": roll_watcher()
    elif cmd == "newstory": newstory(mins)
    elif cmd == "recover": recover()
    elif cmd == "remake": remake()
    elif cmd == "autopilot": autopilot(mins)
    elif cmd == "auto": auto(mins)
    elif cmd == "story": story(mins)
    elif cmd == "pick": picker()
    elif cmd == "pictures": chapters_helper() if os.getenv("M2_ONE_BY_ONE") != "1" else pictures_helper()
    elif cmd == "import": import_pictures(sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None)
    elif cmd == "video":
        P0 = latest(); st0 = P0.load("story.json") or {"pictures": []}; need0 = len(st0["pictures"])
        have0 = len(glob.glob(P0.p(pics_dir(P0), "*.png")))
        if need0 and have0 < need0 * 0.9:                       # pictures missing in the story folder -> take them again from my_pics
            FROM_FOLDER = FROM_FOLDER or os.path.join(HERE, "my_pics")
            say(f"Only {have0} of {need0} pictures in the story folder - taking them again from {FROM_FOLDER} ...")
            remake()
        else:
            video("--no-subtitles" not in sys.argv)
    else: print(__doc__)
