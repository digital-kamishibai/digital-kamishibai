#!/usr/bin/env python3
"""Build a work folder's work.json from its script.md.

    python build_work.py <work folder>              # reads script.md, writes work.json next to it
    python build_work.py <work folder> --check      # checks only; writes nothing
    python build_work.py <work folder> --media DIR  # pictures, music and videos live in DIR
    python build_work.py <work folder> --draft      # a version for practising and correcting in the player
    python build_work.py <work folder> --skip-text  # leave the words on the screen ([Text]) out

A [Video] may be a YouTube link instead of a file (`> [Video] https://youtu.be/<id> start 5:51 end 6:09`, §2.4):
nothing is checked in the media folder for it, and each device plays it from YouTube.

The format is defined in docs/work-format.md of the Digital Kamishibai repository (§2 script.md, §3 work.json,
§5 checks). This file follows it and nothing else. Standard library only.

Exit code 0: work.json written (warnings may have been printed). Exit code 1: errors; nothing written.

Words on the screen ([Text], §2.6) are drawn into pictures/_built/NN.jpg by a headless Microsoft Edge or Google
Chrome (burn.py), with the room player's own drawing code. The original pictures are never changed.

With --draft, a [Video] that is the output of the work's ending video (ending_video*.json, made with the ladder)
gets role "ending" and its seats (§3.3), so the narrator can point at a seat while practising (§6 ending seat N).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import burn  # noqa: E402  (burn.py, next to this file)

FORMAT = 'digital-kamishibai/work'
VERSION = 1

PICTURE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')
HEIC_EXTS = ('.heic', '.heif')
AUDIO_EXTS = ('.mp3', '.m4a')
VIDEO_EXTS = ('.mp4',)
VIDEO_MAX_BYTES = 300 * 1024 * 1024
WORK_VIDEO_MAX_BYTES = 1024 * 1024 * 1024

CUE_KEYWORDS = ('Picture', 'Text', 'BGM', 'BGM once', 'BGM after video', 'BGM stop', 'Sound', 'Video')
BGM_KEYWORDS = ('BGM', 'BGM once', 'BGM after video', 'BGM stop')

# a linked video (§2.4): a YouTube link instead of a file, with the stretch to play
YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com',
                 'youtu.be'}
YOUTUBE_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
# [0-9], not \d: \d also reads full-width digits, and the player's reader (script.js) does not
SECONDS = re.compile(r'^(?:(?:([0-9]+):)?([0-9]+):)?([0-9]+(?:\.[0-9]+)?)$')         # 351, 351.5, 5:51, 1:05:51
LINK_TIME = re.compile(r'^(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+(?:\.[0-9]+)?)s?)?$')  # t=351, t=351s, t=5m51s
LINK = re.compile(r'^https?://', re.IGNORECASE)
CAPTIONS = re.compile(r'^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$')       # ja, en, pt-BR
VOLUME = re.compile(r'^([+-]?[0-9]+(?:\.[0-9]+)?)dB$', re.IGNORECASE)      # -6dB (a linked video, §2.4)
MIN_VOLUME_DB = -40                                                  # the player's lower end (ytlink.js)

HEADING = re.compile(r'^## \[Slide ([0-9]+)\][ \t]*(.*?)[ \t]*$')
NEAR_HEADING = re.compile(r'^##\s*\[')              # looks like a slide heading but is not one
TITLE = re.compile(r'^# (.+?)[ \t]*$')
LANGUAGE = re.compile(r'^>[ \t]*Language:[ \t]*(\S+)[ \t]*$')
CUE = re.compile(r'^>[ \t]*\[([^\]]+)\][ \t]*(.*?)[ \t]*$')
# a hole's narration (§2.3): read aloud, the maker may replace it. "~ ", or a numbered hole "~N " (N from 1 to 99)
HOLE_MARK = re.compile(r'^~([0-9]*) ')
HOLE_NUMBER = re.compile(r'^[1-9][0-9]?$')
# a full-width tilde or wave dash and a space, "~" with no space, or "~" and digits with no space (full-width digits too)
NEAR_HOLE = re.compile(r'^(?:[～〜][ \t　]|~(?=[^ ~0-9])|~[0-9]+(?![ 0-9]))')

TEXT_LENGTH = re.compile(r'^[0-9]+(\.[0-9]{1,2})?in$')
TEXT_SIZE = re.compile(r'^[0-9]+pt$')
TEXT_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')
EMU_PER_IN = 914400
SLIDE_SIZE = {'width': 12192000, 'height': 6858000}          # 16:9, 13.333 x 7.5 in
INSET = [91440, 45720, 91440, 45720]                          # 0.10 / 0.05 in
PLACES = {'top': 0.30, 'middle': 3.15, 'bottom': 6.00}        # bands: left 0.50, width 12.33, height 1.20
FONTS = {'ja': 'Meiryo', 'ko': 'Malgun Gothic', 'zh': 'Microsoft YaHei'}
DEFAULT_FONT = 'Arial'
BUILT = 'pictures/_built'

TEXT_CHOICES = {
    'place': ('top', 'middle', 'bottom'),
    'align': ('left', 'center', 'right'),
    'anchor': ('top', 'middle', 'bottom'),
}


@dataclass
class Line:
    number: int          # 1-based line number in script.md
    text: str            # the line with production notes removed
    had_note: bool       # a production note was removed from this line
    only_note: bool      # the line held nothing but production notes (and spaces)


@dataclass
class Result:
    work: dict | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # the same errors and warnings as short codes with where they are ("slide-numbers", "cue-unknown line 7"):
    # the room player reads a pasted script.md with the same codes (docs/work-format.md §2.7, tests/golden/)
    error_codes: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)

    def error(self, code: str, at: str, text: str) -> None:
        self.errors.append(f'{at}: {text}' if at else text)
        self.error_codes.append(f'{code} {at}' if at else code)

    def warn(self, code: str, at: str, text: str) -> None:
        self.warnings.append(f'{at}: {text}' if at else text)
        self.warning_codes.append(f'{code} {at}' if at else code)


# ---------- reading ----------

def strip_notes(source: str, result: Result) -> list[Line]:
    """Split into lines and remove production notes (<!-- ... -->), remembering where they were."""
    lines: list[Line] = []
    inside = False
    opened_at = 0
    for number, raw in enumerate(source.split('\n'), 1):
        out, had, pos = [], False, 0
        while pos <= len(raw):
            if inside:
                end = raw.find('-->', pos)
                had = True
                if end < 0:
                    pos = len(raw) + 1
                else:
                    inside = False
                    pos = end + 3
            else:
                start = raw.find('<!--', pos)
                if start < 0:
                    out.append(raw[pos:])
                    break
                out.append(raw[pos:start])
                inside, had, opened_at = True, True, number
                pos = start + 4
        text = ''.join(out)
        lines.append(Line(number, text, had, had and text.strip() == ''))
    if inside:
        result.error('note-open', f'line {opened_at}', f'"<!--" is never closed with "-->" '
                             '(everything after it would vanish from the narrator\'s screen)')
    return lines


def parse_text_attrs(rest: str, where: str, result: Result) -> dict:
    words = rest.split()
    attrs: dict = {}
    i = 0
    while i < len(words):
        key = words[i]
        if key == 'bold':
            value, i = True, i + 1
        elif key in ('place', 'align', 'anchor', 'left', 'top', 'width', 'height', 'size', 'color', 'fill'):
            if i + 1 >= len(words):
                result.error('text-no-value', where, f'[Text] "{key}" needs a value')
                break
            value, i = words[i + 1], i + 2
            ok = (value in TEXT_CHOICES[key] if key in TEXT_CHOICES
                  else TEXT_LENGTH.match(value) if key in ('left', 'top', 'width', 'height')
                  else TEXT_SIZE.match(value) if key == 'size'
                  else TEXT_COLOR.match(value))
            if not ok:
                result.error('text-bad-value', where, f'[Text] "{key} {value}" is not a value it takes')
        else:
            result.error('text-unknown-word', where, f'[Text] unknown word "{key}" (do not translate the words on a [Text] line)')
            i += 1
            continue
        if key in attrs:
            result.error('text-twice', where, f'[Text] "{key}" is written twice')
        attrs[key] = value
    lengths = [k for k in ('left', 'top', 'width', 'height') if k in attrs]
    if 'place' in attrs and lengths:
        result.error('text-place-and-box', where, f'[Text] write either "place" or left/top/width/height, not both')
    elif 'place' not in attrs and len(lengths) != 4:
        if lengths:
            missing = ', '.join(k for k in ('left', 'top', 'width', 'height') if k not in attrs)
            result.error('text-box-partial', where, f'[Text] needs all four of left/top/width/height (missing: {missing})')
        else:
            result.error('text-no-box', where, f'[Text] needs "place top|middle|bottom" or left/top/width/height')
    return attrs


def read_slide(number: int, title: str, body: list[Line], result: Result) -> dict:
    where = f'slide {number}'
    notes: list[str] = []
    removed = any(line.had_note for line in body)
    cues: list[dict] = []
    pictures: list[str] = []
    bgm_count = 0
    texts: list[dict] = []

    kept = [line for line in body if not line.only_note]
    para_mark: tuple[str, int] | None = None     # the mark of the paragraph so far, and its line (§2.3)
    i = 0
    while i < len(kept):
        line = kept[i]
        if not line.text.startswith('>'):
            mark = HOLE_MARK.match(line.text)
            if not line.text.strip():
                para_mark = None
            if mark:
                digits = mark.group(1)
                if digits and not HOLE_NUMBER.match(digits):
                    result.error('hole-number', f'line {line.number}', f'"~{digits} " is not a hole number '
                                 '(write ~1 to ~99 with no leading zero, or "~ " for a hole with no number)')
                elif para_mark and para_mark[0] != digits:
                    result.error('hole-mixed', f'line {line.number}', f'the mark "~{digits} " is not the mark '
                                 f'"~{para_mark[0]} " of line {para_mark[1]} in the same paragraph (a paragraph is one hole)')
                elif not para_mark:
                    para_mark = (digits, line.number)
                if not line.text[mark.end():].strip():
                    result.warn('hole-empty', f'line {line.number}',
                                f'"~{digits} " (the mark of a hole\'s narration) with no words after it')
            elif NEAR_HOLE.match(line.text):
                result.warn('hole-near', f'line {line.number}', f'looks like the mark of a hole\'s narration, but the mark is '
                                       '"~ " (a half-width tilde and a space). As written, it is read as plain narration')
            notes.append(line.text)
            i += 1
            continue
        block = [line]
        para_mark = None
        i += 1
        while i < len(kept) and kept[i].text.startswith('>'):
            block.append(kept[i])
            i += 1
        first = CUE.match(block[0].text)
        if not first:                                           # a free cue: shown to the narrator
            for later in block[1:]:
                m = CUE.match(later.text)
                if m and m.group(1) in CUE_KEYWORDS:
                    result.error('cue-in-free-cue', f'line {later.number}', f'[{m.group(1)}] is inside a free cue that starts on '
                                         f'line {block[0].number}, so it would do nothing. Put a blank line before it')
            notes.extend(b.text for b in block)
            continue
        removed = True
        if first.group(1) == 'Text':
            words = [re.sub(r'^> ?', '', b.text) for b in block[1:]]
            attrs = parse_text_attrs(first.group(2), f'line {block[0].number}', result)
            for b, w in zip(block[1:], words):
                m = CUE.match(b.text)
                if m and m.group(1) in CUE_KEYWORDS:
                    result.error('cue-in-text-words', f'line {b.number}', f'[{m.group(1)}] is read as words of the [Text] on line '
                                         f'{block[0].number}. Put a blank line after the words')
            if not any(w.strip() for w in words):
                result.error('text-no-words', f'line {block[0].number}', f'[Text] has no words (write them on the ">" lines after it)')
            texts.append({'attrs': attrs, 'words': words})
            continue
        for b in block:
            m = CUE.match(b.text)
            if not m:
                result.error('cue-block-mixed', f'line {b.number}', f'not a machine cue, but inside the cue block that starts on line '
                                     f'{block[0].number}. Put a blank line between them')
                continue
            keyword, arg = m.group(1), m.group(2)
            if keyword not in CUE_KEYWORDS:
                result.error('cue-unknown', f'line {b.number}', f'unknown cue "[{keyword}]" (known: '
                                     + ', '.join(f'[{k}]' for k in CUE_KEYWORDS) + '. Do not translate them)')
                continue
            if keyword == 'Text':
                result.error('text-not-first', f'line {b.number}', f'[Text] must start its own block. Put a blank line before it')
                continue
            if keyword == 'BGM stop':
                if arg:
                    result.error('bgm-stop-file', f'line {b.number}', f'[BGM stop] takes no file')
            elif not arg:
                result.error('cue-no-file', f'line {b.number}', f'[{keyword}] needs a file path')
                continue
            elif '\\' in arg:
                result.error('path-backslash', f'line {b.number}', f'use "/" in paths, not "\\": {arg}')
            if keyword == 'Picture':
                pictures.append(arg)
            elif keyword in BGM_KEYWORDS:
                bgm_count += 1
                cues.append({'type': 'bgm-stop'} if keyword == 'BGM stop'
                            else {'type': 'bgm', 'file': arg, 'loop': False} if keyword == 'BGM once'
                            else {'type': 'bgm', 'file': arg, 'loop': False, 'start': 'after-video'}
                            if keyword == 'BGM after video'
                            else {'type': 'bgm', 'file': arg})
            elif keyword == 'Video' and LINK.match(arg):
                cue = link_cue(arg, b.number, result)
                if cue:
                    cues.append(cue)
            else:
                cues.append({'type': keyword.lower(), 'file': arg})
    if len(pictures) > 1:
        result.error('picture-twice', where, f'more than one [Picture]')
    if bgm_count > 1:
        result.error('bgm-twice', where, f'more than one of [BGM] / [BGM once] / [BGM after video] / [BGM stop]')
    if (any(c.get('start') == 'after-video' for c in cues)
            and not any(c['type'] == 'video' for c in cues)):
        result.error('bgm-after-no-video', where, f'[BGM after video] needs a [Video] on the same slide')

    return {'number': number, 'title': title, 'picture': pictures[0] if pictures else None,
            'notes': make_notes(notes, removed), 'cues': cues, '_texts': texts}


def youtube_id(url: str) -> str | None:
    """The 11-character id of a YouTube link (watch?v=, youtu.be/, embed/, shorts/, live/), or None.
    The room player reads links the same way (player/js/ytlink.js youtubeId)."""
    try:
        u = urlsplit(url)
        host = (u.hostname or '').lower()
    except ValueError:
        return None
    if u.scheme not in ('http', 'https') or host not in YOUTUBE_HOSTS:
        return None
    parts = [p for p in u.path.split('/') if p]
    if host == 'youtu.be':
        vid = parts[0] if parts else None
    elif parts[:1] == ['watch']:
        vid = (parse_qs(u.query).get('v') or [None])[0]
    elif parts[:1] and parts[0] in ('embed', 'shorts', 'live', 'v') and len(parts) > 1:
        vid = parts[1]
    else:
        vid = None
    return vid if vid and YOUTUBE_ID.match(vid) else None


def seconds(text: str) -> float | None:
    """351 / 351.5 / 5:51 / 1:05:51 -> seconds, or None."""
    m = SECONDS.match(text)
    if not m:
        return None
    h, mi, sec = m.group(1), m.group(2), float(m.group(3))
    if (mi is not None and sec >= 60) or (h is not None and int(mi) >= 60):
        return None
    return int(h or 0) * 3600 + int(mi or 0) * 60 + sec


def link_seconds(text: str) -> float | None:
    """t=351 / t=351s / t=5m51s / start=351 in a link -> seconds, or None."""
    m = LINK_TIME.match(text)
    if not m or not text:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)


def plain(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 3)


def link_cue(arg: str, line: int, result: Result) -> dict | None:
    """`[Video] <YouTube link> start 5:51 end 6:09 captions ja volume -6dB`
    -> {'type': 'video', 'url', 'start', 'end', 'captions', 'volume'} (§2.4).
    start and end may also come from the link itself (t=, start=, end=), but not from both."""
    words = arg.split()
    url, rest = words[0], words[1:]
    vid = youtube_id(url)
    if not vid:
        result.error('link-not-youtube', f'line {line}', f'[Video] can play a YouTube link only (got {url}). '
                             'For another video, save it as MP4 and write its path')
        return None
    said: dict[str, float] = {}
    if len(rest) % 2:
        result.error('link-words', f'line {line}', f'after the link, [Video] takes "start <time>", "end <time>", '
                             f'"captions <language>" and "volume <dB>" (got: {" ".join(rest)})')
        return None
    captions = None
    volume = None
    for key, value in zip(rest[::2], rest[1::2]):
        if (key not in ('start', 'end', 'captions', 'volume') or key in said
                or (key == 'captions' and captions) or (key == 'volume' and volume is not None)):
            result.error('link-word', f'line {line}', f'after the link, [Video] takes "start <time>", "end <time>", '
                                 f'"captions <language>" and "volume <dB>", once each (got "{key}")')
            return None
        if key == 'volume':
            m = VOLUME.match(value)
            db = float(m.group(1)) if m else None
            if db is None or db > 0 or db < MIN_VOLUME_DB:
                result.error('link-volume', f'line {line}', f'volume {value} is not a volume. Write how much quieter, in dB, '
                                     f'from 0dB to {MIN_VOLUME_DB}dB, like -6dB (a linked video cannot be made louder)')
                return None
            volume = db
            continue
        if key == 'captions':
            if not CAPTIONS.match(value):
                result.error('link-captions', f'line {line}', f'captions {value} is not a language (write a code, like ja or en)')
                return None
            captions = value
            continue
        sec = seconds(value)
        if sec is None:
            result.error('link-time', f'line {line}', f'{key} {value} is not a time (write seconds, like 351, or m:ss, like 5:51)')
            return None
        said[key] = sec
    query = parse_qs(urlsplit(url).query)
    in_link: dict[str, float] = {}
    for key, names in (('start', ('start', 't')), ('end', ('end',))):
        for name in names:
            if name in query:
                sec = link_seconds(query[name][0])
                if sec is None:
                    result.error('link-time-in-link', f'line {line}', f'{name}={query[name][0]} in the link is not a time')
                    return None
                in_link[key] = sec
    both = set(said) & set(in_link)
    if both:
        result.error('link-time-twice', f'line {line}', f'[Video] has {" and ".join(sorted(both))} both in the link and after it. '
                             'Write it once (after the link is easier to read)')
        return None
    cut = {**in_link, **said}
    if 'end' in cut and cut['end'] <= cut.get('start', 0):
        result.error('link-end-before-start', f'line {line}', f'[Video] end must come after start')
        return None
    cue = {'type': 'video', 'url': f'https://www.youtube.com/watch?v={vid}'}
    if cut.get('start'):
        cue['start'] = plain(cut['start'])
    if 'end' in cut:
        cue['end'] = plain(cut['end'])
    if captions:
        cue['captions'] = captions
    if volume:
        cue['volume'] = plain(volume)
    return cue


def text_box(attrs: dict, words: list[str], language: str) -> tuple[list, dict]:
    """A [Text] block -> (its overlays entry: paragraphs -> lines, its overlay_layout entry). §2.6."""
    lines = list(words)
    while lines and lines[0].strip() == '':
        lines.pop(0)
    while lines and lines[-1].strip() == '':
        lines.pop()
    paragraphs = [p.split('\n') for p in '\n'.join(lines).split('\n\n')]

    def emu(value: str) -> int:
        return round(float(value[:-2]) * EMU_PER_IN)

    if 'place' in attrs:
        x, y, w, h = (round(0.50 * EMU_PER_IN), round(PLACES[attrs['place']] * EMU_PER_IN),
                      round(12.33 * EMU_PER_IN), round(1.20 * EMU_PER_IN))
    else:
        x, y, w, h = (emu(attrs[k]) for k in ('left', 'top', 'width', 'height'))
    style = {'align': attrs.get('align', 'center'), 'space_before': 0, 'size': int(attrs.get('size', '40pt')[:-2]),
             'bold': bool(attrs.get('bold')), 'color': attrs.get('color', '#000000').upper(),
             'font': FONTS.get(language.split('-')[0].lower(), DEFAULT_FONT)}
    box = {'x': x, 'y': y, 'width': w, 'height': h, 'inset': list(INSET), 'anchor': attrs.get('anchor', 'middle'),
           'wrap': True}
    if 'fill' in attrs:
        box['fill'] = attrs['fill'].upper()
    box['paragraphs'] = [dict(style) for _ in paragraphs]
    return paragraphs, box


def make_notes(lines: list[str], removed: bool) -> str:
    """§3.2: bold marks off; blank runs folded only if something was removed; blank ends trimmed."""
    lines = [line.replace('**', '') for line in lines]
    if removed:
        folded: list[str] = []
        for line in lines:
            if line.strip() == '' and folded and folded[-1].strip() == '':
                continue
            folded.append(line)
        lines = folded
    while lines and lines[0].strip() == '':
        lines.pop(0)
    while lines and lines[-1].strip() == '':
        lines.pop()
    return '\n'.join(lines)


def guess_language(text: str) -> str:
    if re.search(r'[぀-ヿ]', text):
        return 'ja'
    if re.search(r'[가-힯]', text):
        return 'ko'
    if re.search(r'[一-鿿]', text):
        return 'zh'
    return 'en'


def parse_script(source: str, result: Result) -> dict | None:
    source = source.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')
    lines = strip_notes(source, result)

    starts = []
    for index, line in enumerate(lines):
        if line.only_note:
            continue
        m = HEADING.match(line.text)
        if m:
            starts.append((index, int(m.group(1)), m.group(2)))
        elif NEAR_HEADING.match(line.text):
            result.error('heading-near', f'line {line.number}', f'looks like a slide heading but is not "## [Slide N] Title" '
                                 '(the marker [Slide N] is never translated)')
    if not starts:
        result.error('no-slides', '', 'no slide headings ("## [Slide 1] Title") were found; nothing to build')
        return None

    header = lines[:starts[0][0]]
    title = next((m.group(1) for line in header if (m := TITLE.match(line.text))), None)
    if title is None:
        result.error('no-title', '', 'the script has no title ("# Title" before the first slide)')
    language = next((m.group(1) for line in header if (m := LANGUAGE.match(line.text))), None)

    numbers = [n for _, n, _ in starts]
    if numbers != list(range(1, len(numbers) + 1)):
        result.error('slide-numbers', '', 'slide numbers must be 1, 2, 3, ... with no gaps or repeats; found '
                             + ', '.join(map(str, numbers)))

    slides = []
    for k, (index, number, slide_title) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = lines[index + 1:end]
        cut = next((j for j, line in enumerate(body) if line.text == '---' and not line.had_note), None)
        if cut is not None:
            after = [line for line in body[cut + 1:] if line.text.strip() and not line.only_note]
            if after:
                result.warn('after-end', f'line {after[0].number}', f'text after "---" of slide {number} is ignored')
            body = body[:cut]
        slides.append(read_slide(number, slide_title, body, result))

    if language is None:
        language = guess_language('\n'.join(s['notes'] for s in slides))
        result.warn('no-language', '', f'no "> Language:" line in the header; guessed "{language}"')

    return {'format': FORMAT, 'version': VERSION, 'title': title or '', 'language': language, 'slides': slides}


# ---------- media ----------

def default_picture(number: int) -> str:
    return f'pictures/{number:02d}.jpg'


def same_name_pictures(media: Path, picture: str) -> list[str]:
    """Other pictures with the same name and another extension (pictures/02.png beside pictures/02.jpg)."""
    path = Path(picture)
    return [path.with_suffix(ext).as_posix() for ext in PICTURE_EXTS
            if ext != path.suffix.lower() and (media / path.with_suffix(ext)).is_file()]


def resolve_media(work: dict, media: Path | None, result: Result) -> None:
    video_total = 0
    for slide in work['slides']:
        where = f'slide {slide["number"]}'
        has_video = any(c['type'] == 'video' for c in slide['cues'])
        if slide['picture'] is None:
            base = default_picture(slide['number'])
            found = None
            if media is not None:
                stem = base[:-len('.jpg')]
                for ext in PICTURE_EXTS + HEIC_EXTS:
                    if (media / (stem + ext)).is_file():
                        found = stem + ext
                        break
            if found:
                slide['picture'] = found
            elif has_video and media is not None:
                slide['picture'] = None          # the player shows the video's first frame
            else:
                slide['picture'] = base
                if media is not None:
                    result.warnings.append(f'{where}: picture not found: {base} (or .jpeg/.png/.webp)')
        else:
            if media is not None and not (media / slide['picture']).is_file():
                others = same_name_pictures(media, slide['picture'])
                result.warnings.append(f'{where}: picture not found: {slide["picture"]}'
                                       + (f' ({others[0]} is there: write "> [Picture] {others[0]}")' if others else ''))
        picture = slide['picture']
        if picture and media is not None and (media / picture).is_file():
            # a new picture saved next to the old one under another extension (a chat AI's PNG beside a sample's
            # JPEG) would otherwise be left out without a word
            for other in same_name_pictures(media, picture):
                result.warnings.append(f'{where}: shows {picture}, but {other} is there too (to show it, write '
                                       f'"> [Picture] {other}" or move {picture} out of the folder)')
        if picture:
            ext = Path(picture).suffix.lower()
            if ext in HEIC_EXTS:
                result.error('picture-heic', where, f'{picture} is HEIC, which players cannot show. Export it as JPEG')
            elif ext not in PICTURE_EXTS:
                result.warn('picture-format', where, f'{picture} is not JPEG, PNG or WebP')

        for cue in slide['cues']:
            file = cue.get('file')
            if not file:
                continue
            ext = Path(file).suffix.lower()
            if cue['type'] == 'video' and ext not in VIDEO_EXTS:
                result.warn('video-format', where, f'{file} is not MP4 (H.264 + AAC); listeners will not receive it')
            if cue['type'] in ('bgm', 'sound') and ext not in AUDIO_EXTS:
                result.warn('audio-format', where, f'{file} is not MP3 or AAC (.m4a)')
            if media is None:
                continue
            path = media / file
            if not path.is_file():
                result.warnings.append(f'{where}: file not found: {file}')
                continue
            if cue['type'] == 'video':
                size = path.stat().st_size
                video_total += size
                if size > VIDEO_MAX_BYTES:
                    result.warnings.append(f'{where}: {file} is {size / 1024 / 1024:.0f} MB, over 300 MB; '
                                           'export a lighter copy (720p or 1080p)')
    if video_total > WORK_VIDEO_MAX_BYTES:
        result.warnings.append(f'videos add up to {video_total / 1024 / 1024:.0f} MB, over 1 GB for one work')


# ---------- ending video seats (§3.3) ----------

ENDING_DEFINITIONS = 'ending_video*.json'


def ending_seats(folder: Path | None, result: Result) -> dict[str, list[dict]]:
    """videos/<output> → seats, from the ending video definitions in the work folder (the ladder's format:
    an optional prologue, then frames with at/dur on the song). Seconds are from the start of the video file.
    The cross-fade from seat k into seat k+1 runs from at_(k+1) for xfade_k seconds (the ladder's xfade_offsets);
    it is split at its middle, so a seat is where its own picture is the one mostly seen."""
    out: dict[str, list[dict]] = {}
    if folder is None:
        return out
    for path in sorted(folder.glob(ENDING_DEFINITIONS)):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            head = float(data['prologue']['dur']) if data.get('prologue') else 0.0
            frames = data['frames']
            seats = []
            for k, f in enumerate(frames, 1):
                if f.get('i', k) != k:           # the seat numbers of the storyboard and of `--replace N`
                    raise ValueError(f'seat {k} is numbered {f.get("i")!r}')
                fade_in = float(frames[k - 2].get('xfade', 0) or 0) / 2 if k > 1 else 0.0
                fade_out = float(f.get('xfade', 0) or 0) / 2 if k < len(frames) else 0.0
                start = head + float(f['at'])
                seat = {'n': k, 'from': round(start + fade_in, 3), 'to': round(start + float(f['dur']) + fade_out, 3)}
                if f.get('src'):
                    seat['label'] = str(f['src'])
                if f.get('pin'):
                    seat['pin'] = str(f['pin'])
                seats.append(seat)
            output = data['output']
        except (OSError, ValueError, KeyError, TypeError) as e:
            result.warnings.append(f'{path.name}: cannot read the seats of the ending video ({e}); '
                                   'its seats are left out')
            continue
        if not seats or any(b['from'] < a['to'] - 1e-6 or b['from'] >= b['to'] for a, b in zip(seats, seats[1:])):
            result.warnings.append(f'{path.name}: the seats are not in order on the song; its seats are left out')
            continue
        out[f'videos/{output}'] = seats
    return out


def check_ending_sources(folder: Path | None, result: Result) -> None:
    """Warn about seats of the ending videos whose picture or video in the work folder is not there any more —
    for example a slide's picture that a chosen candidate replaced (it moved to pictures/_replaced/). The video then
    still shows the old picture, and building it again stops. Seats in a photo folder elsewhere are not looked at
    (it may be on another computer). Unreadable definitions are left to ending_seats and the ladder's --check."""
    if folder is None:
        return
    for path in sorted(folder.glob(ENDING_DEFINITIONS)):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            frames = [f for f in data['frames'] if f.get('src') and (f.get('root') == 'work' or not data.get('photo_root'))]
            name = path.name
            opt = f'--config {name[len("ending_video_"):-len(".json")]} ' if name.startswith('ending_video_') else ''
            for f in frames:
                src = str(f['src']).replace('\\', '/')
                if (folder / src).is_file():
                    continue
                same = sorted(p for p in (folder / src).parent.glob(Path(src).stem + '.*')
                              if p.suffix.lower() in PICTURE_EXTS) if (folder / src).parent.is_dir() else []
                new = same[0].relative_to(folder).as_posix() if same else 'FILE'
                result.warnings.append(f'{name}: seat {f["i"]} shows {src}, which is not there any more, so the ending '
                                       f'video still shows the old one. Ask the maker; to put {new} there: '
                                       f'build_ending_video.py <work folder> {opt}--replace {f["i"]}={new}')
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue


def add_seats(work: dict, folder: Path | None, result: Result) -> None:
    by_file = ending_seats(folder, result)
    for slide in work['slides']:
        for cue in slide['cues']:
            if cue['type'] == 'video' and cue.get('file') in by_file:
                cue['role'] = 'ending'
                cue['seats'] = by_file[cue['file']]


# ---------- building ----------

def add_text(work: dict, media: Path | None, draft: bool, renderer, result: Result) -> None:
    """Draw [Text] into pictures/_built/ (through renderer) and point the slides there. §2.6."""
    jobs = []
    for slide in work['slides']:
        texts = slide['_texts']
        if not texts:
            continue
        if slide['picture'] is None:
            result.errors.append(f'slide {slide["number"]}: [Text] needs a picture to draw on '
                                 '(this slide has only a video)')
            continue
        boxes = [text_box(t['attrs'], t['words'], work['language']) for t in texts]
        name = f'{BUILT}/{slide["number"]:02d}'
        picture = slide['picture'] if media is not None and (media / slide['picture']).is_file() else None
        jobs.append({'slide': slide, 'boxes': boxes, 'picture': picture, 'name': name})
    if not jobs or result.errors:
        return
    if media is None:
        result.errors.append('drawing words on the screen needs the media folder')
        return
    try:
        fits = renderer([{'picture': j['picture'], 'boxes': [{'box': b, 'words': w} for w, b in j['boxes']],
                   'out': media / (j['name'] + '.jpg'), 'base': media / (j['name'] + '.base.jpg') if draft else None}
                  for j in jobs], media)
    except Exception as e:                       # the browser, the page or the disk
        # a connection the system cut (an AI's sandbox can stop the browser): not the work's fault
        hint = ' (inside a sandbox the browser may be stopped: run this command outside it)' if isinstance(e, OSError) else ''
        result.errors.append(f'could not draw the words on the screen: {e}{hint}')
        return
    for j, fit in zip(jobs, fits or [[] for _ in jobs]):
        slide = j['slide']
        for k, f in enumerate(fit or [], 1):
            if f.get('off'):
                result.warnings.append(f'slide {slide["number"]}: the words of [Text] {k} run off the slide '
                                       '(make the box larger, the words smaller or fewer)')
            elif f.get('outside'):
                result.warnings.append(f'slide {slide["number"]}: the words of [Text] {k} run out of its colour band '
                                       '(make the box taller or the words smaller)')
        slide['picture'] = j['name'] + '.jpg'
        if draft:
            slide['overlays'] = [w for w, _ in j['boxes']]
            slide['overlay_layout'] = [b for _, b in j['boxes']]
            slide['overlay_base'] = j['name'] + '.base.jpg'
            if j['picture']:
                # the picture the words were drawn on: the player tells a new picture by this file, not by the
                # built one, which every build writes again (a picture correction must not look done after a rebuild)
                slide['picture_source'] = j['picture']


def build(source: str, media: Path | None = None, *, draft: bool = False, renderer=None,
          skip_text: bool = False, definitions: Path | None = None) -> Result:
    """Read script.md text; return work.json content (or errors). media: the folder the paths are relative to.
    renderer(jobs, media) draws the words on the screen (burn.render); without one, [Text] is an error
    unless skip_text. definitions: the work folder, where ending_video*.json lives (seats, only with draft)."""
    result = Result()
    work = parse_script(source, result)
    if work is None:
        return result
    resolve_media(work, media, result)
    with_text = [s['number'] for s in work['slides'] if s['_texts']]
    if with_text and skip_text:
        result.warnings.append('words on the screen ([Text]) on slide ' + ', '.join(map(str, with_text))
                               + ' are left out (--skip-text)')
    elif with_text and renderer is None:
        result.errors.append('words on the screen ([Text]) need Microsoft Edge or Google Chrome to be drawn; '
                             'install one, set DK_BROWSER to its path, or build with --skip-text')
    elif with_text and not result.errors:
        add_text(work, media, draft, renderer, result)
    check_ending_sources(definitions, result)
    if draft:
        add_seats(work, definitions, result)
        work = {**{k: work[k] for k in ('format', 'version', 'title', 'language')}, 'draft': True,
                'slide_size': dict(SLIDE_SIZE), 'slides': work['slides']}
    for slide in work['slides']:
        del slide['_texts']
    if not result.errors:
        result.work = work
    return result


def dump(work: dict) -> str:
    return json.dumps(work, ensure_ascii=False, indent=2) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build work.json from script.md (Digital Kamishibai).')
    parser.add_argument('folder', type=Path, help='the work folder that holds script.md')
    parser.add_argument('--media', type=Path, help='folder that holds the pictures, music and videos '
                                                   '(default: the work folder)')
    parser.add_argument('--check', action='store_true', help='check only; do not write work.json or pictures')
    parser.add_argument('--draft', action='store_true', help='a version for practising and correcting in the player')
    parser.add_argument('--skip-text', action='store_true', help='leave the words on the screen ([Text]) out')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # a Japanese Windows console cannot show every character
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')

    script = args.folder / 'script.md'
    if not script.is_file():
        print(f'error: {script} not found', file=sys.stderr)
        return 1
    media = args.media if args.media is not None else args.folder
    if not media.is_dir():
        print(f'error: media folder {media} not found', file=sys.stderr)
        return 1

    source = script.read_text(encoding='utf-8')
    renderer = None
    if not args.skip_text:
        executable = burn.find_browser()
        if executable and args.check:
            renderer = lambda jobs, folder: None                      # noqa: E731  (--check draws nothing)
        elif executable:
            renderer = lambda jobs, folder: burn.render(jobs, folder, executable)  # noqa: E731
    result = build(source, media, draft=args.draft, renderer=renderer, skip_text=args.skip_text,
                   definitions=args.folder)
    for warning in result.warnings:
        print(f'warning: {warning}', file=sys.stderr)
    for error in result.errors:
        print(f'error: {error}', file=sys.stderr)
    if result.errors:
        print(f'{len(result.errors)} error(s); work.json was not written', file=sys.stderr)
        return 1
    slides = len(result.work['slides'])
    if args.check:
        print(f'ok: {slides} slides (nothing written: --check)')
        return 0
    out = args.folder / 'work.json'
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(dump(result.work))
    print(f'wrote {out}: {slides} slides')
    return 0


if __name__ == '__main__':
    sys.exit(main())
