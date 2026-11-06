# The ending video

The family's record — photos and videos from the beginning until now, pets included — on **one song**, played after the
story. Of everything a family kamishibai can hold, this is the part that has reached every listener, adults included.

It is optional, like every hole. Offer it; do not push it.

## Choosing

- **The form**: the family's record × one song. After the story, not inside it.
- **The song**: one the family already lives with — a song someone the show is for recommended, one that plays at home. The maker
  chooses. Songs with lyrics are fine here: nobody is narrating.
- **The seats**: think of the song as a row of seats (a few seconds each) and the photos as who sits where. A quiet
  intro wants one picture held long; a chorus can carry many quick ones. Line the biggest moment of the song up with
  the picture that matters most.
- **The same material works again** in another work with another song. Do not think "we already used those".
- **Leave room for a listener to add a seat** (their own photo, their own clip) — only if they want to. Do not ask.
- **Whose photos**: the parent decides which photos of the children are used; a child decides about their own.
  Photos and clips of anyone outside the family (a class, a group of friends) are used only after asking each person
  first — for a child, their parent or guardian.

## Checking the material

- **Look at every photo at full size, corners included.** A picture taken for another use can carry its old title,
  a caption or a watermark in a corner.
- **Check the orientation of portrait videos by eye.** A phone sometimes records the wrong rotation, and the video
  plays lying on its side.
- **Look at the motion, not only the sound.** A slow zoom made by moving the frame in whole pixels stutters (still,
  still, jump). If the video is made with an app, play it full screen once before the show; if it stutters, use less
  zoom or none.

## Making it

Either way works; the maker chooses.

| Way | Cost | Needs |
|---|---|---|
| A phone's photo app, or a free video editor | free | the app; the family's photos on that device |
| **The ending-video ladder** (`ladder/ending-video/` in the Digital Kamishibai repository) | free | Python 3.10+, Pillow and ffmpeg on a computer |

**Export at 720p or 1080p**, as an MP4. The room player sends the video to every listener's device before the show:
a large file takes long to send and can crash a phone. The room player takes at most 300 MB per video.

Put the video in the work's `videos/` folder and play it from the last slide with `> [Video] videos/<file>.mp4`
(see `templates/script-template.md`).

## The ladder

Installed as a plugin, the ladder is in `<repository>`, two folders above this skill's folder;
elsewhere the maker runs it on their own computer. Its README has the details. The way of working:

1. **Seats first.** `--init` cuts the song into equal seats and puts photos from a folder into them, by date taken.
   All are placeholders. Adjust seat lengths to the song only if the maker wants (that changes the timing; after the
   photos are chosen, the seats should stay as they are).
2. **The storyboard.** `--storyboard` makes `ending/storyboard.html`: every seat as a card, by part of the song. The
   maker points at the seats to change. Show the maker this page — it holds the family's photos, so it stays on their
   computer. When the maker pointed at seats while practising in the room player (`ending seat N` in a correction
   sheet), add `--mark N,M`: the page opens with those seats already pointed at.
3. **Changes are made seat by seat**: `--replace N=FILE` (a video with `@second`), `--move N=M`, `--sort RANGE`
   (by date), `--pin-set N="why"` for a seat that must not move (a lyric). None of these moves a seat in time.
4. **After every change, `--storyboard` again** before the next round of pointing; `--check` says when it is old.
   The maker points at the new page, not the old one.
5. **Build**, then `check_smoothness.py` (the stutter check), then watch it with the maker. `--confirm RANGE` records
   what the maker has decided.

Rules while helping:

- The maker chooses every picture and the song. You can suggest a seat for a picture they mention, explain what a
  command will do, and run it.
- Do not open, list or describe the family's photos unless the maker asks you to look at a particular one.
- Never move seats in time once the maker has started choosing, unless they ask: everything already chosen would slip.
- Keep the song file: the seats are timed to that exact file (`audio_sha256`). Another download of the same song is
  usually a little different in length.
