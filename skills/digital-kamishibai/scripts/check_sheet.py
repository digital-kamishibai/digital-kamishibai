#!/usr/bin/env python3
"""Check whether a correction sheet has been written back into script.md.

    python check_sheet.py <work folder> <correction sheet .md>

Reads the sheet (docs/work-format.md §6), builds the work from script.md in memory (as with --draft, without drawing
any picture), and judges every correction on the same slide by the same rules the room player uses when the work is
opened again (§6, the table at the end):

    done      — After is there (or, for a removal, Before is gone)
    reworded  — neither Before nor After is there (the writer changed it again; the narrator decides)
    pending   — Before is still there: not written back yet

Exit code 0 when nothing is pending, 1 otherwise (or on errors). Standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_work  # noqa: E402  (build_work.py, next to this file)

HEADING = re.compile(r'^## \[Slide (\d+)\] (?:(notes) (\d+)(?:-(\d+))?|(overlay|layout|video|ending seat) (\d+)|(comment|picture))[ \t]*$')
# Pictures and videos (work-format §6): the sheet says what to change and where; the maker chooses the new one.
MEDIA_KINDS = ('picture', 'video', 'ending seat')
MEDIA_LINE = re.compile(r'^(From|To|At|Label|Pin|Use) (.+?)[ \t]*$')
FENCE = re.compile(r'^(`{3,})[ \t]*$')
LAYOUT_LINE = re.compile(r'^(left|top|width|height) (-?\d+(?:\.\d+)?)in$|^size (\d+)pt$'
                         r'|^(color) (#[0-9A-Fa-f]{6})$|^(fill) (#[0-9A-Fa-f]{6}|none)$')
LAYOUT_KEYS = ('left', 'top', 'width', 'height', 'size', 'color', 'fill')
SPACES = '[ \t　]+$'


# ---------- reading the sheet ----------

def trim_ends(text: str) -> str:
    return '\n'.join(re.sub(SPACES, '', line) for line in text.split('\n'))


def paragraphs(text: str) -> list[str]:
    """Notes → paragraphs: separated by one or more blank lines (a line of spaces is blank)."""
    out, current = [], []
    for line in str(text or '').split('\n'):
        if re.fullmatch(r'[ \t　]*', line):
            if current:
                out.append('\n'.join(current))
                current = []
        else:
            current.append(re.sub(SPACES, '', line))
    if current:
        out.append('\n'.join(current))
    return out


def box_of(text: str) -> list[list[str]]:
    """Overlay text → paragraphs → lines (paragraphs are separated by exactly one blank line)."""
    if text == '':
        return []
    return [p.split('\n') for p in text.split('\n\n')]


def layout_of(text: str, where: str, errors: list[str]) -> dict:
    values = {}
    for line in text.split('\n'):
        if not line.strip():
            continue
        m = LAYOUT_LINE.match(line.strip())
        if not m:
            errors.append(f'{where}: not a layout line: {line!r}')
            continue
        if m.group(3) is not None:
            values['size'] = int(m.group(3))
        elif m.group(4) is not None:
            values['color'] = m.group(5).upper()
        elif m.group(6) is not None:
            values['fill'] = m.group(7) if m.group(7) == 'none' else m.group(7).upper()
        else:
            values[m.group(1)] = float(m.group(2))
    return values


def read_sheet(text: str) -> tuple[str | None, list[dict], list[str]]:
    """→ (title, items, errors). An item: slide, kind ('notes', 'overlay', 'layout', 'comment'), at, before, after, comment."""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿').split('\n')
    title = None
    m = re.match(r'^# Correction sheet: (.*) \(\d{4}-\d{2}-\d{2} \d{2}:\d{2}\)[ \t]*$', lines[0] if lines else '')
    errors = []
    if m:
        title = m.group(1)
    else:
        errors.append('the first line is not "# Correction sheet: <title> (YYYY-MM-DD hh:mm)"')
    items: list[dict] = []
    item = None
    i = 1
    while i < len(lines):
        line = lines[i]
        h = HEADING.match(line)
        if h:
            slide = int(h.group(1))
            if h.group(2):
                item = {'slide': slide, 'kind': 'notes', 'at': (int(h.group(3)), int(h.group(4) or h.group(3)))}
            elif h.group(5):
                item = {'slide': slide, 'kind': h.group(5), 'at': int(h.group(6))}
            else:
                item = {'slide': slide, 'kind': h.group(7), 'at': None}
            items.append(item)
            i += 1
            continue
        if line.startswith('## '):
            errors.append(f'line {i + 1}: not a correction heading: {line!r}')
            item = None
        elif line in ('### Before', '### After') and item is not None and i + 1 < len(lines):
            f = FENCE.match(lines[i + 1])
            if not f:
                errors.append(f'line {i + 2}: a fence of backticks should follow {line!r}')
                i += 1
                continue
            end = next((k for k in range(i + 2, len(lines)) if lines[k] == f.group(1)), None)
            if end is None:
                errors.append(f'line {i + 2}: the fence is never closed')
                break
            item['before' if line == '### Before' else 'after'] = '\n'.join(lines[i + 2:end])
            i = end + 1
            continue
        elif line.startswith('Comment:') and item is not None:
            item['comment'] = line[len('Comment:'):].strip()
        elif item is not None and item['kind'] in MEDIA_KINDS and (mm := MEDIA_LINE.match(line)):
            item.setdefault('media', {})[mm.group(1).lower()] = mm.group(2)   # not 'at': that is the heading's number
        i += 1

    for item in items:
        where = f'[Slide {item["slide"]}] {item["kind"]}'
        if item['kind'] == 'comment':
            continue
        if item['kind'] in MEDIA_KINDS:
            if item['kind'] == 'picture' and not item.get('comment') and 'use' not in item.get('media', {}):
                errors.append(f'{where}: a picture correction needs "Comment:" (what to change) or "Use" (the chosen candidate)')
            continue
        if 'before' not in item or 'after' not in item:
            errors.append(f'{where}: needs both "### Before" and "### After"')
            continue
        if item['kind'] == 'notes':
            item['before'], item['after'] = paragraphs(item['before']), paragraphs(item['after'])
        elif item['kind'] == 'overlay':
            item['before'], item['after'] = box_of(item['before']), box_of(item['after'])
        else:
            item['before'] = layout_of(item['before'], where, errors)
            item['after'] = layout_of(item['after'], where, errors)
    return title, items, errors


# ---------- judging (the player's rules, §6) ----------

def find_run(paras: list[str], seq: list[str]) -> int:
    if not seq:
        return 0
    for i in range(len(paras) - len(seq) + 1):
        if all(paras[i + k] == p for k, p in enumerate(seq)):
            return i
    return -1


def norm_box(box):
    return [[re.sub(SPACES, '', line) for line in para] for para in box or []]


def box_color(box: dict, words: list | None) -> str | None:
    """The colour of a box (§3.2): the colour of its paragraphs that have words. None when they differ."""
    def has(k):
        return words is None or any(line.strip() for line in (words[k] if k < len(words) else []))
    paras = [p for k, p in enumerate(box['paragraphs']) if has(k)] or box['paragraphs']
    colors = {str(p['color']).upper() for p in paras}
    return colors.pop() if len(colors) == 1 else None


def sheet_values(box: dict, words: list | None = None) -> dict:
    """A box of overlay_layout, as the sheet writes it. A box with no fill is 'fill none' (the only place this is decided)."""
    sizes = [p['size'] for p in box['paragraphs']]

    def inches(emu):
        return round(emu / 9144) / 100
    values = {'left': inches(box['x']), 'top': inches(box['y']), 'width': inches(box['width']),
              'height': inches(box['height']), 'size': round(max(sizes) if sizes else 18),
              'fill': box['fill'].upper() if box.get('fill') else 'none'}
    color = box_color(box, words)
    if color is not None:
        values['color'] = color
    return values


def judge(item: dict, slide: dict | None) -> str:
    if slide is None:
        return 'reworded'
    if item['kind'] == 'layout':
        boxes = slide.get('overlay_layout') or []
        if item['at'] > len(boxes):
            return 'reworded'
        words = (slide.get('overlays') or [])
        now = sheet_values(boxes[item['at'] - 1], words[item['at'] - 1] if item['at'] <= len(words) else None)
        keys = list(item['after'])
        if all(now.get(k) == item['after'][k] for k in keys):
            return 'done'
        if all(now.get(k) == item['before'].get(k) for k in keys):
            return 'pending'
        return 'reworded'

    def found(x):
        if item['kind'] == 'notes':
            return find_run([trim_ends(p) for p in paragraphs(slide['notes'])], [trim_ends(p) for p in x]) >= 0
        return any(norm_box(b) == norm_box(x) for b in slide.get('overlays') or [])

    if not item['after']:
        return 'pending' if item['before'] and found(item['before']) else 'done'
    if found(item['after']):
        return 'done'
    return 'pending' if found(item['before']) else 'reworded'


def seat_state(item: dict, slide: dict | None) -> str:
    """An ending seat (§6): 'changed' when the seat now holds another picture than its Label, else 'look'."""
    seats = next((c['seats'] for c in (slide or {}).get('cues', [])
                  if c.get('role') == 'ending' and c.get('seats')), None)
    if not seats:
        return 'changed'
    seat = next((t for t in seats if t['n'] == item['at']), None)
    label = (item.get('media') or {}).get('label')
    return 'changed' if seat is None or seat.get('label') != label else 'look'


def check(folder: Path, sheet_text: str, media: Path | None = None) -> tuple[list[tuple[dict, str]], list[str]]:
    """→ ([(item, 'done' | 'reworded' | 'pending' | 'comment' | 'look' | 'changed')], errors).
    'look': a picture or video correction — never judged from the sheet; the maker makes and chooses the new one.
    A picture with 'Use' (the maker chose a candidate): 'pending' while that candidate is still there (not used yet),
    'done' once it is gone (gen_images.py --use moved it into the slide's place).
    'changed': an ending seat whose picture (its Label) is not the one pointed at any more — look, then remove it"""
    title, items, errors = read_sheet(sheet_text)
    script = folder / 'script.md'
    if not script.is_file():
        return [], errors + [f'{script} not found']
    result = build_work.build(script.read_text(encoding='utf-8'), media if media is not None else folder,
                              draft=True, renderer=lambda jobs, m: None, definitions=folder)
    if result.errors:
        return [], errors + ['script.md does not build: ' + e for e in result.errors]
    work = result.work
    if title is not None and title != work['title']:
        errors.append(f'the sheet is for "{title}", but script.md is "{work["title"]}"')
    slides = {s['number']: s for s in work['slides']}
    def state(item):
        if item['kind'] == 'comment':
            return 'comment'
        if item['kind'] == 'ending seat':
            return seat_state(item, slides.get(item['slide']))
        if item['kind'] == 'picture' and 'use' in item.get('media', {}):
            use = item['media']['use']
            left = any((base / use).is_file() for base in (folder, media) if base is not None)
            return 'pending' if left else 'done'
        if item['kind'] in MEDIA_KINDS:
            return 'look'
        return judge(item, slides.get(item['slide']))
    return [(item, state(item)) for item in items], errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check that a correction sheet has been written back into script.md.')
    parser.add_argument('folder', type=Path, help='the work folder that holds script.md')
    parser.add_argument('sheet', type=Path, help='the correction sheet (.md) saved or copied from the room player')
    parser.add_argument('--media', type=Path, help='folder of the pictures, if not the work folder')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # a Japanese Windows console cannot show every character
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    if not args.sheet.is_file():
        print(f'error: {args.sheet} not found', file=sys.stderr)
        return 1
    judged, errors = check(args.folder, args.sheet.read_text(encoding='utf-8'), args.media)
    for e in errors:
        print(f'error: {e}', file=sys.stderr)
    labels = {'done': 'done     ', 'reworded': 'reworded ', 'pending': 'PENDING  ', 'comment': 'comment  ', 'look': 'look     ', 'changed': 'changed  '}
    for item, state in judged:
        at = item['at'] if item['kind'] != 'notes' else (
            f'{item["at"][0]}' if item['at'][0] == item['at'][1] else f'{item["at"][0]}-{item["at"][1]}')
        where = f'[Slide {item["slide"]}] {item["kind"]}' + (f' {at}' if at is not None else '')
        use = item.get('media', {}).get('use') if item['kind'] == 'picture' else None
        note = (f'  - use {use}' if use else '') + (f'  - {item["comment"]}' if item.get('comment') else '')
        print(f'{labels[state]} {where}{note}')
    pending = sum(1 for _, s in judged if s == 'pending')
    print(f'{len(judged)} item(s): {pending} pending')
    return 1 if errors or pending else 0


if __name__ == '__main__':
    sys.exit(main())
