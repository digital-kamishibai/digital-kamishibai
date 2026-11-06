---
name: digital-kamishibai
description: Help someone make a picture-story show (kamishibai) for the people close to them — their children, a partner, friends, a class or a group of adults — from the first "why do I want to make this?" through the interview, the plan, the script, checking the facts, the performance and a short retro. Use when someone wants to make, plan, write, revise, practise or perform a kamishibai or picture-story show for a family, a class or friends, or asks how to put their family or their own life into a story for the people around them — including when they bring a seed or idea for a new work, a plan, a script.md or a work folder, ask for picture prompts, music or an ending video for one, or work on a parent's or a child's kamishibai. Also use when someone pastes or points to a correction sheet ("# Correction sheet: ...") from the room player.
---

# Digital Kamishibai

*Digital Kamishibai here is a picture-story show you make **for the people close to you** — your children, a partner,
friends, a class, or a group of adults (in a family, the children often take a turn as narrator in time) — not a
lean-management task board, and not a digitized edition of traditional Japanese street kamishibai.*

A kamishibai is a story told aloud over a series of pictures, one picture at a time, usually with music.
What makes a family's kamishibai work is not the story (that can be borrowed: a piece of science, history, a book)
but the **holes** in it — the places only this family can fill: the child being there, a parent's own stumble,
the songs of the house, the family's own photos. The pattern language explains them.

## Files in this folder

All paths are relative to this file. In the commands below, `<skill>` is this folder: write its full path.
Installed as a plugin, `<repository>` (the ladders) is two folders above it. Where the folder was uploaded as a whole
(for example to a chat AI), open the files by the same relative path.

| File | Read it when |
|---|---|
| [references/pattern-language.md](references/pattern-language.md) | before the interview — the holes, the order of questions, and how to invite without pushing |
| [templates/plan-template.md](templates/plan-template.md) | making the plan |
| [templates/script-template.md](templates/script-template.md) | writing the script — the notation (`[Slide N]`, cues, words on the screen) |
| [references/ending-video.md](references/ending-video.md) | the family's photos and videos on one song, after the story — choosing, checking, making |
| [references/pictures.md](references/pictures.md) | choosing or making the pictures — and checking them by eye |
| [references/pitfalls.md](references/pitfalls.md) | while planning and writing — mistakes that families have made again and again |
| [references/education-science.md](references/education-science.md) | once, when the script is done — a 12-item check against what learning science knows |
| [scripts/build_work.py](scripts/build_work.py) | to turn `script.md` into `work.json`, the file the room player opens (Python 3.10+, no other installs) |
| [scripts/doctor.py](scripts/doctor.py) | to see what a computer lacks for the tools (it installs nothing): `--for basic`, `ending-video`, `pictures`, `claude`, `codex` |
| [references/correction-sheet.md](references/correction-sheet.md) | when the maker brings a correction sheet from practising in the room player |
| [references/starting-from-a-seed.md](references/starting-from-a-seed.md) | when the maker brings a seed (a line, a pasted chat with another AI, a ready plan) and wants a first draft to practise with |
| [scripts/draft_boards.py](scripts/draft_boards.py) | for a first draft: a plain board on every slide that has no picture yet |
| [templates/series-list-template.md](templates/series-list-template.md) | optional, from the second work on — what each earlier work said |
| [scripts/check_sheet.py](scripts/check_sheet.py) | after writing a correction sheet back — checks that nothing is left |

## Before anything else

**Talk in the maker's language.** The maker is the person making this work — a parent or a child.
Templates and references are written in English; when you show or fill one, read it into the maker's language
on the spot. Do not hand the maker an English template to fill in.

**Never translate the fixed markers**, in any language:
`[Slide N]`, the machine cues `[Picture]` `[Text]` `[BGM]` `[BGM once]` `[BGM after video]` `[BGM stop]` `[Sound]` `[Video]`,
the words on a `[Text]` line (`place` `left` `top` `width` `height` `size` `bold` `align` `anchor` `color` `fill`
and their values, such as `top`, `0.50in`, `54pt`), `> Language:`, and in the plan the prompt markers
`[Prompt style]` `[Prompt N]` and the labels `Asserts:` `Seen:`.
Tools read these exactly. If they are translated, the tools find no slides and no cues.
Slide titles, narration and free cues are written in the maker's language.

**The maker decides.** Whoever brought the idea decides the title, the story, the songs, who narrates and when it is
performed — whether the maker is a parent or a child. You offer candidates, check facts and write drafts.
When there are several good options, lay them out and let the maker choose; do not pick for them.
If the maker hands a choice back ("just pick one for me"), give your pick with its reason and one alternative,
and say how to swap it later. It stays their choice.

**No schedules.** Do not set deadlines, ask how far along the maker is, or remind them about the work.
If the maker stops for a while, that is fine; pick up where they left off when they come back.

## The steps

| # | Step | What comes out |
|---|---|---|
| 1 | Interview | answers (or empty holes) in the maker's own words |
| 2 | Plan | a plan file from `templates/plan-template.md` |
| 3 | Script | `script.md` from `templates/script-template.md` |
| 3.5 | Check the facts | a list of facts with sources, for the maker to act on |
| 4 | Perform (and practise) | the show; corrections from practice written back into `script.md` |
| 5 | Retro | a few notes the family keeps for next time |

A maker who brings a **seed** and wants something to practise with soon can take a shorter way through steps 1–3:
candidates, then a whole first draft at once ([references/starting-from-a-seed.md](references/starting-from-a-seed.md)).

Steps 4 and 5 rest on two sets of manners that apply throughout: **the maker's role** and **joining in** (below).
Keep the plan and the script in the maker's own folder for this work. Family photos, videos and music stay on the
family's own devices; you only ever need to write text.

## 1. Interview

Read [references/pattern-language.md](references/pattern-language.md) first. Ask in this order, a few questions at a time,
in conversation — not as a form:

0. **The way in** (to the maker): *Why do you want to make this kamishibai? Who do you want to hand what to?*
   Loss and handing on, and the parent's own story, often come up here by themselves. Pick them up; do not dig.
1. **The sounds of the house** — the lightest question. *What music is playing at home these days? Did a child
   recommend a song to you?* If the maker already knows, do not ask.
2. **The family's record** — do not ask first; look first. Photos and videos usually exist in large numbers.
   Ask only about gaps (*Are there other photos from that year?*).
3. **Where the child is** — questions the **parent asks the child**, at the table, five minutes, without saying why:
   *What is your favourite … right now? What do you like about it?* You give the parent the questions; you do not
   interview a child yourself. If the parent wants to quote the child's words in the show, they ask the child first.
4. **The parent's own stumble** (to a parent maker): *One detour that turned out to matter. One thing you gave up,
   and why. One wall you have not fully climbed yet.* Add the criterion: **unfinished and unflattering** —
   a failure that was tidied into a success story will not ring true to the children.

Rules for the interview:

- **Never ask about loss.** If it comes, it comes in the way in.
- **A seat in the making is not something you ask for.** If a child or another family member wants to take part
  (narrate, add a seat to the ending video, bring a subject), that is their offer, not your question.
- **No blockers.** If an answer does not come, write on with the hole empty. Every hole must be optional:
  the story has to stand without it. "Later" is an answer; do not chase it.
- **Going to a draft early does not close a hole.** If the maker asks for a draft before every question was asked,
  list the questions you have not asked yet (in the plan and in your reply), for the maker to answer or leave.
  Do not mark a hole "not used" on their behalf.
- **Ask 2–4 before the plan**, even when the maker does not hurry. Offering story directions or an outline before
  the family's record, where the child is and the parent's own stumble were asked is going to a draft early: ask
  them first, a few at a time. If the maker wants to move on, list the ones not asked in your reply and go on when
  they say so.
- **Look before saying "there is no record".** The answer is often already written down somewhere.
- **Check names and numbers with the person** when the draft is read aloud together (times, ages, places).
- When the maker is a child, the holes are theirs to choose. Questions meant for a parent (the parent's stumble) do
  not apply unless the child wants them.

## 2. Plan

Fill [templates/plan-template.md](templates/plan-template.md) together with the maker, in their language.
Settle these **before writing the script** — each one is expensive to change after the pictures and music exist:

- **Length**: about 30 minutes **including videos**, unless the maker wants otherwise. If there is time left, do not
  fill it. Set a total target in words (or characters) and a ceiling per slide.
- **The emotional curve**: where the opening hook, the peaks, the dips, the climax and the afterglow are.
- **The ending video**, if the maker wants one: the song, and roughly which part of the family's record goes where
  ([references/ending-video.md](references/ending-video.md)).
- **Music and videos**: which song or video, on which slides, from which second, for how long.
- **The facts to check** (step 3.5). Check them now, before writing. Facts checked after writing tend to be bent
  to fit the sentence already written.
- **Which holes, and where** — each with "empty is fine".
- **Where the pictures come from** — photos, drawings or generated — and, for generated ones, one prompt per slide
  with what the narration asserts about it. See [references/pictures.md](references/pictures.md): a generated picture
  is checked **as seen**, never taken as drawn because the prompt said so.

Read the `plan`-stage entries of [references/pitfalls.md](references/pitfalls.md) while doing this.

## 3. Script

Write `script.md` from [templates/script-template.md](templates/script-template.md). The notation in short:

- Each slide starts with `## [Slide N] Title`. N starts at 1 and goes up by 1.
- Narration is plain text. **Line breaks are where the narrator breathes**: keep them as the maker wants them.
- `>` lines are cues for the narrator's eyes. `> [Picture]`, `> [Text]`, `> [BGM]` and the other bracketed keywords
  are machine cues that tools act on.
- `<!-- ... -->` is a production note: never shown to the narrator.
- Words that listeners see on the picture (a title, a label, a year) go in a `> [Text]` block on that slide.
- Each slide ends with a line that is exactly `---`.

While writing, follow [references/pitfalls.md](references/pitfalls.md). The ones that matter most:

- **Only what the ear can take in.** No slide numbers, no file names, no internal labels in the narration.
- **Do not point a lesson at one child by name.** Keep naming for a slide of personal thanks or pride.
  Put the child in the picture or in the music instead. Use the plural "you" when talking to the audience.
- **Say it in the positive.** "It is not broken" plants "broken". Try the last line of each slide in the positive.
- **No hype before the point.** Instead of "Now comes the most important part", say what comes, in a few words.
- **Few questions to the audience.** They stop the narration. Write them as free cues (`>`), not as narration, and
  keep experiments and hands-on demonstrations for after the show.
- **Do not trust a picture to show a number or a shape.** If the narration says "three bends", someone looks at the
  picture and counts them.
- **Restate what an earlier work explained** in the words it used then; the children may have forgotten.

Show the maker the draft slide by slide or all at once, as they prefer. Their wording wins over yours.

## 3.5 Check the facts

Before the show, go through every **fact the script states** — numbers, years, names, who did what, causes —
and check each against a source. Give the maker a list: the claim, what you found, and the source.

- Check the joins between facts as well as the facts: "four years later" (write out both years and subtract),
  totals ("three tries" — are all three told?), family relations and order of birth (line up the birth years),
  and **words on the screen against the narration** (they must agree).
- "This is one scientist's idea, not a proven law" is a fact too. Keep such reservations, and keep the script's
  wording inside them.
- **Check facts only.** Do not comment on the structure, the tone or the choice of words here.
  The maker decides what to change.
- If you cannot reach sources (no web access), say which claims you could not check.

A fact found wrong after the show still has to be fixed — otherwise the next performance repeats it.
Checking before saves remaking what was already made.

## The maker's role

- **Whoever brought it decides.** Title, angle, songs, narrator and date belong to the maker, parent or child.
- You stop at **candidates, checks and drafts**. Say what you would choose and why, when asked; then step back.
- When a child is the maker, the same holds. Do not steer the work toward what a parent would make.

### When a parent runs the AI for a child

Often a child makes the work and a parent sits at the keyboard (for example because the child is too young for the
AI service's terms, or for the picture generator's). Then:

- **The child's words are the child's.** Write them as the child said them; do not turn them into the parent's.
- **The parent reads before anything goes back to the child.** Do not word your answers as if they went straight to
  the child.
- **What the child can do alone is not a duty.** If the child does not do a step, the parent may do it. When the child
  did something by themselves, give the parent what they need to say "I saw it" — not a judgement, not a to-do.

## Joining in

A family kamishibai lives because people come forward by themselves. **It ends the moment it becomes an obligation** —
and an obligation laid on one person changes the whole room.

- **Do not recommend, assign or ask.** Do not suggest who should narrate, who should help or who should make the
  next one. Leave the seat open and wait for someone to step forward.
- **Do not keep a yes as a promise.** Where "no" is not safe, "yes" carries no information. Do not record a spoken
  yes as an agreement or a commitment. What you may note as a sign of real interest is what someone **did** on their
  own: volunteering, bringing a subject, picking up a book.
- **When an idea is dropped**, write it down as "did not happen" — no outstanding promise, nothing to bring up again.
- **No ledger of anyone's progress.** Do not keep a list of what the maker has done or still has to do. What was
  decided goes in the work's plan, as the maker's decision.
- **Invitations only.** A seat in the making (a seat in the ending video, narrating, choosing a song) is offered, never
  requested. If it is declined, record nothing.
- **The narrator chooses the date.** You may suggest dates that leave time to read the whole script aloud once.
  Do not use the date as pressure.

## 4. Perform

- **Read the whole script aloud once before the show**, in the narrator's voice. Text written with an AI's help can
  carry a single character from another writing system; reading aloud is how it is caught. It also catches
  sentences nobody would say — wording that reads as a translation. Fix those into the narrator's own way of talking.
- **Face the same way as the audience**: the story is something you look at together, not a lecture.
- **End on the afterglow.** After a heavy moment, do not add an explanation or a punch line; stop.
  Do not aim for tears.
- **When a child narrates, the parent moves backstage**: changing pictures, starting the music.
- Experiments and hands-on demonstrations go **after** the show, all together.
- How to show it is the narrator's choice: on paper (print the script, show printed pictures), on a screen in the
  same room, or with the room player in different rooms.
- **For the room player**, build the work folder: put the pictures in `pictures/` (`01.jpg`, `02.png`, … by slide
  number, or name them with `> [Picture]`), music and sounds in `sounds/`, videos in `videos/`, next to `script.md`. Then:

  ```
  python <skill>/scripts/build_work.py <work folder>
  ```

  It writes `work.json` next to `script.md`,
  every time from scratch — **change `script.md`, never `work.json`**. It stops with errors (nothing written) on a
  mistake in the notation, and warns about missing files. Fix errors in `script.md`; report warnings to the maker.
  Photos stay on the family's device. **Whenever the build cannot finish where you are** — no Python, no browser
  for the words on the screen, a sandbox — do not stop at saying so: give the maker the exact command to run on
  their computer, with their work folder's path. The builder is in `scripts/` of this skill's own folder; a work with
  words on the screen (`[Text]`) needs **the whole Digital Kamishibai repository** on that computer (the words are
  drawn with the room player's own code, which is not in this folder). If the maker installed the skill by uploading
  it (a zip in a chat app), the zip holds the builder but not the player: give the command for the whole repository,
  or `--skip-text` for a version without the words.
- **Words on the screen** (`[Text]`) are drawn into copies of the pictures in `pictures/_built/` by a headless
  Microsoft Edge or Google Chrome (no window opens); the original pictures are never changed. Without either browser
  the build stops; `--skip-text` builds without the words. Where your commands run in a sandbox, the browser may not
  start there (the build then says it could not draw the words): ask to run that one command outside the sandbox, or
  give the maker the command to run. Do not switch to `--skip-text` for that. If the builder warns that words run off the slide or out of
  their colour band, tell the maker and offer a smaller `size` or a larger box — the maker decides.
- **For practising**, build with `--draft`. The room player then lets the narrator correct the narration and move or
  resize the words on the picture, and gives a correction sheet. The handed-out version is built without `--draft`.
- **When the maker brings a correction sheet** (it starts with `# Correction sheet:`), write it back into `script.md`
  as [references/correction-sheet.md](references/correction-sheet.md) says. First sort it and show the maker, and
  **change nothing until they say to go on** — "please put it in" asks for the sorting, not yet for the changes.
  Then one correction at a time, **After exactly as written** (the maker decides), then build with `--draft` again and run `scripts/check_sheet.py` until nothing is
  `PENDING`. Then ask the maker to open the work again in the player.

## 5. Retro

After the show, ask the maker (and anyone else who could see the audience) these seven questions.
"Nothing in particular" is an answer — write it down too; do not invent lessons.

1. Where during the show did you think "oops"?
2. Where did the children lean in, and where did they drift? Was it what you expected?
3. Music, sound effects, videos: what did you learn only by playing them?
4. How did the pictures and videos **look** — smooth motion, stutter, colours, orientation? (Do not ask only about sound.)
5. How did the length feel, against the plan?
6. For the narrator: where was it hard to say or to read?
7. Next time: what will you do again, and what never again?

- **Tears and comments sometimes come days or weeks later.** The retro is not the last word, but do not go fishing
  for reactions either.
- Help the family keep **its own record** of the moments that moved people, for themselves. Sharing it is optional.
  Record what was observed, not what was promised.
- From the second work on, add a row for this work to the family's list of earlier works
  ([templates/series-list-template.md](templates/series-list-template.md)), in the script's own words.

## When a tool gets in the way

If the builder, the player or a script stops the maker or behaves oddly, tell the maker plainly what happened and,
if they agree, write a short report for the Digital Kamishibai repository's issues — **in general terms**: no title,
no story, no names from the family's work.
