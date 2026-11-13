# Starting from a seed: a first draft, quickly

The interview (step 1 of the skill) settles a work little by little, in conversation. Some makers come another way:
they bring a **seed** — a line, a pasted conversation with another AI, a plan they already wrote — and want to see
something they can practise with. For them, **make a first draft all at once and get it into the player**: practising
and the correction sheet then do the rest. A draft that is read aloud teaches more than another round of questions.

Two round trips at most: **round 1, candidates → the maker chooses → round 2, the first draft.** If the seed already settles the
title and the structure, skip round 1.

## The seed is the maker's own words

Copy the seed **as it is** into the plan, under `## Seed`. Do not reword it. Then tell what kind of seed it is:

| Kind | How to tell | What to do |
|---|---|---|
| **A line** | a few lines, no title or structure | Round 1: candidates |
| **A pasted conversation with another AI** | speaker lines ("You:", "ChatGPT:"), a long back-and-forth | Separate **what the maker said or chose** (decided) from **what the AI only offered** (candidates), in a small table. Use what is decided; offer candidates only for what is left open |
| **A plan, ready to use** | a title, a structure, slides | No candidates. Hold it against `templates/plan-template.md` and list **only the empty sections**; ask whether to go on to round 2 |
| **A seed with wishes** | a book to build on, who it is for, a song, the ending video's song and photos | Every wish is **decided**. Check the facts it brings (step 3.5) and show the maker only what does not fit. Offer candidates only for what is left open |
| **A sample** | a finished work folder with `holes.md` in it (for example `six-friends-smoothie-ja`), or "use the sample to make our own" | No candidates and no round 1. Go through its holes instead: [Starting from a sample](#starting-from-a-sample) below |

- **What is written is decided; fill only what is empty.** The maker's words win. Do not overwrite a wish with a
  candidate.
- What is missing becomes **one short question the maker can be asked aloud** ("Where should the music come in on the
  drum slide?"). If no answer comes, go on with the hole empty: every hole is optional.
- If the seed continues an earlier work, read that work's plan first. Do not propose a series yourself.

## Round 1: candidates

1. Make the work folder (a short folder name from the contents; it need not change when the title does).
2. Start `plan.md` with only three sections — not the plan itself yet:
   - `## Seed` (and, for a pasted conversation, the table of decided and offered)
   - `## Candidates (the maker chooses; nothing decided yet)`: **three titles** (is each one understood at once, by
     ear?) and **two structures**, A and B — six to eight lines each: the opening, the peak, the end, about how many
     slides, and roughly which pictures go where
   - `## Questions` (if any): one short question each
3. Show the maker the three titles and the two structures, briefly. Say which one you would choose, and why, **only
   when asked**.

## Round 2: the first draft, all at once

Write what the maker chose — in their words — under `## Decided (<date>)`; keep the candidates below as "not chosen".
Then, in one go:

1. **The plan** (`templates/plan-template.md`), every section that matters before writing: length, the emotional curve,
   questions to the audience, music, videos, facts to check, picture prompts. Songs and videos not chosen yet are
   written as candidates and left open — the maker chooses them. Read the `plan` entries of `references/pitfalls.md`.
2. **Check the facts** (step 3.5) **before** writing the script. For health or nutrition, say how strong the evidence
   in people is.
3. **The whole script** (`templates/script-template.md`), every slide. Give each slide its title as `> [Text]` so it
   can be read on a board. Write for the youngest listener and for the narrator's voice.
4. **Boards instead of pictures**: `python <skill>/scripts/draft_boards.py <work folder>` puts a plain
   board on every slide that has no picture. **Do not make the real pictures yet**: they come once the script has
   settled, through a `picture` correction from practice (`references/correction-sheet.md`).
5. **Build for practising**: `python <skill>/scripts/build_work.py <work folder> --draft`. No errors;
   report the warnings.
6. Show the maker the main points (title, structure, slides and length, what the fact check changed) and the questions,
   and ask them to open the work in the player and read it. From here it is the usual loop: practise → correction
   sheet → write back.

## Starting from a sample

A sample is a finished work published to be remade. Its `holes.md` lists the places a maker replaces with their own
(the holes), how the sample's maker filled each one, and other ways to fill it. The story's frame is already there;
the work becomes the maker's own through the holes.

1. **Read `holes.md` first**, then `script.md`, then `plan.md` if there is one (the sample's picture prompts). With a
   chat AI the maker may have given only these three text files; that is enough. The pictures, sounds and videos stay
   on the maker's computer.
2. If the folder is there, copy it to a new work folder first, so that the sample stays as it was.
3. **Go through the holes one at a time**, in the order of `holes.md`, in the maker's language. For each hole, say in
   a line or two what it is and how the sample filled it, give one or two of the other ways from `holes.md`, and ask
   one short question. A hole that touches the people around the maker (who narrates, who is asked the question) is
   theirs to decide; do not choose for them.
4. **A hole the maker does not fill stays as the sample has it.** That is a finished choice, not something left
   undone. Do not come back to it unless the maker does.
5. Start `plan.md` (keep the sample's prompts below it if they are there) with a short table: each hole, and either
   the maker's own words or "as in the sample".
6. **The pictures** are a hole like any other. Offer the ways in `holes.md` easiest first: photos of the real thing,
   a child's drawing, a chat AI that makes pictures, or the sample's pictures as they are. If the maker changes the
   characters and paints with an AI, the sample's prompts follow slide 2's picture: paint slide 2 first and attach it
   for the rest (`gen_images.py --anchor 2` on the picture ladder). If the recipe changes but the pictures stay,
   tell the maker that the pictures still show the sample's ingredients, and let them choose. Write new prompts in
   `plan.md` only when the maker chooses an AI, and with no real person's name (`references/pictures.md`).
   **Rewrite a slide's `[Prompt N]` where it stands**, below the table: a second `[Prompt N]` for the same slide stops
   the picture ladder. The slides not redrawn keep the sample's prompts.
   **A new picture must be the one the script names.** The sample's `script.md` names each picture
   (`> [Picture] pictures/02.jpg`): a new picture saved beside it under another name or extension (a chat AI's
   `02.png`) is not shown until that line names it. Change the line, or save the new picture under the old name
   (keep the sample's picture somewhere outside `pictures/`). The builder warns when two pictures share a name.
   A phone photo is usually 4:3: the player shows it with dark bands at the sides, and words on the screen near the
   edge (the recipe on the last slide) can land on them or on a busy part of the photo — look at the built slide, and
   offer the maker a `fill` behind the words or a photo cut to 16:9.
7. **Rewrite only what the holes change** in `script.md`, in the maker's words, and keep the markers and the frame.
   A hole's narration starts with a mark on each line (highlighted on the narrator's screen): in the samples it is
   numbered after the hole in `holes.md` (`~1 ` for hole 1). When the maker's own words go in, take the mark off; a hole
   left as in the sample keeps it, number and all, so the narrator still sees they may tell it their way.
   A hole can reach past the slides `holes.md` names for it (the narrator is named again near the end; a new recipe
   changes the title, the slides that explain how the ingredients help each other, and sounds such as a mixer):
   before building, read the whole script once for what still belongs to the sample, and show the maker the list.
   New facts the holes bring (a new ingredient's "special skill") go through step 3.5 before they go into the script.
   Read `holes.md`'s notes on what the sample was careful about, and keep to them.
8. Build for practising (`build_work.py <work folder> --draft`) and go on as usual: practise → correction sheet.
9. If the maker means to give the work out beyond the family, point them to the rights notes in `holes.md` (the credit
   the sample's licence asks for, the music, the people in photos and videos). Give no legal judgement of your own.

## What not to do

- Do not decide the title, the story, the songs or the videos. Offer; the maker chooses.
- Do not generate pictures for a first draft.
- No deadlines, no "what next?", no record of how far the maker has got. If the questions are not answered, leave the
  holes empty and go on.
