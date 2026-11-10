# A guide to the holes — Six Friends Smoothie

Someone who makes a smoothie every morning made this picture-story show for their family and performed it for them the same day.
It doesn't have to be for children: you can make one just as well for a partner, friends, a class, or a group of adults.
For this public version we marked **the places you can replace with your own (the holes)**.
The holes are not blank. What the maker put there is still in place — that is the "filled-in example".
On the narrator's screen, the narration that is a hole shows with a **pale yellow background** (in the script, the lines
that start with `~ `).

Changing just the holes is enough to make it your own. The frame of the story (each ingredient has a special skill, and together they help each
other) works for any favourite dish.

| Hole | Where | What you can change |
|---|---|---|
| 1 | Slide 1 (and the ends of slides 4 and 5) | The narrator, and why they started |
| 2 | Slides 2 to 5 | Your own recipe |
| 3 | All five slides | The music |
| 4 | After slide 5 | The ending video |
| 5 | Slide 2 | The question |
| 6 | All five slides | The pictures |

---

## Hole 1: The narrator, and why they started (slide 1)

**Where**: all of slide 1, from "Every morning, Mom makes a smoothie." to "Today's story is about…".
The narrator comes up again at the end of slide 4 and in the last line of slide 5: if you change the narrator, change those too.

**What**: the narrator, and why they started making the dish.

**Why**: to the people who eat it every day, the food is just "there". When the person who makes it explains why, it becomes
**something someone chose and kept doing**. This slide is the "story about a person" that comes before the science.

**How the maker filled it**: **the person who always makes it** told it themselves, and gave two reasons in their own
words: "to keep the body from rusting" and "to keep blood vessels soft and bendy".

**Other ways to fill it**:
- "I wanted my children to have Grandma's taste too."
- "It takes five minutes, even on a busy morning."
- "At first it went wrong every time. By the tenth try, it finally tasted good."

If your reasons are about **health**, it helps to check that you aren't saying too much ("What this sample shows" below
has the examples this sample fixed).

---

## Hole 2: Your own recipe (slides 2 to 5)

**Where**: the ingredients on slide 2, the combinations (the passes) on slide 3, the talk about the body on slide 4,
and the method and amounts on slide 5.

**What**: **your own favourite dish** — a "special skill" for each ingredient, and what happens when they are put together.

**Why**: "each one is useful on its own, but together they help each other" can be found in every dish. When the ingredients are
characters, listeners can follow who passes to whom.

**How the maker filled it**: cashew nuts, pine nuts, cherry tomatoes, golden kiwifruit, mixed berries and soy milk.
Three combinations were kept (the tomato's red × the nuts' oil, iron from plants × vitamin C, vitamin E × vitamin C).

**Other ways to fill it**:
- The spices in a curry (turmeric × black pepper, onions turning sweet as they cook)
- A sandwich (butter keeps the bread from going soggy; tomato × cheese)
- A soup (stock × salt, beans × greens)

**Looking things up with an AI**: for this sample, each ingredient's special skill and the combinations were looked up
with an AI. The answers didn't go straight into the story: **the AI was asked for sources, and they were checked** first
(see "What this sample shows").

**What changes along with the dish**:
- The title: the first line of the script and the `[Text]` on slide 1. If you remake the ending video, also `title` under
  `final_still` and `page` in `ending_video.json`
- The blender sound on slide 5 (`sounds/mixer.mp3`): a sound that fits your dish, or delete that line and its stage direction
- Slide 4 need not be about the body ("cooked together, the flavours come together" keeps the same frame)

---

## Hole 3: The music (all five slides)

**Where**: the `[BGM]` on slide 1. One piece loops through all five slides.

**What**: music that does not get in the way of the voice.

**Why**: one piece of music can make the story feel like your family's. Even more so if it's a piece that always plays
in your kitchen, or one your listeners love.

**How the maker filled it**: a film theme from the 1960s. In this public version it is replaced by a recording
anyone may use (a Schubert piano sonata).
For playing to your family, music you already own, such as songs copied from your own CDs, is generally thought to be fine (in Japan this counts as private use; it differs from country to country, and this is not legal advice). It was replaced here only because the work is given out beyond the family. Music you can use only by breaking its copy protection, such as tracks downloaded from a streaming service, is safer left out even at home.

**Other ways to fill it**:
- The music you always put on while cooking
- A piece you heard on a family outing
- A piece your child can play on the piano, played by your child

This sample uses music without words, so it doesn't get in the way of the narration. A song with words can work too if
it is in a language your listeners don't use every day. Which music to use is up to you.

**If you swap in your own music, its volume is evened out.** Before the show, the narrator's player measures each
piece and plays any that is too loud at a level that sits under the voice (the files are not changed, and quiet pieces
are not made louder).

---

## Hole 4: The ending video (after slide 5)

**Where**: the `[Video]` on slide 5. The narrator plays it after the story ends.

**What**: a video of about two and a half minutes in which the ingredient characters appear one by one, dance, and at
the end turn into one dish.

**Why**: it shows with pictures what the story said in words — "The six friends have become one." Nothing is added
after the narration; the video alone lets the feeling linger.

**How the maker filled it**: the characters' movements were made with an AI and set to a favourite song.
In this public version the song is replaced by a recording anyone may use (Mozart's Overture to *The Marriage of Figaro*),
and the clips are re-timed to it (the music shortened by leaving out its middle).

**Other ways to fill it**:
- A phone video of the dish being made
- Photos of the dish from different days, in order
- No video at all: end on the picture of slide 5 (that works too)

**Putting your own photos into the example's video**: this example comes with the definition of its ending video,
[ending_video.json](ending_video.json), and its song, `sounds/ending.mp3`. The video is cut into 27 "seats" on the
beats of the song, and the seats never move. Put your own photos or videos into only the seats you want to change; the
seats you leave alone are re-made just as they are in the example. You could, say, replace only the seats where the six
friends come in with photos of the ingredients in your own kitchen.

```
python ladder/ending-video/build_ending_video.py <work folder> --storyboard                 # a page of every seat (ending/storyboard.html), to choose the ones to change
python ladder/ending-video/build_ending_video.py <work folder> --replace 9=photos/kitchen.jpg   # a photo in seat 9 (a video from its 3rd second: photos/cooking.mp4@3)
python ladder/ending-video/build_ending_video.py <work folder>                               # makes videos/my_ending.mp4
```

- The tool is in the Digital Kamishibai repository, under `ladder/ending-video/` (it needs Python, Pillow and ffmpeg;
  its README has the details). Like the picture tool, it is optional: the kamishibai works without it. If you are
  making the work with an AI, asking "put this photo in seat 9" is often the quickest way
- Keeping the photos and videos you put in inside the work folder means nothing gets lost when the folder moves
- The re-made video is `videos/my_ending.mp4`. The example's `videos/ending.mp4` is the template the untouched seats
  are cut from, so it is worth keeping. To play your version in the show, change the `[Video]` on slide 5 of the
  script to `videos/my_ending.mp4`
- The closing seat (27) is the picture without a title, `videos/key_26.png`, with the title drawn on it. To change the
  title, change `title` under `final_still` in `ending_video.json`. The closing picture is the smoothie in the blender:
  with another dish, `--replace 27=<a photo of the finished dish>` puts yours there (the title is drawn on it)
- You can also make an ending video without this tool: a phone's photo app or a free video editor will put photos to
  a song. The example's song, `sounds/ending.mp3`, is yours to use as well (it is a recording anyone may use)

For showing to your family, your own videos and a favourite song you own are generally thought to be fine (in Japan this counts as private use; it differs from country to country). If you give the work out, or send it through the room player to people outside the family, it is safer to use music whose rights have expired, and to ask the people in the video first.

---

## Hole 5: The question (slide 2)

**Where**: the stage direction on slide 2, after "Six ingredients. Six friends."

**What**: a question for the listeners. This sample asks it once: "What colors can you see in these six?" **You can leave it out.**

**Why**: in a story you only listen to, this makes one moment when it is your turn to answer. Anyone can answer a question
about colors by looking at the picture.

**How the maker filled it**: the question went to a child who looked ready to answer. When an answer came, the story
went on without correcting it.

**Other ways to fill it**:
- "Which of these have you never eaten?"
- "Which one do you think is the strongest?"

This sample has just one question, so the story keeps moving. How many to ask is up to you.

---

## Hole 6: The pictures (all five slides)

**Where**: the five pictures in `pictures/`. The title and the amounts are laid on top later from `[Text]` in the script,
so the pictures need no words.

**What**: one picture per slide. If you change the recipe in hole 2, the ingredients in the pictures change too.

**Why**: with a photo of the real ingredients, listeners know at once: "that's the one we always have". Repainting in the
sample's style tends to make the work look like the sample. Keeping the same style is not a step you need for your own version.

**How the maker filled it**: all five were painted in one style by an AI that makes pictures (Gemini). The prompts are in
[plan.md](plan.md).

**Other ways to fill it** (easiest first):
- Phone photos of the real ingredients, or of the finished dish (landscape; with the top 15% or so left clear, the
  title fits there). Phone photos are usually 4:3, so dark bands show at the sides. On slide 5 the amounts sit on the
  right: leave the right third clear too, or add a `fill` (a band of colour behind the words) to the amounts' `[Text]`
- A drawing by your child, photographed in good light
- Pictures from a chat AI that makes pictures: you paste `[Prompt style]` and `[Prompt N]` from plan.md together.
  **If you change the characters, slide 2 comes first** (the other prompts are written to follow slide 2's picture);
  the new slide 2 then goes with each request for the rest. To rewrite a prompt for your own ingredients, rewrite that
  `[Prompt N]` in plan.md where it is (two prompts with the same number stop the picture tool)
- The sample's pictures as they are (even with different ingredients, the frame of the story — together they help each other — still works)

Photos and pictures can be mixed: a family photo on slide 1 and the sample's pictures for the rest also works.

**After adding a new picture, look at the script's `[Picture]` line.** The script names each picture, like `> [Picture] pictures/02.jpg`.
If your new picture has another name (`02.png`, `IMG_1234.jpg`), change that slide's `[Picture]` line to it
(otherwise the sample's picture keeps showing; the builder tells you when two pictures share a number).

---

If you give out a work made from this sample, add the credit "Digital Kamishibai, by Fast Focus Technologies" and say what
you changed (the sample's text is under CC BY 4.0; see [CREDITS.md](CREDITS.md)).

---

## What this sample shows: fixing claims that go too far

When you talk about health or science, especially to children, the easiest mistake is **saying too much**.
In this story, the maker's first words were checked against sources and then changed.

| First words | What checking found | What the story says |
|---|---|---|
| "It cleans your blood vessels" | No evidence it "washes them out". Some studies found that blood vessels widen more easily | There are studies showing they help blood vessels stretch and widen softly |
| "Antioxidants", "anti-ageing" | Taking one antioxidant as a supplement did not help people live longer. Eating foods of many colors is linked with protecting the body | They seem to be stronger as a team than when you take just one of them out |
| "Pine nuts are the food of immortals" | A legend from long ago, not evidence of a long life | There is a legend about a man who … became an immortal |
| "Vitamin C recharges vitamin E" | Clear in a test tube; how strongly it works in the body is still being studied | … is thought to … |

What this sample kept to:
- "is thought to", "there are studies showing" and "seem to" stayed in
- It never says "drink this and you'll live longer" or "you won't get sick"
- It never calls other foods or drinks "bad"
- Numbers (vitamin … mg) are not said in the story; amounts are shown on the screen

When you look things up with an AI, the quickest way is to ask: "Am I saying too much here? Check it with sources."
The sources are in [sources.md](sources.md).
