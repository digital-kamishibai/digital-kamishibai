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

## What not to do

- Do not decide the title, the story, the songs or the videos. Offer; the maker chooses.
- Do not generate pictures for a first draft.
- No deadlines, no "what next?", no record of how far the maker has got. If the questions are not answered, leave the
  holes empty and go on.
