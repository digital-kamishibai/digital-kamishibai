# Picture prompts — Six Friends Smoothie

These are the prompts the sample's five pictures were made with (hole 6, "the pictures", in [holes.md](holes.md), filled
in with an AI). `[Prompt style]` is the style shared by every picture; `[Prompt N]` is the picture for slide N.
The pictures were made from the original Japanese prompts; these are translations.

To paint with a chat AI that makes pictures, you paste `[Prompt style]` and `[Prompt N]` together.
The prompts for slides 1, 3, 4 and 5 say "the same six characters as in the attached picture": they are written to
follow the picture of slide 2 (the six friends). If you change the characters, it works best to paint slide 2 first
and attach it when you ask for the rest; the pictures come out more alike that way.
With the picture ladder (`ladder/images/gen_images.py`), `--anchor 2` makes slide 2 the picture the others follow.

### [Prompt style]

```text
A slide for a children's picture-story show. A gentle watercolour illustration in pastel colours. Soft lines. Cute and friendly.

Composition: fill the whole 16:9 landscape frame. The top 15% of the frame is a plain white band (space for words; draw nothing there). The picture itself sits below the band. No margins, borders or frames on the left or right.
```

### [Prompt 1] Cover: "Six Friends Smoothie ~ How Passes Connect Inside Your Body ~"

```text
Scene: a bright kitchen in the morning. Morning light comes in through the window. In the middle of a wooden table stands an empty clear blender. Around it, the same six ingredient characters as in the attached picture stand in a row, smiling and looking up at the blender: a crescent-shaped cashew nut, three teardrop-shaped pine-nut brothers, a red cherry tomato, a golden kiwifruit cut in half (yellow inside), a little group of four mixed berries (a strawberry, a blueberry, a raspberry and a blackberry), and a white carton of soy milk. Every character has round eyes and a smiling mouth. No people. No cups or glasses.

About words: do not draw any words at all in the picture. No title, labels, captions, numbers, writing on packages or logos. The words will be laid on top later. But leave the white band at the top, the one set aside as space for words, plain white, with no words or patterns in it.
```

### [Prompt 2] Six friends

```text
Scene: six ingredient characters stand side by side in a row, facing us and cheerfully saying hello (a picture introducing the characters). From left to right:
1. Cashew nut — a cream-coloured, crescent-shaped nut. Round eyes and a smiling mouth. A kind big brother.
2. Pine nuts — three small, ivory, teardrop-shaped kernels in a row: brothers. Small eyes. Busy and lively.
3. Cherry tomato — a shiny red ball with a green stalk for a hat. Waving with lots of energy.
4. Golden kiwifruit — a kiwifruit cut in half. The cut side is bright yellow, with a ring of small black seeds and an edge of brown skin. A bright smile.
5. Mixed berries — a little group of four: a strawberry, a blueberry, a raspberry and a blackberry. Many colours.
6. Soy milk — a white paper carton (no words or logo) with a face. Calm; the one who brings everyone together.
All six are about the same size, evenly spaced. Every character has small hands and feet. No people.

About words: do not draw any words at all in the picture. No name labels, captions, numbers, writing on packages or logos. The words will be laid on top later. But leave the white band at the top, the one set aside as space for words, plain white, with no words or patterns in it.
```

### [Prompt 3] Passing to each other

```text
Scene: on the bright green grass of a football pitch, the same six ingredient characters as in the attached picture are playing, passing to each other as in football.
- The main pass (in the middle of the frame, the largest): the crescent-shaped cashew nut passes a shining golden drop (a drop of oil), like a ball, to the red cherry tomato. The cherry tomato catches it happily with both hands.
- A side pass (on the right, smaller): the golden kiwifruit cut in half passes a small glowing orange ball towards the cashew nut, the three pine-nut brothers and the white carton of soy milk.
- The group of four mixed berries cheers nearby.
Draw the path of each pass as a soft streak of light, not a dotted line. Everyone is having fun. No people.

About words: do not draw any words at all in the picture. No labels, captions, numbers, words next to arrows, signs on the goal, writing on packages or logos. The words will be laid on top later. But leave the white band at the top, the one set aside as space for words, plain white, with no words or patterns in it.
```

### [Prompt 4] A team that protects your body

```text
Scene: a park in spring. A soft, light-blue, bendy rubber hose runs across the frame from left to right in a gentle wave, and clear water flows smoothly through it (a spray of water with a small rainbow at the end of the hose). Around the hose, the same six ingredient characters as in the attached picture hold hands in a ring and watch happily: a crescent-shaped cashew nut, three teardrop-shaped pine-nut brothers, a red cherry tomato, a golden kiwifruit cut in half, a group of four mixed berries, and a white carton of soy milk. The cherry tomato and the cashew nut, especially, stand right by the hose with their hands on it. No people. Calm and bright.

About words: do not draw any words at all in the picture. No labels, captions, numbers, signs, writing on packages or logos. The words will be laid on top later. But leave the white band at the top, the one set aside as space for words, plain white, with no words or patterns in it.
```

### [Prompt 5] How to make it

```text
Scene (the left 55% of the frame): a clear blender on a wooden kitchen table in the morning. The same six ingredient characters as in the attached picture are happily jumping into the blender: first the crescent-shaped cashew nut, the three teardrop-shaped pine-nut brothers and the white carton of soy milk. Behind them, the red cherry tomato, the golden kiwifruit cut in half and the group of four mixed berries wait their turn in a line. Inside the blender, a smooth smoothie in pale pink and cream swirls round. No people. No cups or glasses.

About words: do not draw any words at all in the picture. No labels, captions, numbers, recipe text, numbers on the blender's scale, writing on packages or logos. The words will be laid on top later. But leave the white band at the top, the one set aside as space for words, and the recipe card on the right, plain, with no words or patterns in them.
```
