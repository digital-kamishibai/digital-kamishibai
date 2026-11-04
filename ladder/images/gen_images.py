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


@dataclass
class Prompts:
    style: str = ''
    slides: dict[int, str] = field(default_factory=dict)
    asserts: dict[int, str] = field(default_factory=dict)
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
        asserts, block, fence, done = '', [], '', False
        for row in body:                                   # only the first code block is the prompt
            if done:
                break
            if not fence:
                opened = FENCE.match(row)
                if opened:
                    fence = opened.group(1)
                elif ASSERTS.match(row) and not asserts:
                    asserts = ASSERTS.match(row).group(1)
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

def request_body(prompt: str, anchor: Path | None) -> dict:
    parts = []
    if anchor is not None:
        mime = 'image/png' if anchor.suffix.lower() == '.png' else (
            'image/webp' if anchor.suffix.lower() == '.webp' else 'image/jpeg')
        parts.append({'inline_data': {'mime_type': mime, 'data': base64.b64encode(anchor.read_bytes()).decode('ascii')}})
        parts.append({'text': STYLE_NOTE})
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


def anchor_for(pictures: Path, number: int, anchor: str) -> Path | None:
    if anchor == 'none':
        return None
    source = int(anchor)
    if source == number:
        return None
    return existing_picture(pictures, source)


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
    parser.add_argument('--anchor', default='1', help='slide whose picture sets the style (default 1), or "none"')
    parser.add_argument('--model', default=os.environ.get('DK_GEMINI_MODEL', MODEL), help=f'default {MODEL}')
    parser.add_argument('--dry-run', action='store_true', help='show what would be sent and the cost; send nothing')
    parser.add_argument('--use', metavar='N[-K]', help='put candidate K (default: the newest) in slide N\'s place')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # a Japanese Windows console cannot show every character
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')

    pictures = args.folder / 'pictures'
    if args.use:
        try:
            print(use_candidate(pictures, args.use))
        except ValueError as e:
            print(f'error: {e}', file=sys.stderr)
            return 1
        return 0
    if args.anchor != 'none' and not args.anchor.isdigit():
        print('error: --anchor takes a slide number or "none"', file=sys.stderr)
        return 1

    plan = args.plan if args.plan is not None else args.folder / 'plan.md'
    if not plan.is_file():
        print(f'error: {plan} not found', file=sys.stderr)
        return 1
    prompts = parse_plan(plan.read_text(encoding='utf-8'))
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
    # the style picture goes first, so that the others can follow it
    anchor_number = None if args.anchor == 'none' else int(args.anchor)
    if anchor_number in numbers:
        numbers = [anchor_number] + [n for n in numbers if n != anchor_number]
    print(cost_line(args.model, len(numbers)))

    if args.dry_run:
        for n in numbers:
            anchor = anchor_for(pictures, n, args.anchor)
            print(f'\n--- slide {n} -> {output_path(pictures, n)}'
                  f' (style from: {anchor if anchor else "nothing"})\n{full_prompt(prompts, n)}')
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
        anchor = anchor_for(pictures, n, args.anchor)
        out = output_path(pictures, n)
        print(f'slide {n}: asking {args.model}' + (f' (style from {anchor.name})' if anchor else '') + ' ...')
        try:
            image = tidy(request_image(key, args.model, request_body(full_prompt(prompts, n), anchor)))
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
