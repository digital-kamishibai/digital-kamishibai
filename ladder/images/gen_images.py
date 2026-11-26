#!/usr/bin/env python3
"""Make a work's pictures with Google's Gemini image model, from the prompt table in its plan.

    python gen_images.py <work folder>               # every prompt whose slide has no picture yet
    python gen_images.py <work folder> 2 5-7         # these slides (a slide that has a picture gets a candidate)
    python gen_images.py <work folder> --dry-run     # what would be sent, and what it would cost; no key needed
    python gen_images.py <work folder> --use 5       # take the newest candidate for slide 5 (or --use 5-2)

This is a ladder: optional, and not free. It needs Python 3.10+, Pillow (pip install pillow) and a Gemini API key
in the environment variable GEMINI_API_KEY. Every picture is billed to the key's owner, re-made pictures included.
See README.md next to this file.

The prompts come from the plan (plan.md in the work folder, or --plan FILE): a code block under a heading
"### [Prompt style]" (sent with every picture) and one under "### [Prompt N]" for slide N. The markers are not
translated; the rest of the plan may be in any language.

Pictures are never overwritten. A slide with no picture gets pictures/NN.png. A slide that already has one gets a
candidate, pictures/_candidates/NN-K.png; --use moves the old picture to pictures/_replaced/ and puts the candidate
in its place. If an ending video of the work (ending_video*.json) shows the old picture in a seat, --use names the seat
and the command that puts the new picture there (it never changes the ending video itself). Every picture is saved as PNG, at most 1920 px on its long side, and without an alpha channel when it is
fully opaque.

Pictures can be attached as references, each with a role (on the command line, or per slide in the plan):
    --anchor N|FILE      the style to follow (repeatable; default: slide 1; "none" for no style picture)
    --character N|FILE   characters to draw with the same look (repeatable), e.g. a picture from the previous work
    --sketch             the slide's own picture now (a rough sketch) as the composition to follow
A number is a slide of this work; anything else is a file. In the plan, under "### [Prompt N]":
    - Anchor: 2, ../previous-work/pictures/02.png     (or "none"; a path is from the plan's folder)
    - Character: 2
    - Sketch: yes
A line in the plan replaces the command line's choice of that role for that slide.

A generated picture does not keep to the numbers and shapes in its prompt. After each run, look at every new picture
and check what the narration says about it (the "Asserts:" line of its prompt); write what you see on "Seen:".
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

KEY_ENV = 'GEMINI_API_KEY'
MODEL = 'gemini-3-pro-image'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
PRICING_URL = 'https://ai.google.dev/gemini-api/docs/pricing'
COST_PER_PICTURE = {'gemini-3-pro-image': 0.134}        # US$, 2K, standard tier (Google's price list, 2026-10)

MAX_SIDE = 1920
PICTURE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')        # the builder's order (build_work.py)
CANDIDATES = '_candidates'
REPLACED = '_replaced'
ENDING_DEFINITIONS = 'ending_video*.json'   # the ending video ladder's definitions, in the work folder
BAND_LIMIT = 0.04                                         # side bands wider than this share of the width
ASPECT = 16 / 9
ASPECT_TOLERANCE = 0.02                                   # the builder stretches within 2%, letterboxes beyond

HEADING = re.compile(r'^#{2,4}[ \t]+\[Prompt[ \t]+(style|\d+)\][ \t]*(.*?)[ \t]*$')
NEAR_HEADING = re.compile(r'^#{1,6}[ \t]*\[\s*prompt', re.IGNORECASE)
ANY_HEADING = re.compile(r'^#{1,6}[ \t]')
FENCE = re.compile(r'^[ \t]*(```|~~~)')
ASSERTS = re.compile(r'^[ \t]*[-*][ \t]*Asserts:[ \t]*(.*?)[ \t]*$')

STYLE_NOTE = ('The attached picture is from the same picture-story show. Match its drawing style, colours, line '
              'quality and lighting closely. Draw a new picture; do not copy its content.\n\n')
CHARACTER_NOTE = ('The attached picture shows characters of this picture-story show (people, animals or things). '
                  'Wherever they appear in the new picture, draw them with the same look: face, hair, clothes, colours '
                  'and build. Draw a new scene; do not copy its scene, pose or composition.\n\n')
# a sketch: what rough sketches did when sent as they were (in a real work): their notes and frame were copied, the
# middle was left white like their paper, and the empty areas asked for the words came out as bands of another colour
SKETCH_NOTE = ('The attached picture is a rough sketch of this very picture. Follow its composition: the same things '
               'in the same places, at about the same sizes, with the same colours where it shows them. It is only a '
               'sketch: do not copy its words, notes, arrows, dotted lines, frames or the colour of its paper. Paint '
               'the background across the whole picture in one piece, with no bands of another colour.\n\n')
NOTES = {'style': STYLE_NOTE, 'character': CHARACTER_NOTE, 'sketch': SKETCH_NOTE}
ROLES = {'Anchor': 'style', 'Character': 'character', 'Sketch': 'sketch'}
MAX_REFERENCES = 14                                       # input pictures per request (Gemini 3 Pro Image)
REFERENCE = re.compile(r'^[ \t]*[-*][ \t]*(Anchor|Character|Sketch):[ \t]*(.*?)[ \t]*$')


@dataclass
class Prompts:
    style: str = ''
    slides: dict[int, str] = field(default_factory=dict)
    asserts: dict[int, str] = field(default_factory=dict)
    refs: dict[int, dict] = field(default_factory=dict)   # slide -> {'style': [...], 'character': [...], 'sketch': bool}
    errors: list[str] = field(default_factory=list)


# ---------- the plan ----------

def parse_plan(text: str) -> Prompts:
    """Read the [Prompt style] and [Prompt N] blocks. Headings and other text may be in any language."""
    result = Prompts()
    sections: list[tuple[str, int, list[str]]] = []      # (style or N, line number, lines under the heading)
    current: list[str] | None = None
    fence = ''
    for number, line in enumerate(text.replace('\r\n', '\n').split('\n'), 1):
        if fence:                                          # inside a code block nothing is a heading
            if current is not None:
                current.append(line)
            if line.strip().startswith(fence):
                fence = ''
            continue
        opened = FENCE.match(line)
        if opened:
            fence = opened.group(1)
        elif HEADING.match(line):
            current = []
            sections.append((HEADING.match(line).group(1), number, current))
            continue
        elif NEAR_HEADING.match(line):
            result.errors.append(f'line {number}: looks like a prompt heading but is not one: {line.strip()!r} '
                                 '(write "### [Prompt style]" or "### [Prompt N]"; do not translate it)')
        elif ANY_HEADING.match(line):
            current = None
            continue
        if current is not None:
            current.append(line)
    if fence:
        result.errors.append('a code block is not closed')

    for key, line, body in sections:
        asserts, block, fence, done, refs = '', [], '', False, {}
        for row in body:                                   # only the first code block is the prompt
            if done:
                break
            if not fence:
                opened = FENCE.match(row)
                if opened:
                    fence = opened.group(1)
                elif ASSERTS.match(row) and not asserts:
                    asserts = ASSERTS.match(row).group(1)
                elif REFERENCE.match(row):
                    name, value = REFERENCE.match(row).groups()
                    role = ROLES[name]
                    if role in refs:
                        result.errors.append(f'line {line}: [Prompt {key}]: a second "{name}:"')
                    elif role == 'sketch':
                        if value.lower() not in ('yes', 'no'):
                            result.errors.append(f'line {line}: [Prompt {key}]: "Sketch:" is yes or no')
                        refs[role] = value.lower() == 'yes'
                    else:
                        refs[role] = [v.strip() for v in value.split(',') if v.strip()]
            elif row.strip().startswith(fence):
                done = True
            else:
                block.append(row)
        prompt = '\n'.join(block).strip()
        if not prompt:
            result.errors.append(f'line {line}: [Prompt {key}] has no prompt '
                                 '(put it in a ``` code block under the heading)')
            continue
        if key == 'style':
            if refs:
                result.errors.append(f'line {line}: [Prompt style] takes no "Anchor:", "Character:" or "Sketch:"')
            if result.style:
                result.errors.append(f'line {line}: a second [Prompt style]')
            result.style = prompt
            continue
        slide = int(key)
        if slide < 1:
            result.errors.append(f'line {line}: [Prompt {slide}]: slides start at 1')
        elif slide in result.slides:
            result.errors.append(f'line {line}: a second [Prompt {slide}]')
        else:
            result.slides[slide] = prompt
            if asserts:
                result.asserts[slide] = asserts
            if refs:
                result.refs[slide] = refs
    if not result.errors and not result.slides:
        result.errors.append('no "### [Prompt N]" found in the plan (the marker is not translated)')
    return result


def full_prompt(prompts: Prompts, number: int) -> str:
    return (prompts.style + '\n\n' + prompts.slides[number]) if prompts.style else prompts.slides[number]


def parse_numbers(words: list[str]) -> list[int]:
    numbers: list[int] = []
    for word in words:
        m = re.fullmatch(r'(\d+)(?:-(\d+))?', word)
        if not m:
            raise ValueError(f'not a slide number or range: {word!r}')
        first, last = int(m.group(1)), int(m.group(2) or m.group(1))
        if last < first:
            raise ValueError(f'empty range: {word!r}')
        numbers += [n for n in range(first, last + 1) if n not in numbers]
    return numbers


# ---------- the pictures folder ----------

def existing_picture(pictures: Path, number: int) -> Path | None:
    for ext in PICTURE_EXTS:
        path = pictures / f'{number:02d}{ext}'
        if path.is_file():
            return path
    return None


def candidates(pictures: Path, number: int) -> list[tuple[int, Path]]:
    found = []
    for path in (pictures / CANDIDATES).glob(f'{number:02d}-*.png'):
        m = re.fullmatch(rf'{number:02d}-(\d+)\.png', path.name)
        if m:
            found.append((int(m.group(1)), path))
    return sorted(found)


def output_path(pictures: Path, number: int) -> Path:
    """Where a new picture for this slide goes. Never an existing file."""
    if existing_picture(pictures, number) is None:
        return pictures / f'{number:02d}.png'
    taken = candidates(pictures, number)
    k = taken[-1][0] + 1 if taken else 1
    return pictures / CANDIDATES / f'{number:02d}-{k}.png'


def use_candidate(pictures: Path, spec: str) -> str:
    """Put a candidate in a slide's place; the old picture is moved to _replaced/, never deleted."""
    m = re.fullmatch(r'(\d+)(?:-(\d+))?', spec)
    if not m:
        raise ValueError(f'--use takes N or N-K, not {spec!r}')
    number = int(m.group(1))
    found = dict(candidates(pictures, number))
    if not found:
        raise ValueError(f'slide {number}: no candidates in {pictures / CANDIDATES}')
    k = int(m.group(2)) if m.group(2) else max(found)
    if k not in found:
        raise ValueError(f'slide {number}: no candidate {number:02d}-{k}.png (there are: '
                         + ', '.join(f'{number:02d}-{n}' for n in sorted(found)) + ')')
    old = existing_picture(pictures, number)
    moved = ''
    if old is not None:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        target = pictures / REPLACED / f'{number:02d}-{stamp}{old.suffix.lower()}'
        target.parent.mkdir(parents=True, exist_ok=True)
        old.rename(target)
        moved = f'; the old picture is in {target}'
    new = pictures / f'{number:02d}.png'
    found[k].rename(new)
    lines = [f'slide {number}: {found[k].name} is now {new}{moved}']
    if old is not None:
        lines += ending_notes(pictures.parent, old, new)
    return '\n'.join(lines)


def ending_seats_showing(work: Path, picture: Path) -> list[tuple[str, int]]:
    """(definition file, seat number) of every seat of the work's ending videos that shows this picture.
    A seat's src is in the work folder when the definition has no photo_root or the seat says "root": "work"
    (the ladder's resolve_src). Unreadable definitions are left to the ladder's own --check."""
    target = os.path.normcase(os.path.normpath(str(picture.resolve())))
    out = []
    for path in sorted(work.glob(ENDING_DEFINITIONS)):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            root = data.get('photo_root')
            base = (Path(root) if os.path.isabs(root) else work / root) if root else work
            for f in data.get('frames', []):
                src = f.get('src')
                if not src:
                    continue
                where = work if f.get('root') == 'work' else base
                if os.path.normcase(os.path.normpath(str((where / src).resolve()))) == target:
                    out.append((path.name, int(f['i'])))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return out


def ending_notes(work: Path, old: Path, new: Path) -> list[str]:
    """The ending video seats that still show the picture just moved away, and the command that puts the new one there.
    Never replaced here: the ending video is the maker's; they say whether the new picture goes there too."""
    notes = []
    rel = new.relative_to(work).as_posix()
    for name, seat in ending_seats_showing(work, old):
        config = name[len('ending_video_'):-len('.json')] if name.startswith('ending_video_') else ''
        opt = f'--config {config} ' if config else ''
        notes.append(f'note: seat {seat} of the ending video ({name}) still shows the old picture. If the maker wants '
                     f'the new one there too: build_ending_video.py <work folder> {opt}--replace {seat}={rel}, '
                     'then the storyboard and the video again')
    return notes


# ---------- one picture ----------

def tidy(data: bytes):
    """Fully opaque -> RGB; long side at most MAX_SIDE. Returns a Pillow image."""
    from PIL import Image
    image = Image.open(io.BytesIO(data))
    image.load()
    if image.mode == 'P':
        image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
    if image.mode in ('RGBA', 'LA'):
        low, _high = image.getchannel('A').getextrema()
        if low == 255:
            image = image.convert('RGB' if image.mode == 'RGBA' else 'L')
    elif image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')
    if max(image.size) > MAX_SIDE:
        scale = MAX_SIDE / max(image.size)
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.LANCZOS)
    return image


def side_bands(image) -> float:
    """Share of the width taken by plain vertical bands at the left and right edges (a tall picture centred on 16:9)."""
    from PIL import ImageStat
    small = image.convert('RGB')
    if small.width > 480:
        small = small.resize((480, max(1, round(small.height * 480 / small.width))))
    w, h = small.size

    def run(xs) -> int:
        n = 0
        for x in xs:
            if sum(ImageStat.Stat(small.crop((x, 0, x + 1, h))).stddev) / 3 >= 6.0:
                break
            n += 1
        return n
    return (run(range(w)) + run(range(w - 1, -1, -1))) / w


def picture_warnings(image) -> list[str]:
    warnings = []
    ratio = image.width / image.height
    if abs(ratio - ASPECT) / ASPECT > ASPECT_TOLERANCE:
        warnings.append(f'{image.width}x{image.height} is not 16:9; the builder will put it on black')
    bands = side_bands(image)
    if bands > BAND_LIMIT:
        warnings.append(f'plain bands at the sides ({bands:.0%} of the width): probably a tall picture in the middle. '
                        'Add "fills the frame from the left edge to the right edge, no bands" to the prompt and make it again')
    return warnings


# ---------- Gemini ----------

def request_body(prompt: str, refs: list[tuple[str, Path]]) -> dict:
    """refs: (role, picture) in the order of references(); each picture is followed by what to take from it."""
    parts = []
    for role, picture in refs:
        mime = 'image/png' if picture.suffix.lower() == '.png' else (
            'image/webp' if picture.suffix.lower() == '.webp' else 'image/jpeg')
        parts.append({'inline_data': {'mime_type': mime, 'data': base64.b64encode(picture.read_bytes()).decode('ascii')}})
        parts.append({'text': NOTES[role]})
    parts.append({'text': prompt})
    return {'contents': [{'parts': parts}],
            'generationConfig': {'responseModalities': ['IMAGE'],
                                 'imageConfig': {'aspectRatio': '16:9', 'imageSize': '2K'}}}


def request_image(key: str, model: str, body: dict, retries: int = 3) -> bytes:
    """Send one request; return the picture's bytes. The key travels in a header and is never printed."""
    data = json.dumps(body).encode('utf-8')
    last = ''
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(ENDPOINT.format(model=model), data=data, method='POST',
                                     headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
        try:
            with urllib.request.urlopen(req, timeout=300) as res:
                answer = json.loads(res.read().decode('utf-8'))
            for candidate in answer.get('candidates', []):
                for part in candidate.get('content', {}).get('parts', []):
                    inline = part.get('inlineData') or part.get('inline_data')
                    if inline and inline.get('data'):
                        return base64.b64decode(inline['data'])
            reason = [c.get('finishReason') for c in answer.get('candidates', [])] or answer.get('promptFeedback')
            last = f'no picture in the answer ({reason})'
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code}: {e.read().decode("utf-8", "replace")[:300]}'
            if 400 <= e.code < 500 and e.code != 429:
                break                                           # a wrong key or a refused prompt: retrying will not help
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = f'{type(e).__name__}: {e}'
        if attempt < retries:
            time.sleep(5 * attempt)
    raise RuntimeError(last.replace(key, '***') if key else last)


# ---------- the run ----------

def choose(prompts: Prompts, pictures: Path, numbers: list[int]) -> tuple[list[int], list[str]]:
    notes = []
    if numbers:
        missing = [n for n in numbers if n not in prompts.slides]
        if missing:
            raise ValueError('no [Prompt N] for slide ' + ', '.join(map(str, missing)))
        return numbers, notes
    chosen = []
    for n in sorted(prompts.slides):
        if existing_picture(pictures, n) is None:
            chosen.append(n)
        else:
            notes.append(f'slide {n}: has a picture; skipped (name the slide to make a candidate)')
    return chosen, notes


@dataclass
class Choice:
    """The references asked for on the command line. A slide's line in the plan replaces that role for the slide."""
    style: list[str]
    character: list[str]
    sketch: bool
    plan_dir: Path = Path('.')

    def of(self, prompts: Prompts, number: int) -> tuple[list[str], list[str], bool]:
        mine = prompts.refs.get(number, {})
        style = mine.get('style', self.style)
        return ([] if style == ['none'] else style), mine.get('character', self.character), mine.get('sketch', self.sketch)


def references(choice: Choice, prompts: Prompts, pictures: Path,
               number: int) -> tuple[list[tuple[str, Path]], list[str], list[str]]:
    """The pictures to attach to slide `number`: [(role, picture)] in the order style, characters, sketch (the most
    particular last, next to the prompt); then errors (nothing is sent for this slide) and notes.
    A slide that has no picture yet is left out with a note (it may be made earlier in the same run)."""
    style, character, sketch = choice.of(prompts, number)
    mine = prompts.refs.get(number, {})
    refs, errors, notes = [], [], []
    for role, specs in (('style', style), ('character', character)):
        for spec in specs:
            if spec.isdigit():
                source = int(spec)
                if source == number:                       # its own picture is not its own reference
                    continue
                found = existing_picture(pictures, source)
                if found is None:
                    notes.append(f'{role} from slide {source}: it has no picture yet')
                else:
                    refs.append((role, found))
                continue
            path = Path(spec)
            if not path.is_absolute() and role in mine:     # a path in the plan is read from the plan's folder
                path = choice.plan_dir / path
            if path.suffix.lower() not in PICTURE_EXTS:
                errors.append(f'{role} from {spec}: not a picture ({", ".join(PICTURE_EXTS)})')
            elif not path.is_file():
                errors.append(f'{role} from {spec}: not found ({path})')
            else:
                refs.append((role, path))
    if sketch:
        own = existing_picture(pictures, number)
        if own is None:
            errors.append('sketch: the slide has no picture to follow')
        else:
            refs.append(('sketch', own))
    if len(refs) > MAX_REFERENCES:
        errors.append(f'{len(refs)} pictures attached; at most {MAX_REFERENCES}')
    return refs, errors, notes


def referred_slides(choice: Choice, prompts: Prompts, numbers: list[int]) -> list[int]:
    """Slides of this run whose pictures others follow: they are made first."""
    first = []
    for n in numbers:
        style, character, _ = choice.of(prompts, n)
        for spec in style + character:
            if spec.isdigit() and int(spec) in numbers and int(spec) != n and int(spec) not in first:
                first.append(int(spec))
    return first


def describe(refs: list[tuple[str, Path]]) -> str:
    if not refs:
        return 'nothing attached'
    return '; '.join(f'{role}: ' + ', '.join(str(p) for r, p in refs if r == role)
                     for role in NOTES if any(r == role for r, _ in refs))


def cost_line(model: str, count: int) -> str:
    price = COST_PER_PICTURE.get(model)
    if price is None:
        return f'{count} picture(s) with {model}: see {PRICING_URL} for the price'
    return (f'{count} picture(s) with {model}: about US${price * count:.2f} '
            f'(US${price} each; prices change: {PRICING_URL})')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Make pictures from the prompt table in the plan (Gemini; paid).')
    parser.add_argument('folder', type=Path, help='the work folder (pictures go in its pictures/ folder)')
    parser.add_argument('slides', nargs='*', help='slide numbers or ranges such as 5-7 (default: slides with no picture)')
    parser.add_argument('--plan', type=Path, help='the plan file (default: plan.md in the work folder)')
    parser.add_argument('--anchor', action='append', metavar='N|FILE',
                        help='a picture whose style to follow: a slide number or a file (repeatable; default 1), '
                             'or "none"')
    parser.add_argument('--character', action='append', default=[], metavar='N|FILE',
                        help='a picture of characters to draw with the same look (repeatable)')
    parser.add_argument('--sketch', action='store_true',
                        help="follow the composition of the slide's own picture now (a rough sketch)")
    parser.add_argument('--model', default=os.environ.get('DK_GEMINI_MODEL', MODEL), help=f'default {MODEL}')
    parser.add_argument('--dry-run', action='store_true', help='show what would be sent and the cost; send nothing')
    parser.add_argument('--use', metavar='N[-K]', help='put candidate K (default: the newest) in slide N\'s place')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # a Japanese Windows console cannot show every character
        if hasattr(stream, 'reconfigure'):
            if stream.isatty():
                stream.reconfigure(errors='backslashreplace')
            else:  # into a pipe or a file: UTF-8 (not cp932 on a Japanese Windows)
                stream.reconfigure(encoding='utf-8', errors='backslashreplace')

    pictures = args.folder / 'pictures'
    if args.use:
        try:
            print(use_candidate(pictures, args.use))
        except ValueError as e:
            print(f'error: {e}', file=sys.stderr)
            return 1
        return 0
    style = args.anchor or ['1']
    if 'none' in style and len(style) > 1:
        print('error: --anchor none cannot go with another --anchor', file=sys.stderr)
        return 1

    plan = args.plan if args.plan is not None else args.folder / 'plan.md'
    if not plan.is_file():
        print(f'error: {plan} not found', file=sys.stderr)
        return 1
    prompts = parse_plan(plan.read_text(encoding='utf-8'))
    choice = Choice(style, args.character, args.sketch, plan.parent)
    for error in prompts.errors:
        print(f'error: {plan.name}: {error}', file=sys.stderr)
    if prompts.errors:
        return 1
    try:
        numbers, notes = choose(prompts, pictures, parse_numbers(args.slides))
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    for note in notes:
        print(note)
    if not numbers:
        print('nothing to make')
        return 0
    # the pictures that others follow go first
    first = referred_slides(choice, prompts, numbers)
    numbers = first + [n for n in numbers if n not in first]
    # a missing file stops the run before anything is paid for
    stops = [f'slide {n}: {e}' for n in numbers for e in references(choice, prompts, pictures, n)[1]]
    for stop in stops:
        print(f'error: {stop}', file=sys.stderr)
    if stops:
        return 1
    print(cost_line(args.model, len(numbers)))

    if args.dry_run:
        for n in numbers:
            refs, _, notes = references(choice, prompts, pictures, n)
            print(f'\n--- slide {n} -> {output_path(pictures, n)} ({describe(refs)})'
                  + ''.join(f'\n    ({note}; attached if it is made first in this run)' for note in notes)
                  + f'\n{full_prompt(prompts, n)}')
        print('\n(dry run: nothing sent)')
        return 0

    key = os.environ.get(KEY_ENV, '').strip()
    if not key:
        print(f'error: the environment variable {KEY_ENV} is not set. This ladder needs a Gemini API key '
              f'(paid; see {PRICING_URL}). Set it on this computer only; never write it in a file.', file=sys.stderr)
        return 1
    try:
        import PIL  # noqa: F401
    except ImportError:
        print('error: Pillow is not installed (python -m pip install pillow)', file=sys.stderr)
        return 1

    made, failed, as_candidate = [], [], []
    for n in numbers:
        refs, errors, _ = references(choice, prompts, pictures, n)
        if errors:                                             # over the limit, now that a slide of this run was made
            print(f'slide {n}: failed: ' + '; '.join(errors), file=sys.stderr)
            failed.append(n)
            continue
        out = output_path(pictures, n)
        print(f'slide {n}: asking {args.model} ({describe(refs)}) ...')
        try:
            image = tidy(request_image(key, args.model, request_body(full_prompt(prompts, n), refs)))
        except Exception as e:                                 # one failed slide does not stop the others
            message = str(e).replace(key, '***')
            print(f'slide {n}: failed: {message}', file=sys.stderr)
            failed.append(n)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out, optimize=True)
        if out.parent.name == CANDIDATES:
            as_candidate.append(n)
        print(f'slide {n}: wrote {out} ({image.width}x{image.height}, {image.mode})')
        for warning in picture_warnings(image):
            print(f'warning: slide {n}: {warning}', file=sys.stderr)
        made.append(n)

    if made:
        print('\nNow look at each new picture. Check what the narration says about it, and write what you see '
              'on its "Seen:" line:')
        for n in made:
            print(f'  slide {n}: ' + (prompts.asserts.get(n) or '(no "Asserts:" line; does the narration say anything '
                                                                'about this picture?)'))
        if as_candidate:
            print('Candidates are not used until you choose one: --use N (the newest) or --use N-K.')
    if failed:
        print(f'{len(failed)} failed: ' + ' '.join(map(str, failed)) + ' (run again with these numbers)',
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
