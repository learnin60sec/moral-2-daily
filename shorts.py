"""SHORTS: a vertical teaser (about 45-50 s) cut from the finished video.
It starts at the strangest moment (the hook part), ends at a cliffhanger BEFORE the reveal (never in the last two parts), and has big English words on top
and "WATCH THE FULL STORY" below. Uploaded 30 minutes after the main video, with its link in the description."""
import os, sys, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import studio as S


def pick_window(bt, hook_part, limit=50.0, minimum=18.0):
    """bt = start times of the story parts (+ the end); returns (start, end) in video seconds: whole parts, the cliffhanger at the end of the last one"""
    n = len(bt) - 1
    def best(sb):
        s, e = bt[sb], None
        for j in range(sb + 1, n + 1):
            if j > max(1, n - 2): break                                # the last two parts hold the reveal: never in the teaser
            if bt[j] - s > limit: break
            e = bt[j]
        return (s, e) if e and e - s >= minimum else None
    for sb in (hook_part, max(0, hook_part - 1), 0):
        w = best(min(sb, max(0, n - 3)))
        if w: return w
    s = bt[0]; return s, min(s + 40.0, bt[max(1, n - 2)])


def _font(size):
    from PIL import ImageFont
    for fp in (os.path.join(HERE, "ThumbFont.ttf"), "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(fp):
            try:
                f = ImageFont.truetype(fp, size)
                try: f.set_variation_by_axes([800])
                except Exception: pass
                return f
            except Exception: continue
    return ImageFont.load_default()


def _overlays(P, words, kind):
    """two transparent PNGs: the top banner (big words) and the bottom call to action"""
    from PIL import Image, ImageDraw
    words = (words or "WATCH THIS").upper().split(); best = None
    for split in (range(1, len(words) + 1) if len(words) > 1 else [1]):
        lines = [" ".join(words[:split]), " ".join(words[split:])] if len(words) > 1 and split < len(words) else [" ".join(words)]
        d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        for sz in range(190, 60, -6):
            f = _font(sz)
            if max(d.textlength(l, font=f) for l in lines) <= 940 and len(lines) * sz * 1.05 <= 330: break
        if best is None or sz > best[0]: best = (sz, lines)
    sz, lines = best; top = Image.new("RGBA", (1080, 430), (0, 0, 0, 0)); d = ImageDraw.Draw(top)
    tag = "MYSTERY STORY" if "Mystery" in kind else "MORAL STORY"; ft = _font(42); tw = d.textlength(tag, font=ft)
    d.rounded_rectangle(((1080 - tw - 40) / 2, 0, (1080 + tw + 40) / 2, 66), radius=14, fill=(222, 30, 36), outline=(255, 255, 255), width=3); d.text(((1080 - tw) / 2, 4), tag, font=ft, fill=(255, 255, 255))
    f = _font(sz); y = 86
    for k, l in enumerate(lines):
        w = d.textlength(l, font=f); x = (1080 - w) / 2; col = (255, 255, 255) if k % 2 == 0 else (255, 224, 40)
        d.text((x + 5, y + 7), l, font=f, fill=(0, 0, 0), stroke_width=max(7, sz // 10), stroke_fill=(0, 0, 0))
        d.text((x, y), l, font=f, fill=col, stroke_width=max(7, sz // 10), stroke_fill=(0, 0, 0)); y += int(sz * 1.05)
    bot = Image.new("RGBA", (1080, 250), (0, 0, 0, 0)); d = ImageDraw.Draw(bot)
    f1 = _font(66); t1 = "WATCH THE FULL STORY"; w1 = d.textlength(t1, font=f1)
    d.rounded_rectangle(((1080 - w1 - 70) / 2, 10, (1080 + w1 + 70) / 2, 120), radius=30, fill=(222, 30, 36), outline=(255, 255, 255), width=5); d.text(((1080 - w1) / 2, 14), t1, font=f1, fill=(255, 255, 255))
    t2 = "The Moral Story Club  -  a new story every day at 6 PM IST"
    for sz2 in range(44, 24, -2):                                      # the line must fit inside the picture
        f2 = _font(sz2); w2 = d.textlength(t2, font=f2)
        if w2 <= 1000: break
    d.text(((1080 - w2) / 2 + 3, 148), t2, font=f2, fill=(0, 0, 0), stroke_width=6, stroke_fill=(0, 0, 0)); d.text(((1080 - w2) / 2, 145), t2, font=f2, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    a, b = P.p("short_top.png"), P.p("short_bottom.png"); top.save(a); bot.save(b); return a, b


def make_short(P, st, meta, seconds=None):
    """SHORT.mp4 (1080x1920): the video in the middle over a blurred copy of itself, words above, call to action below"""
    seconds = float(seconds or os.getenv("M2_SHORT_SECONDS", "50"))
    video = P.p("FINAL.mp4")
    if not os.path.exists(video): raise RuntimeError("FINAL.mp4 not found")
    total = S.probe(video)[0]
    try:
        tl = P.load("timeline.json"); s, e = pick_window(tl["beat_times"], int(tl.get("hook_part", st.get("hook_part", 0))), seconds)
    except Exception:
        s, e = 8.0, min(total - 6, 8.0 + 40.0)                         # no timeline (an older video): the first part of the story
    e = min(e, total - 1.0); dur = e - s
    if dur < 10: raise RuntimeError(f"the video is too short for a Short ({dur:.0f} s)")
    top, bot = _overlays(P, (meta or {}).get("thumb"), (meta or {}).get("kind", "Hindi Mystery Story"))
    out = P.p("SHORT.mp4")
    fc = ("[0:v]split=2[a][b];[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=5:2,eq=brightness=-0.10:saturation=1.1,scale=1080:1920:flags=bilinear[bg];"
          "[b]scale=1080:-2:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2-40[v0];[v0][1:v]overlay=0:185[v1];"
          f"[v1][2:v]overlay=0:1390,fade=t=out:st={dur - 0.6:.2f}:d=0.6,format=yuv420p[v]")
    r = subprocess.run([S.ffmpeg(), "-y", "-v", "error", "-ss", f"{s:.2f}", "-t", f"{dur:.2f}", "-i", video, "-loop", "1", "-t", f"{dur:.2f}", "-i", top, "-loop", "1", "-t", f"{dur:.2f}", "-i", bot,
                        "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-af", f"afade=t=in:d=0.2,afade=t=out:st={dur - 0.7:.2f}:d=0.7", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-shortest", out], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 100000: raise RuntimeError("ffmpeg could not make the Short: " + r.stderr[-200:])
    return out
