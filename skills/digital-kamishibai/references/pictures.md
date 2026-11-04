# Pictures

Any picture works: family photos, a child's drawing, pictures painted or generated anywhere. The room player only
needs one picture per slide in `pictures/` (`01.jpg`, `02.png`, … by slide number, or named with `> [Picture]`).

## Where pictures come from

| Way | Cost | Notes |
|---|---|---|
| Family photos and videos | free | Look at each one at full size, corners included: a photo taken for another use can carry a title, a caption or a watermark. Check the orientation of portrait videos by eye. |
| Drawings | free | Photograph or scan them in daylight; landscape (16:9) fits the screen. |
| A chat AI that makes pictures | the maker's own subscription | Ask for 16:9 and for no words in the picture. Save each picture into `pictures/`. |
| **The picture ladder** (`ladder/images/` in the Digital Kamishibai repository) | **paid per picture** (Gemini API, about US$0.134 each in October 2026) and needs Python, Pillow and a Gemini API key | Paints every slide from the plan's prompt table. Only for a family that already has the key; see below. |

Photos stay on the family's devices. You never need to see them unless the maker shows you one.

## Writing prompts (any generator)

Keep the prompts in the plan, one per slide, under the markers `### [Prompt style]` and `### [Prompt N]`
(see `templates/plan-template.md`; the markers are never translated). Then:

- **No real person's name** in a prompt. Describe them instead (age, hair, clothes), or leave them out of the picture.
  Faces of the family's own children are their parents' choice; a back view or a silhouette is often enough.
- **No words in the picture.** Generators misspell, and in many languages invent characters. Write in every prompt
  that the picture has no letters, numbers or signs, and put the words in `[Text]` on the slide instead.
- **Leave a calm band** (sky, wall, sea) where `[Text]` will sit, and say where in the prompt.
- **Give every person an age.** "An old keeper" may come out much older than meant; "a man of about sixty" does not.
- **Say "fills the frame from the left edge to the right edge"** for tall subjects (cliffs, towers, people standing):
  otherwise a tall picture can come back centred between plain bands.
- **Keep one style**: paint the cover first, then ask for the others "in the style of the attached picture".
- **For a sequel, choose the attached picture with care.** A group picture from the earlier work tends to be copied
  almost as it is, and a new character drawn next to it may come out as someone else (an animal turns human).
  Attach a picture where the **new** character came out right, and describe the old ones in words.
- **If words on the screen seem to vanish**, measure the colour of the picture behind them before blaming an overlap:
  white words on a pale sky disappear. Move the box to the calm band, or give it a `fill`.

## Look at the picture, not the prompt

A generated picture does not keep to the numbers and shapes in its prompt — numbers least of all. When the narration
says "three bends" and the picture shows one, the listeners believe the picture.

1. For each slide, write on its `Asserts:` line what the narration says **about the picture**: a number, a shape,
   a difference between two things, something that is on or off. "Nothing" is a fine answer.
2. **Right after a picture is made, check exactly those, by eye**, one at a time. Not the whole prompt: what the
   narration points at. Then look once more for anything that contradicts the narration (a lamp that should be dark
   is lit, a season that is wrong).
3. **Write what you see** on the `Seen:` line. What counts is the picture as seen, not as prompted.
4. **Do not leave numbers to the generator.** If it misses twice, stop asking: draw that part another way (a simple
   drawing, a photo), or let the narration and `[Text]` carry the number.

If you can see images (the maker shows you the picture, or you can open the file), look yourself and tell the maker
what you see. If you cannot, give the maker the `Asserts:` lines to check.

## The picture ladder

Only when the maker wants it, and run by the adult who holds the key (Google's terms for the Gemini API require
users to be 18 or older). Before running it, **say how many pictures and about
how much it will cost**, and that the key's owner pays; making a picture again costs again.

```
python <repository>/ladder/images/gen_images.py <work folder>              # slides with no picture yet
python <repository>/ladder/images/gen_images.py <work folder> 3 5-7        # these slides
python <repository>/ladder/images/gen_images.py <work folder> --dry-run    # what would be sent, and the cost
python <repository>/ladder/images/gen_images.py <work folder> --use 3      # take the newest candidate for slide 3
```

Installed as a plugin, `<repository>` is two folders above this skill's folder.
The key is read from the environment variable `GEMINI_API_KEY`: **never ask for the key,
never write it in a file or a command line, and never print it.** If it is not set, say so and stop; setting it up is
the key holder's job.

- It never overwrites a picture: a slide that already has one gets a candidate in `pictures/_candidates/`, and nothing
  changes until `--use`. The old picture is kept in `pictures/_replaced/`. **The maker chooses** which candidate to use.
- Pictures are saved at most 1920 px wide and without transparency, ready for the builder.
- After each run it prints the `Asserts:` lines of the new pictures. Do the check above before calling a picture done.
- A request from the room player's correction sheet (`## [Slide N] picture`) goes the same way: change the prompt,
  make a candidate, and the maker chooses — in the room player, which shows a slide's candidates while practising and
  writes the choice on the sheet as `Use` (`references/correction-sheet.md`).
