=====================================================================
  MORAL 2 - AUTOPILOT  (you only make the pictures)
=====================================================================
ONE-TIME SETUP
  1. pip install requests pillow numpy edge-tts imageio-ffmpeg google-auth-oauthlib google-api-python-client
  2. YouTube: put client_secret.json in this folder (same file as the 60-second channel)
     -> YOUTUBE_LOGIN.bat -> browser -> choose the MORAL channel -> Allow
  3. SETUP_AUTOSTART.bat  -> the autopilot starts by itself every time you log in to Windows
     (or start it yourself: START_AUTOPILOT.bat - keep that window open, minimise it)

EVERY DAY
  YOU:   open the newest folder in projects -> PROMPTS_CHAPTERS.txt -> make the pictures in Gemini
         (MASTER once, then each chapter) -> download -> put them ALL in  my_pics   (png or zip)
  ITSELF (checks my_pics every 2 minutes):
         all pictures there (or 80%+ and nothing new for 45 min) -> order -> AI check -> video with
         title card, flip-book movement, Hindi subtitles, music, moral card -> DOCTOR check ->
         if CORRECTED & COMPLETE: YouTube upload (scheduled, marked AI-made, thumbnail) ->
         the next story is prepared at once (old pictures go to my_pics\old_<date>)
  LOG:   autopilot_log.txt shows everything it did

SETTINGS (setx NAME value, then a new window)
  STUDIO_UPLOAD    schedule (default) | public | private      STUDIO_TIMES "10:00"  (IST, scheduled time)
  STUDIO_AUDIENCE  family (default) | kids                     M2_AUTO_UPLOAD 0  (make videos, no upload)
  M2_WAIT_MINUTES  45   (wait for missing pictures)            M2_MUSIC_VOLUME 0.18   M2_FLIP_SECONDS 1.2
MANUAL (still there): ONE_CLICK.bat, python m2.py video, folder extra\
=====================================================================
=====================================================================
  MORAL 2 - HOW IT WORKS   (only ONE button: ONE_CLICK.bat)
=====================================================================

WHAT YOU DO                              WHAT HAPPENS BY ITSELF
---------------------------------------  -------------------------------------------------
1. Double-click ONE_CLICK.bat            STEP A: best story (YouTube views) is chosen and
                                         written, picture prompts made (PROMPTS_CHAPTERS.txt),
                                         the WHOLE story is spoken in ONE voice take
                                         (FULL_VOICE.mp3 - no breaks). Folder opens.

2. Gemini: paste MASTER once, then       -
   every CHAPTER. Download the pictures
   in page order (png or zip, any way).
   Put them ALL in the folder  my_pics

3. Double-click ONE_CLICK.bat again      STEP B: pictures taken from my_pics (zips opened),
                                         ordered (download time, then number in the name),
                                         exact repeats removed, saved as 001.png 002.png ...
                                         MISSING pages? It STOPS, shows which pages and what
                                         they should show. Add them to my_pics -> ENTER ->
                                         it checks the folder AGAIN (or V = video now).
                                         STEP C: AI check of the pictures (max 90 s).
                                         STEP D: VIDEO
                                           1/5 voice + pictures read, broken files found
                                           2/5 every picture timed to its spoken words
                                           2/5 TITLE CARD (main character + big title, spoken
                                               "aaj ki kahani hai ...") and MORAL CARD (moral written,
                                               spoken happy / sad / serious like the moral)
                                           3/5 drawn: flip-book movement (~1.2 s per picture, every
                                               picture slowly melts into the next, ONE smooth camera
                                               path for the whole film - no jumps),
                                               progress every 15 s, black frames counted
                                           4/5 voice + Hindi subtitles added
                                           5/5 DOCTOR: OK/XX for voice, length, black, files
                                         -> FINAL.mp4 + QC_REPORT.txt, folder opens

4. Watch FINAL.mp4 and upload.           Next ONE_CLICK.bat starts a NEW story (old pictures
                                         in my_pics are moved to my_pics\old_<date>).

FILES OF A STORY:  projects\<date>\
  PROMPTS_CHAPTERS.txt  FULL_STORY.txt  FULL_VOICE.mp3  pictures\  CHECK_ORDER.jpg  FINAL.mp4  QC_REPORT.txt

SETTINGS (optional, setx NAME value, new cmd window):
  M2_FLIP_SECONDS 1.0      seconds per picture in the flip-book movement (0.7 = faster, 1.5 = calmer)
  M2_AI_CHECK 0            switch the AI picture check off
  STUDIO_VOICE gemini      Gemini's acted voice (one take) instead of Microsoft
EXTRA buttons (only if needed): folder  extra\
=====================================================================

REMAKE THE VIDEO OF THE LAST STORY (same pictures, new smooth version):
   cmd:  cd C:\moral_2   then   python m2.py video

BACKGROUND MUSIC: soft music under the voice, it gets quieter while the narrator speaks.
   default: made by the script for the story's mood (happy / sad / serious) - no copyright problems
   your own: put mp3 files in the folder  music  (e.g. YouTube Audio Library; names with happy / sad / calm pick the mood)
   louder / softer:  setx M2_MUSIC_VOLUME 0.25   (default 0.18)      no music:  setx M2_MUSIC 0

VIDEO STYLE (default "story"): every picture is shown ONCE, in story order, while its words are spoken (about 2-4 s),
   slowly melting into the next one, with one calm camera move. Old fast flip-book:  setx M2_STYLE flip
PAGE NUMBERS IN FILE NAMES: pic_007.png (or page_7.png) always goes to page 7 - a missing page never shifts the others.
FLOW BOT (your SECOND Google account only):  FLOW_BOT_SETUP.bat once (show it the prompt box + download button),
   then FLOW_BOT_RUN.bat: it pastes every page's prompt, downloads, saves my_pics\pic_001.png ... in order.
   STOP: move the mouse into a corner of the screen. Do not use the PC while it runs.
REMAKE THE LAST STORY'S VIDEO:  python m2.py video        UNDO an accidental new story:  RECOVER.bat

PICTURES IN ANY ORDER: the AI (Groq, Gemini backup) looks at every picture and puts it on the page it shows (result cached).
MISSING PAGES: their FULL prompts open in Notepad (MISSING_PROMPTS.txt). Make them, put them in my_pics, press ENTER -> it continues.

ROLL WATCHER (easiest way to make the pictures yourself):
   Every prompt starts with  ROLL 007.  (a chapter with  ROLLS 005-008.)
   1. ROLL_WATCHER.bat  -> keep its window open
   2. Copy ANY prompt (any order) -> Gemini -> download -> it is saved as my_pics\pic_007.png by itself
      (a chapter: the next 4 downloads become 005, 006, 007, 008)
   3. RULE: copy -> make -> DOWNLOAD, and only then copy the next prompt
   4. Ctrl+C in its window shows which rolls are still missing.   Then ONE_CLICK.bat (rolls = exact pages).

HOW MANY PICTURES: decided by the REAL story. The story is written, the voice is made, every part is measured; each part gets
   (its seconds / 3) pictures (short part = 1, long part = 5 ...). The window shows e.g.  VIDEO 3.4 min -> 68 PICTURES -> 17 CHAPTERS.
   Fewer pictures:  setx M2_SECONDS_PER_PICTURE 4

VOICE-SYNCED PICTURES: a picture appears exactly when the narrator starts its words (at a , । ! ? pause - never in the middle of
   a sentence), stays at least 3.5 s, and melts into the next one in 2 s. The camera breathes very slowly.
   Calmer / livelier:  setx M2_MIN_SECONDS 4.5   or   3      New stories: one picture per ~4 s (M2_SECONDS_PER_PICTURE)

LIVING DETAILS: from each part's place the video adds gentle life: flying birds + falling leaves (outside), a slowly breathing
   warm sun glow (sunrise/sunset), fireflies (night), rain, smoke (kitchen/fire).
   Stronger / softer:  setx M2_ATMOSPHERE_STRENGTH 1.5   or   0.6        Off:  setx M2_ATMOSPHERE 0
