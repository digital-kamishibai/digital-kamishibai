# Ladder: pictures with Gemini

Optional. **Not free.** You do not need this to make a kamishibai: family photos, drawings, or pictures you made
anywhere else work the same way. This tool is for families who already have a Gemini API key and want the computer to
paint the pictures from the plan.

## What it costs and needs

| | |
|---|---|
| Money | Every picture is billed to the owner of the API key: **about US$0.134 per picture** with `gemini-3-pro-image` at 2K (Google's price list, October 2026; there is no free tier for this model). Making a picture again costs again. Prices change: [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing). The tool prints the count and an estimate before it sends anything; `--dry-run` shows them without sending. |
| Key | A Gemini API key from Google AI Studio, in the environment variable `GEMINI_API_KEY` on the computer that runs the tool. **Never write the key in a file**, in the plan, or in a repository. |
| Software | Python 3.10 or later, and Pillow (`python -m pip install pillow`). |
| Age | Google's Gemini API terms (March 2026): users must be 18 or older, and the API may not be used as part of a service directed towards or likely to be accessed by people under 18. The adult who holds the key runs this tool. |

## Use

The prompts live in the plan (`plan.md` in the work folder), under two markers that are never translated:

````markdown
### [Prompt style]

```text
Watercolour, soft lines ... Do not draw any letters or numbers. Leave the top 15% empty.
```

### [Prompt 3] Morning

- Asserts: one boat on the beach, with a sleeping child in it
- Seen:

```text
Early morning after the storm ...
```
````

`[Prompt style]` is sent with every picture. `[Prompt N]` is slide N. **Asserts** is what the narration says about the
picture (a number, a shape, a difference); **Seen** is filled in after looking at the picture.

```
python ladder/images/gen_images.py <work folder>            # slides that have no picture yet
python ladder/images/gen_images.py <work folder> 3 5-7      # these slides
python ladder/images/gen_images.py <work folder> --dry-run  # what would be sent, and the cost
python ladder/images/gen_images.py <work folder> --use 3    # take the newest candidate for slide 3
```

- **Nothing is overwritten.** A slide with no picture gets `pictures/NN.png`, which the builder finds by itself.
  A slide that already has a picture gets a candidate, `pictures/_candidates/NN-K.png`. `--use N` (or `--use N-K`)
  puts it in place and moves the old picture to `pictures/_replaced/`.
- **The style follows slide 1.** Slide 1's picture is attached to the others with "match this style".
  If slide 1 is a photo or a placeholder, use `--anchor none` or `--anchor N`.
- Every picture is saved as PNG, at most 1920 px on its long side, without an alpha channel when it is fully opaque.
  Keep these pictures: the same prompt never paints the same picture twice.
- It warns when a picture is not 16:9, or has plain bands at its sides (a tall picture put in the middle).

## Look at every picture

A generated picture does not keep to the numbers and shapes in its prompt. **What counts is the picture as seen, not
as prompted.** After each run, check exactly what the narration asserts about each new picture, by eye, and write what
you see on `Seen:`. If a number comes out wrong twice, stop asking: draw that part another way, or say it in `[Text]`.

Try:

```
python ladder/images/gen_images.py examples/sample-story 3 --anchor none
```

The example already has a picture for slide 3, so this makes a candidate and leaves the example as it is
(`--anchor none`: the example's pictures are placeholders, not a style to follow). It costs one picture.
