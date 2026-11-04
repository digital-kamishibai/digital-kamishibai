#!/usr/bin/env python3
"""Build an ending video for a kamishibai: the family's photos and videos on one song.

    python build_ending_video.py <work folder>                       # build videos/<output>
    python build_ending_video.py <work folder> --init --audio sounds/song.mp3 --photos D:/Photos/family
    python build_ending_video.py <work folder> --check               # check the definition and the files
    python build_ending_video.py <work folder> --storyboard          # storyboard: a JPEG and a page to point at seats
    python build_ending_video.py <work folder> --replace 17=2016/bike.jpg --replace 3=clips/run.mp4@1.2
    python build_ending_video.py <work folder> --move 14=2           # the content of seat 14 goes after seat 2
    python build_ending_video.py <work folder> --sort 1-30 [--pin 7] # by date taken (pinned seats stay)
    python build_ending_video.py <work folder> --pin-set 42="the line of the chorus" | --unpin 42 | --pins
    python build_ending_video.py <work folder> --pick 1-10 | --confirm 1-22
    python build_ending_video.py <work folder> --config second       # a second ending video for the same work

This is a ladder: optional. It costs nothing, but needs Python 3.10+, Pillow and ffmpeg (with ffprobe) on the PATH.
See README.md next to this file.

The definition is <work>/ending_video.json. Its core rule: **the timeline is frozen first; only the content changes.**
Each seat has `at` (seconds from the start of the song) and `dur` (seconds on screen). Replacing, moving and sorting
change only what sits in a seat (`src`, `kind`, `status`, ...), never `at`/`dur`/`beat`/`xfade`/`zoom`/`pin`.
So a whole video can be built before the photos are chosen, and no change ever shifts a picture against the song.

Camera moves (zoom in, zoom out, `zoom_center`) are drawn one frame at a time by Pillow at sub-pixel positions.
ffmpeg's zoompan/crop can only place the window on whole pixels: a slow zoom then moves in visible steps ("judder"),
a few frames still and one frame jumping. Making the picture larger first does not help (measured: the rounding
happens on the input side). check_smoothness.py measures the finished video for this.

Nothing random is used: the same definition gives the same video. Video clips are always silent (the song is the
only sound), except the optional prologue and epilogue, which play a family video with its own sound before or after
the song, never on top of it.

The finished video is made playable in the room player (docs/work-format.md: at most 1080p and 300 MB per file):
its loudness is set to -22 LUFS, and a file over the limit is re-encoded in two passes to about 270 MB.

Files (all under the work folder; the photos stay wherever photo_root says):
    ending_video.json             the definition (keep it with the work)
    videos/<output>               the video, for the room player's [Video] cue
    ending/storyboard.jpg|.html   the storyboard (contains the family's photos: do not commit)
    ending/cache/                 segments and prepared pictures, reused when nothing changed
With --config NAME these become ending_video_NAME.json and ending_NAME/.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time

FPS = 30
OUT_W, OUT_H = 1920, 1080
# The room player's level for videos (the work's BGM sits lower, under the narration).
# -22, about as loud as the narrator's voice: at -16 a video played about 6 dB louder than the narration (2026-10-27).
LOUDNESS_TARGET_LUFS = -22.0
TRUE_PEAK_CEIL_DBTP = -1.5          # headroom for the AAC encoder's overshoot
LOUDNESS_TOLERANCE_LU = 0.5         # beyond this, add what the limiter took and try once more
# docs/work-format.md section 4 (counted in decimal megabytes, on the small side)
MAX_VIDEO_BYTES = 300 * 1000 * 1000
TARGET_VIDEO_BYTES = 270 * 1000 * 1000
AUDIO_BPS = 192 * 1000
MIN_VIDEO_BPS = 500 * 1000         # below this a 1080p picture of photos falls apart
# Pictures are prepared at 4K and cut down to 1080p: not to avoid judder (that is what sub-pixel drawing is for),
# but because shrinking a cropped window keeps more detail than cropping a 1080p picture.
BIG_W, BIG_H = 3840, 2160
ZOOM_MAX = 1.06                     # gentle; never make anyone seasick
BLUR_SIGMA = 30                     # the blurred background behind portrait photos
BG_DARKEN = 0.72                    # darken it so the photo stands out

# Labels on the storyboard can carry any script (file names, the work's language). Pillow's default font has no CJK
# glyphs and draws boxes, so look for a real font first.
LABEL_FONTS = (
    r'C:\Windows\Fonts\meiryo.ttc', r'C:\Windows\Fonts\YuGothR.ttc', r'C:\Windows\Fonts\msgothic.ttc',
    '/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc', '/System/Library/Fonts/Hiragino Sans GB.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
TITLE_FONTS = (
    r'C:\Windows\Fonts\meiryob.ttc', r'C:\Windows\Fonts\YuGothB.ttc', r'C:\Windows\Fonts\arialbd.ttf',
    '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc', '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', '/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
LABEL_PT = 13

PHOTO_EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
VIDEO_EXT = ('.mp4', '.mov', '.mts', '.m2ts', '.avi', '.3gp', '.mkv')
KINDS = ('photo', 'clip', 'final')
STATUSES = ('placeholder', 'picked', 'confirmed')
EASES = ('linear', 'out')           # one easing law for every move, so there is one way of stopping
# Kept in the seat, not in its content. `pin` too: a lyric is sung at the seat's second, so "do not move this"
# belongs to the seat, whatever picture sits in it.
SLOT_KEYS = ('i', 'at', 'dur', 'beat', 'xfade', 'zoom', 'pin', 'ease', 'zoom_from', 'zoom_center')
# Written in the definitions of the tool this ladder came from; not carried over (yet). Say so instead of ignoring.
NOT_SUPPORTED = {'pre_still': 'a still before the prologue', 'cover': 'an embedded cover picture'}
NOT_SUPPORTED_SEAT = {'layer': 'sliding bands', 'y0': 'tall-picture pans', 'y1': 'tall-picture pans'}

# a date in a file name: PXL_20240601_..., IMG_20160101_..., 2016-01-01_...
RE_FNAME_DATE = re.compile(r'(?<!\d)(19|20)(\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)')
RE_FNAME_TIME = re.compile(r'(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})')
RE_REPLACE = re.compile(r'^(\d+)=(.+)$')
RE_AT_SEC = re.compile(r'^(.*?)@(\d+(?:\.\d+)?)$')     # only for videos: 3=clips/run.mp4@1.2
RE_MOVE = re.compile(r'^(\d+)=(\d+)$')
RE_RANGE = re.compile(r'^(\d+)(?:-(\d+))?$')
RE_PIN = re.compile(r'^(\d+)=(.+)$')
RE_CONFIG = re.compile(r'^[A-Za-z0-9_-]{1,32}$')


class ConfigError(Exception):
    """Errors in the definition or the files; carries every message."""

    def __init__(self, messages):
        self.messages = list(messages)
        super().__init__('\n'.join(self.messages))


# A sync client (Dropbox, OneDrive) or a virus scanner can hold a file it has just seen for a moment, and Windows then
# refuses to rename onto it (PermissionError, WinError 5). Wait a little and try again before giving up.
REPLACE_WAITS = (0.5, 1.0, 2.0, 4.0)


def replace_file(src, dst):
    """os.replace that waits out a short lock. If the file stays locked, stop with words a maker can act on
    instead of a traceback (the parts already made are reused on the next run)."""
    for wait in REPLACE_WAITS + (None,):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if wait is None:
                break
            time.sleep(wait)
    raise ConfigError([f'another program is using {dst}',
                       '  (a sync folder such as Dropbox, or a virus scanner, often holds a new file for a moment).',
                       '  Wait a little and run the same command again: the parts already made are reused.'])


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ============================================================
# The definition (pure functions)
# ============================================================
def validate_config(data):
    """Return every error in the definition (empty when fine). Files are not looked at here (check_sources)."""
    if not isinstance(data, dict):
        return ['the top level is not an object']
    errors = []
    required = [
        ('audio', str, lambda v: bool(v), 'the song, relative to the work folder'),
        ('output', str, lambda v: v.endswith('.mp4') and '/' not in v and '\\' not in v,
         'a file name ending in .mp4 (written to videos/)'),
        ('duration_sec', (int, float), lambda v: v > 0, 'the length of the song in seconds'),
    ]
    if needs_photo_root(data):
        required.insert(0, ('photo_root', str, lambda v: bool(v),
                            'the folder the photos are taken from (absolute, or relative to the work folder)'))
    for key, types, cond, hint in required:
        if key not in data:
            errors.append(f'missing key {key} ({hint})')
        elif not isinstance(data[key], types) or isinstance(data[key], bool) or not cond(data[key]):
            errors.append(f'{key}={data[key]!r} is not valid ({hint})')
    if 'audio_sha256' in data and not (isinstance(data['audio_sha256'], str) and len(data['audio_sha256']) == 64):
        errors.append(f'audio_sha256={data["audio_sha256"]!r} is not valid (64 hex digits)')
    if 'audio_duration_sec' in data and not (is_num(data['audio_duration_sec']) and data['audio_duration_sec'] > 0):
        errors.append(f'audio_duration_sec={data["audio_duration_sec"]!r} is not valid (seconds)')
    for key, what in NOT_SUPPORTED.items():
        if key in data:
            errors.append(f'{key} ({what}) is not supported by this tool')
    errors += side_errors(data.get('prologue'), 'prologue')
    errors += side_errors(data.get('epilogue'), 'epilogue')
    errors += final_still_errors(data.get('final_still'))
    frames = data.get('frames')
    if not isinstance(frames, list) or not frames:
        errors.append('"frames" is empty: there are no seats')
        return errors

    seen_i = {}
    for idx, f in enumerate(frames, 1):
        where = f'frames[{idx}]'
        if not isinstance(f, dict):
            errors.append(f'{where}: not an object')
            continue
        for key, types, cond, hint in (
            ('i', int, lambda v: v >= 1, 'a seat number from 1 (used to point at the seat)'),
            ('at', (int, float), lambda v: v >= 0, 'seconds from the start of the song'),
            ('dur', (int, float), lambda v: v > 0, 'seconds on screen'),
            ('src', str, lambda v: bool(v), 'the picture or video'),
        ):
            if key not in f:
                errors.append(f'{where}: missing key {key} ({hint})')
            elif not isinstance(f[key], types) or isinstance(f[key], bool) or not cond(f[key]):
                errors.append(f'{where}: {key}={f[key]!r} is not valid ({hint})')
        for key, what in NOT_SUPPORTED_SEAT.items():
            if key in f:
                errors.append(f'{where}: {key} ({what}) is not supported by this tool')
        kind = f.get('kind', 'photo')
        if kind not in KINDS:
            errors.append(f'{where}: kind={kind!r} must be one of ' + '/'.join(KINDS))
        if kind == 'clip':
            cs = f.get('clip_start_sec')
            if not is_num(cs) or cs < 0:
                errors.append(f'{where}: a clip needs clip_start_sec (0 or more)')
            if 'clip_hold_sec' in f:
                h = f['clip_hold_sec']
                if not is_num(h) or h < 0:
                    errors.append(f'{where}: clip_hold_sec={h!r} is not valid (seconds)')
                elif is_num(f.get('dur')) and h >= float(f['dur']) + float(f.get('xfade', 0.0) or 0.0):
                    errors.append(f'{where}: clip_hold_sec={h} is as long as the seat (dur+xfade): '
                                  'the video would not play at all')
            if 'clip_parts' in f:
                errors += clip_parts_errors(f, where)
        else:
            for key in ('clip_hold_sec', 'clip_parts'):
                if key in f:
                    errors.append(f'{where}: {key} belongs only in a clip seat')
        errors += zoom_errors(f, where, kind)
        st = f.get('status', 'placeholder')
        if st not in STATUSES:
            errors.append(f'{where}: status={st!r} must be one of ' + '/'.join(STATUSES))
        xf = f.get('xfade', 0.0)
        if not is_num(xf) or xf < 0:
            errors.append(f'{where}: xfade={xf!r} is not valid (seconds)')
        elif is_num(f.get('dur')) and xf >= f['dur']:
            errors.append(f'{where}: xfade={xf} is not shorter than dur={f["dur"]}: the cross-fade eats the seat')
        errors += rotate_errors(f.get('rotate'), where)
        if 'pin' in f and (not isinstance(f['pin'], str) or not f['pin'].strip()):
            # a reason, not a flag: a pin without a reason becomes "nobody knows why" and is removed one day
            errors.append(f'{where}: pin={f["pin"]!r} is not valid (write why the seat is pinned)')
        n = f.get('i')
        if isinstance(n, int) and not isinstance(n, bool):
            if n in seen_i:
                errors.append(f'{where}: i={n} is used again (frames[{seen_i[n]}])')
            seen_i[n] = idx
    errors += timeline_errors(frames, data.get('duration_sec'))
    errors += fade_out_errors(data)
    return errors


def needs_photo_root(data):
    """True if anything is taken from the photo folder (anything without "root": "work")."""
    if not isinstance(data, dict):
        return True
    items = [f for f in (data.get('frames') or []) if isinstance(f, dict)]
    items += [data[k] for k in ('prologue', 'epilogue') if isinstance(data.get(k), dict)]
    return not items or any(f.get('root') != 'work' for f in items)


def zoom_errors(f, where, kind='photo'):
    """`zoom` (zoom in to), `zoom_from` (zoom out from: a subject moving away) and `zoom_center`."""
    errors = []
    zoom = f.get('zoom', ZOOM_MAX)
    if not is_num(zoom) or zoom < 1.0:
        errors.append(f'{where}: zoom={zoom!r} is not valid (1.0 or more)')
        zoom = ZOOM_MAX
    zf = f.get('zoom_from')
    if zf is not None:
        if kind == 'clip':
            errors.append(f'{where}: zoom_from belongs only in a still seat')
        if not is_num(zf) or zf <= 1.0:
            errors.append(f'{where}: zoom_from={zf!r} is not valid (more than 1.0: the zoom it starts from)')
        elif zf <= zoom:
            errors.append(f'{where}: zoom_from={zf} is not more than zoom={zoom}: that is not a zoom out '
                          '(zoom in is written with zoom alone)')
        errors += ease_errors(f.get('ease'), where)
    elif 'ease' in f:
        errors.append(f'{where}: ease works only with zoom_from')
    zc = f.get('zoom_center')
    if zc is not None:
        if zf is None:
            errors.append(f'{where}: zoom_center works only with zoom_from')
        if not (isinstance(zc, (list, tuple)) and len(zc) == 2 and all(is_num(v) and 0.0 <= v <= 1.0 for v in zc)):
            errors.append(f'{where}: zoom_center={zc!r} is not valid ([x, y], each 0.0 to 1.0: the point that stays put)')
    return errors


def ease_errors(spec, where, what='ease'):
    if spec is None or spec in EASES:
        return []
    return [f'{where}: {what}={spec!r} must be one of ' + '/'.join(EASES)]


def side_errors(side, name):
    """`prologue` / `epilogue`: one family video with its own sound, before / after the song (outside its timeline)."""
    if side is None:
        return []
    if not isinstance(side, dict):
        return [f'{name}: not an object']
    errors = []
    for key, types, cond, hint in (('src', str, lambda v: bool(v), 'a video with sound'),
                                   ('dur', (int, float), lambda v: v > 0, 'seconds')):
        if key not in side:
            errors.append(f'{name}: missing key {key} ({hint})')
        elif not isinstance(side[key], types) or isinstance(side[key], bool) or not cond(side[key]):
            errors.append(f'{name}: {key}={side[key]!r} is not valid ({hint})')
    allowed = {'start_sec': (lambda v: v >= 0, 'seconds into the video'),
               'gain_db': (lambda v: -40 <= v <= 40, 'dB, -40 to 40'),
               'fade_in': (lambda v: v >= 0, 'seconds'), 'fade_out': (lambda v: v >= 0, 'seconds')}
    own, other = ('body_fade_in', 'body_fade_out') if name == 'prologue' else ('body_fade_out', 'body_fade_in')
    allowed[own] = (lambda v: v >= 0, 'seconds')
    if other in side:                                    # written but doing nothing is worse than an error
        errors.append(f'{name}: {other} belongs to the ' + ('epilogue' if name == 'prologue' else 'prologue'))
    for key, (cond, hint) in allowed.items():
        if key in side and (not is_num(side[key]) or not cond(side[key])):
            errors.append(f'{name}: {key}={side[key]!r} is not valid ({hint})')
    fi, fo = side.get('fade_in', 0.0), side.get('fade_out', 0.0)
    if is_num(fi) and is_num(fo) and is_num(side.get('dur')) and fi + fo >= side['dur']:
        errors.append(f'{name}: fade_in={fi} + fade_out={fo} is not shorter than dur={side["dur"]}')
    if side.get('status', 'placeholder') not in STATUSES:
        errors.append(f'{name}: status={side["status"]!r} must be one of ' + '/'.join(STATUSES))
    errors += rotate_errors(side.get('rotate'), name)
    return errors


def final_still_errors(spec):
    if spec is None:
        return []
    if not isinstance(spec, dict) or not isinstance(spec.get('title'), str) or not spec['title'].strip():
        return ['final_still: needs a title (the text drawn on the closing picture)']
    errors = []
    for key in ('title_pt', 'left_in', 'top_in', 'width_in', 'slide_w_in'):
        if key in spec and (not is_num(spec[key]) or spec[key] <= 0):
            errors.append(f'final_still: {key}={spec[key]!r} is not valid (a positive number)')
    if 'color' in spec and not re.fullmatch(r'#[0-9A-Fa-f]{6}', str(spec['color'])):
        errors.append(f'final_still: color={spec["color"]!r} is not valid (#RRGGBB)')
    return errors


def fade_out_errors(data):
    """The picture fading to black at the end (`video_fade_out`, or `epilogue.body_fade_out`). The song fades itself."""
    epi = data.get('epilogue')
    if 'video_fade_out' in data:
        d = data['video_fade_out']
        if not is_num(d) or d <= 0:
            return [f'video_fade_out={d!r} is not valid (seconds)']
        if isinstance(epi, dict):
            return ['video_fade_out and epilogue.body_fade_out do the same thing: with an epilogue, use body_fade_out']
        key = 'video_fade_out'
    elif isinstance(epi, dict) and is_num(epi.get('body_fade_out')) and epi['body_fade_out'] > 0:
        d, key = epi['body_fade_out'], 'epilogue.body_fade_out'
    else:
        return []
    frames = data.get('frames')
    if isinstance(frames, list) and frames and isinstance(frames[-1], dict):
        dur = frames[-1].get('dur')
        if is_num(dur) and d > dur:
            return [f'{key}={d} is longer than the last seat (dur={dur}): it would drag the seat before into black']
    return []


def timeline_errors(frames, duration_sec, tol=0.02):
    """Seats follow each other without gaps or overlaps, and add up to the song. Checked every time."""
    usable = [f for f in frames if isinstance(f, dict) and is_num(f.get('at')) and is_num(f.get('dur'))]
    if len(usable) != len(frames):
        return []
    errors, cursor = [], 0.0
    for idx, f in enumerate(usable, 1):
        if abs(f['at'] - cursor) > tol:
            gap = f['at'] - cursor
            errors.append(f'frames[{idx}] (i={f.get("i")}): at={f["at"]:.2f} but the seats before end at '
                          f'{cursor:.2f}: a {"gap" if gap > 0 else "overlap"} of {abs(gap):.2f} s')
        cursor = f['at'] + f['dur']
    if is_num(duration_sec) and abs(cursor - duration_sec) > tol:
        errors.append(f'the seats add up to {cursor:.2f} s, not duration_sec={duration_sec:.2f} s '
                      f'(difference {cursor - duration_sec:+.2f} s)')
    return errors


def prologue_length(data):
    return float(data['prologue']['dur']) if data.get('prologue') else 0.0


def epilogue_length(data):
    return float(data['epilogue']['dur']) if data.get('epilogue') else 0.0


def total_length(data):
    """prologue + song + epilogue. duration_sec stays the song's length: it is the timeline's own measure."""
    return prologue_length(data) + float(data['duration_sec']) + epilogue_length(data)


# ---------- seats and content ----------

def content_of(frame):
    return {k: v for k, v in frame.items() if k not in SLOT_KEYS}


def put_content(frame, content):
    for k in [k for k in frame if k not in SLOT_KEYS]:
        del frame[k]
    frame.update(content)
    return frame


def apply_move(data, i, after):
    """Move the content of seat i to the seat after `after` (0 = to the front). Seats stay where they are."""
    frames = data['frames']
    pairs = [(f['i'], content_of(f)) for f in frames]
    nums = [n for n, _ in pairs]
    if i not in nums:
        raise ConfigError([f'no seat i={i}'])
    if after != 0 and after not in nums:
        raise ConfigError([f'no seat i={after} to move after'])
    if i == after:
        raise ConfigError([f'seat {i} cannot move after itself'])
    moving = pairs.pop(nums.index(i))
    pos = 0 if after == 0 else [n for n, _ in pairs].index(after) + 1
    pairs.insert(pos, moving)
    for f, (_, c) in zip(frames, pairs):
        put_content(f, c)
    return frames


def pinned_seats(data):
    """{i: reason} of the pinned seats. Pins live in the definition, not in someone's memory."""
    return dict(sorted((f['i'], f['pin']) for f in data.get('frames', [])
                       if isinstance(f, dict) and isinstance(f.get('pin'), str) and f['pin'].strip()))


def apply_pin(data, i, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ConfigError([f'pinning seat {i} needs a reason', '  e.g. --pin-set 42="the first line of the chorus"'])
    for f in data['frames']:
        if f['i'] == i:
            before = f.get('pin')
            f['pin'] = reason.strip()
            return before
    raise ConfigError([f'no seat i={i}'])


def apply_unpin(data, i):
    for f in data['frames']:
        if f['i'] == i:
            return f.pop('pin', None)
    raise ConfigError([f'no seat i={i}'])


def apply_sort(data, numbers, key_of, pinned=()):
    """Sort the content of these seats by key_of(i). Seats pinned in the definition always stay, even if the caller
    forgot to pass them. A stable sort: equal keys keep their order."""
    pinned = set(pinned) | set(pinned_seats(data))
    free = [f for f in data['frames'] if f['i'] in numbers and f['i'] not in pinned]
    keyed = sorted(((key_of(f['i']), content_of(f)) for f in free), key=lambda t: t[0])
    for f, (_, c) in zip(free, keyed):
        put_content(f, c)
    return [f['i'] for f in free]


def apply_status(data, numbers, status):
    if status not in STATUSES:
        raise ConfigError([f'status={status!r} must be one of ' + '/'.join(STATUSES)])
    known = {f['i'] for f in data['frames']}
    missing = sorted(n for n in numbers if n not in known)
    if missing:
        raise ConfigError([f'no such seats: {missing}'])
    hit = 0
    for f in data['frames']:
        if f['i'] in numbers:
            f['status'] = status
            hit += 1
    return hit


def parse_numbers(spec):
    """'1-22', '3,5,9', '1-6,9' -> a set of seat numbers."""
    out = set()
    for part in str(spec).replace(' ', '').split(','):
        if not part:
            continue
        m = RE_RANGE.match(part)
        if not m:
            raise ConfigError([f'not a seat number or range: {part} (e.g. 1-22 or 3,5,9)'])
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if b < a:
            raise ConfigError([f'backwards range: {part}'])
        out.update(range(a, b + 1))
    if not out:
        raise ConfigError(['no seat numbers'])
    return out


def normalize_src(src):
    """Forward slashes everywhere (they work on Windows too); no quotes."""
    return src.strip().strip('"').replace('\\', '/')


def kind_for(src):
    ext = os.path.splitext(src)[1].lower()
    return 'clip' if ext in VIDEO_EXT else 'photo' if ext in PHOTO_EXT else None


def apply_replace(data, i, src, status='picked', clip_start_sec=None):
    """Put another picture or video in seat i. **at and dur are not touched.** The kind follows the file: a video
    becomes a clip (start 0 unless given), a photo drops the clip keys. A closing picture (kind final) stays final."""
    src = normalize_src(src)
    for f in data['frames']:
        if f.get('i') == i:
            before = (f.get('at'), f.get('dur'))
            f['src'] = src
            f['status'] = status
            if f.get('kind') != 'final':
                kind = kind_for(src)
                f.pop('clip_hold_sec', None)          # these were fitted to the previous video
                f.pop('clip_parts', None)
                if kind == 'clip':
                    f['kind'] = 'clip'
                    f['clip_start_sec'] = float(clip_start_sec) if clip_start_sec is not None else 0.0
                elif kind == 'photo':
                    f.pop('kind', None)
                    f.pop('clip_start_sec', None)
                    f.pop('rotate', None)
            assert (f.get('at'), f.get('dur')) == before
            return f
    raise ConfigError([f'no seat i={i}'])


# ============================================================
# Paths and lengths (pure functions)
# ============================================================
def photo_root_of(data, work_dir, override=None):
    root = override or data.get('photo_root')
    if not root:
        return None
    return root if os.path.isabs(root) else os.path.normpath(os.path.join(work_dir, root))


def resolve_src(frame, photo_root, work_dir):
    """The file of a seat: from the photo folder, or from the work folder for "root": "work"."""
    base = work_dir if frame.get('root') == 'work' or not photo_root else photo_root
    return os.path.normpath(os.path.join(base, frame['src']))


def segment_length(frame):
    """A segment is its seconds on screen plus the cross-fade into the next one (see xfade_offsets)."""
    return float(frame['dur']) + float(frame.get('xfade', 0.0))


def xfade_offsets(frames):
    """The offset of each cross-fade is the next seat's `at`. With L_k = dur_k + x_k, the chain up to k is
    sum(dur_1..k) + x_k long; going back x_k lands on sum(dur_1..k) = at_(k+1). So the whole is sum(dur) again."""
    return [float(f['at']) for f in frames[1:]]


ROTATIONS = {'ccw': 'transpose=2', 'cw': 'transpose=1', '180': 'transpose=1,transpose=1'}


def rotate_errors(spec, where):
    if spec is None or spec in ROTATIONS:
        return []
    return [f'{where}: rotate={spec!r} must be one of ' + '/'.join(ROTATIONS)]


def rotate_chain(spec):
    """For a video whose rotation metadata is wrong (a landscape picture marked -90: people lie on their side).
    It turns the picture *on top of* ffmpeg's own autorotation, which stays on: most portrait phone videos are
    right as they are. A named label can be used once, so the turned picture is split in two."""
    if not spec:
        return '', '0:v', '0:v'
    return f'[0:v]{ROTATIONS[spec]},split=2[rotbg][rotfg];', 'rotbg', 'rotfg'


def fit_filter(bg_in='0:v', fg_in='0:v', tag=''):
    """Fill 1920x1080 whatever the shape: a portrait video sits on a blurred, darkened copy of itself."""
    bg = (f'[{bg_in}]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,'
          f'crop={OUT_W}:{OUT_H},gblur=sigma={BLUR_SIGMA},'
          f'eq=brightness=-{(1.0 - BG_DARKEN):.2f}[bg{tag}];')
    fg = f'[{fg_in}]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,setsar=1[fg{tag}];'
    return bg + fg + f'[bg{tag}][fg{tag}]overlay=(W-w)/2:(H-h)/2'


def zoom_center_of(frame):
    zc = frame.get('zoom_center') or (0.5, 0.5)
    return float(zc[0]), float(zc[1])


# ============================================================
# Camera moves drawn at sub-pixel positions
# ============================================================
SUBPIXEL_TAG = 'subpixel1'          # the drawing generation, part of a moving seat's signature


def segment_frames(length):
    """Frames needed for `length` seconds. Rounded up, like ffmpeg's -t (6.219 s -> 187 frames): rounding to the
    nearest would make some seats one frame short and leave the cross-fade short."""
    return max(1, int(math.ceil(length * FPS - 1e-9)))


def ease_at(p, ease='linear'):
    """Progress p (0..1) through the easing: 'out' slows down to a stop, 1-(1-p)^2."""
    p = min(max(p, 0.0), 1.0)
    return 1.0 - (1.0 - p) ** 2 if ease == 'out' else p


def zoom_z_at(z_from, z_to, nframes, n, ease='linear'):
    """The zoom at frame n: z_from at the first frame, z_to at the last. Counted in frames."""
    p = ease_at(n / max(1, nframes - 1), ease)
    lo, hi = min(z_from, z_to), max(z_from, z_to)
    return min(max(z_from + (z_to - z_from) * p, lo), hi)


def crop_box_at(iw, ih, z, cx=0.5, cy=0.5):
    """The window (left, top, right, bottom) at zoom z, **in fractions of a pixel**. The point (cx, cy) stays at the
    same place on the screen. Rounding these to whole pixels is exactly what brings the judder back."""
    cw, ch = iw / z, ih / z
    return (cx * (iw - cw), cy * (ih - ch), cx * (iw - cw) + cw, cy * (ih - ch) + ch)


def rawvideo_input():
    """Raw frames on stdin. The rate must be given on the input side too (ffmpeg would read 25 fps)."""
    return ['-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OUT_W}x{OUT_H}', '-r', str(FPS), '-i', '-']


def ken_burns_frames(img, nframes, z_from, z_to, cx=0.5, cy=0.5, ease='linear'):
    """Yield the raw rgb24 frames of a zoom, each cut from fractional coordinates (Image.resize's box)."""
    from PIL import Image
    with Image.open(img) as src:
        im = src.convert('RGB')
    iw, ih = im.size
    for n in range(nframes):
        z = zoom_z_at(z_from, z_to, nframes, n, ease)
        yield im.resize((OUT_W, OUT_H), Image.LANCZOS, box=crop_box_at(iw, ih, z, cx, cy)).tobytes()


def run_render(cmd, feed=None):
    """Run ffmpeg, feeding raw frames if given. If the feeding side fails, close and kill ffmpeg first (it would
    otherwise wait on stdin for ever). Judge by ffmpeg's exit code: it writes its own reason on stderr."""
    if feed is None:
        subprocess.check_call(cmd)
        return

    def shut(pipe):
        try:
            pipe.close()
        except OSError:
            pass

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for buf in feed():
            proc.stdin.write(buf)
    except OSError:
        pass                                # ffmpeg ended first: its exit code says why
    except BaseException:
        shut(proc.stdin)
        proc.kill()
        proc.wait()
        raise
    shut(proc.stdin)
    rc = proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


ENCODE = ['-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', str(FPS)]


def build_photo_command(img, frame, dst):
    """A still seat from a picture prepared at 3840x2160. Returns (command, frame feeder or None).
    A moving seat is drawn by Pillow (ken_burns_frames); a still one (zoom 1.0) is left to ffmpeg."""
    length = segment_length(frame)
    nframes = segment_frames(length)
    zoom = float(frame.get('zoom', ZOOM_MAX))
    z_from = frame.get('zoom_from')
    head = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    if z_from is None and zoom <= 1.0:
        return head + ['-loop', '1', '-i', img, '-vf', f'scale={OUT_W}:{OUT_H},setsar=1,fps={FPS},format=yuv420p',
                       '-t', f'{length:.3f}', '-an', *ENCODE, dst], None
    if z_from:
        z0, (cx, cy), ease = float(z_from), zoom_center_of(frame), frame.get('ease', 'linear')
    else:
        z0, cx, cy, ease = 1.0, 0.5, 0.5, 'linear'

    def feed():
        return ken_burns_frames(img, nframes, z0, zoom, cx, cy, ease)

    return head + [*rawvideo_input(), '-vf', 'setsar=1,format=yuv420p', '-t', f'{length:.3f}', '-an',
                   *ENCODE, dst], feed


def clip_hold(frame):
    """Seconds to hold the clip's last frame to fill the seat (when the next cut follows too soon to cut longer)."""
    return float(frame.get('clip_hold_sec', 0.0) or 0.0)


def clip_parts(frame):
    """[(start, dur), ...] when a seat joins several stretches of one video with hard cuts; None otherwise."""
    parts = frame.get('clip_parts')
    return [(float(p['start']), float(p['dur'])) for p in parts] if parts else None


def clip_play_plan(frame):
    """The stretches of the source video this seat reads."""
    parts = clip_parts(frame)
    if parts:
        return parts
    return [(float(frame.get('clip_start_sec', 0.0)), segment_length(frame) - clip_hold(frame))]


def clip_parts_errors(f, where):
    parts = f.get('clip_parts')
    if not isinstance(parts, list) or len(parts) < 2:
        return [f'{where}: clip_parts needs two or more stretches (for one, clip_start_sec is enough)']
    errors, total = [], 0.0
    for k, p in enumerate(parts):
        if not isinstance(p, dict):
            return [f'{where}: clip_parts[{k}] must be {{"start": s, "dur": s}}']
        for key, cond in (('start', lambda v: v >= 0), ('dur', lambda v: v > 0)):
            if not is_num(p.get(key)) or not cond(p[key]):
                errors.append(f'{where}: clip_parts[{k}].{key}={p.get(key)!r} is not valid (seconds)')
        if not errors:
            total += float(p['dur'])
    if errors:
        return errors
    if is_num(f.get('clip_start_sec')) and abs(float(f['clip_start_sec']) - float(parts[0]['start'])) > 1e-6:
        errors.append(f'{where}: clip_start_sec must equal clip_parts[0].start')
    if f.get('rotate'):
        errors.append(f'{where}: clip_parts and rotate cannot be used together')
    if is_num(f.get('dur')):
        need = float(f['dur']) + float(f.get('xfade', 0.0) or 0.0) - float(f.get('clip_hold_sec', 0.0) or 0.0)
        if abs(total - need) > 0.011:
            errors.append(f'{where}: the stretches add up to {total:.3f} s, not the seat\'s {need:.3f} s '
                          '(dur + xfade - clip_hold_sec; change the stretches, not the seat)')
    return errors


def clip_thumb_sec(frame):
    """The source second shown for a clip seat on the storyboard: the middle of what plays, mapped onto the
    stretches, and never past the last frame played (a held seat reads less than its length)."""
    mid = float(frame['dur']) / 2
    plan = clip_play_plan(frame)
    mid = min(mid, max(sum(d for _s, d in plan) - 1.0 / FPS, 0.0))
    for start, d in plan:
        if mid < d:
            return start + mid
        mid -= d
    start, d = plan[-1]
    return start + max(d - 1.0 / FPS, 0.0)


def build_clip_command(src, frame, dst):
    """A video seat: seek before -i (fast), always silent, autorotation left on (rotate only on top of it).
    A held seat reads only the seconds that play, then repeats the last frame (tpad)."""
    length = segment_length(frame)
    hold = clip_hold(frame)
    pad = f',tpad=stop_mode=clone:stop_duration={hold:.3f}' if hold > 0 else ''
    head = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    parts = clip_parts(frame)
    if parts:
        inputs, chains, labels = [], [], []
        for k, (start, d) in enumerate(parts):
            inputs += ['-ss', f'{start:.3f}', '-t', f'{d:.3f}', '-i', src]
            chains.append(fit_filter(f'{k}:v', f'{k}:v', tag=str(k)) + f'[p{k}];')
            labels.append(f'[p{k}]')
        chain = ''.join(chains) + ''.join(labels) + f'concat=n={len(parts)}:v=1:a=0,fps={FPS}{pad},format=yuv420p'
        return head + [*inputs, '-t', f'{length:.3f}', '-an', '-filter_complex', chain, *ENCODE, dst]
    pre, bg_in, fg_in = rotate_chain(frame.get('rotate'))
    play = ['-t', f'{length - hold:.3f}'] if hold > 0 else []
    return head + ['-ss', f'{float(frame.get("clip_start_sec", 0)):.3f}', *play, '-i', src,
                   '-t', f'{length:.3f}', '-an',
                   '-filter_complex', pre + fit_filter(bg_in, fg_in) + f',fps={FPS}{pad},format=yuv420p',
                   *ENCODE, dst]


# The prologue, the song part and the epilogue are joined without re-encoding, so they must agree exactly
# (H.264 parameters included): otherwise a player cannot start decoding in the middle of the joined file.
COLOR = (',scale=in_range=auto:out_range=full,setparams=range=pc:color_primaries=unknown'
         ':color_trc=unknown:colorspace=bt470bg')
COLOR_TAGS = ['-color_range', 'pc', '-colorspace', 'bt470bg', '-color_primaries', 'unspecified',
              '-color_trc', 'unspecified']
AUDIO_OUT = ['-c:a', 'aac', '-b:a', f'{AUDIO_BPS // 1000}k', '-ar', '48000', '-ac', '2']


def build_side_command(src, side, dst):
    """The prologue or epilogue: one video with its own sound. The sound is raised by gain_db and always limited;
    fade_out fades picture and sound (never overlapping the song); fade_in starts from black and silence."""
    dur = float(side['dur'])
    fade, fade_in = float(side.get('fade_out', 0.0)), float(side.get('fade_in', 0.0))
    gain = float(side.get('gain_db', 0.0))
    pre, bg_in, fg_in = rotate_chain(side.get('rotate'))
    vchain = pre + fit_filter(bg_in, fg_in) + f',fps={FPS},format=yuv420p' + COLOR
    achain = '[0:a]' + (f'volume={gain:.2f}dB,' if gain else '') + 'alimiter=limit=0.95'
    if fade_in > 0:
        vchain += f',fade=t=in:st=0:d={fade_in:.3f}'
        achain += f',afade=t=in:st=0:d={fade_in:.3f}'
    if fade > 0:
        st = max(0.0, dur - fade)
        vchain += f',fade=t=out:st={st:.3f}:d={fade:.3f}'
        achain += f',afade=t=out:st={st:.3f}:d={fade:.3f}'
    return ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-ss', f'{float(side.get("start_sec", 0.0)):.3f}', '-i', src, '-t', f'{dur:.3f}',
            '-filter_complex', vchain + '[vout];' + achain + ',aformat=sample_rates=48000:channel_layouts=stereo[aout]',
            '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-r', str(FPS),
            *COLOR_TAGS, *AUDIO_OUT, '-movflags', '+faststart', dst]


def build_concat_command(list_path, dst):
    """Join without re-encoding. `setts` restarts the timestamps at 0: without it the concat demuxer leaves a 21 ms
    empty edit at the start of the video track, and Windows' media player then cannot seek in the file."""
    return ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list_path,
            '-c', 'copy', '-bsf:v', 'setts=pts=PTS-STARTPTS:dts=DTS-STARTDTS', '-movflags', '+faststart', dst]


def concat_list_text(parts):
    return ''.join("file '%s'\n" % p.replace('\\', '/').replace("'", "'\\''") for p in parts)


def build_xfade_command(segments, frames, audio, dst, duration_sec, fade_in=0.0, fade_out=0.0):
    """Join every segment with its cross-fade and lay the song under it, unprocessed (loudness comes later, on the
    whole). fade_out darkens only the picture: the song fades by itself."""
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    for s in segments:
        cmd += ['-i', s]
    cmd += ['-i', audio]
    parts, last = [], '[0:v]'
    offsets = xfade_offsets(frames)
    for k in range(1, len(segments)):
        out = f'[v{k}]' if k < len(segments) - 1 else '[vout]'
        x = float(frames[k - 1].get('xfade', 0.0))
        if x <= 0:
            parts.append(f'{last}[{k}:v]concat=n=2:v=1:a=0{out}')
        else:
            parts.append(f'{last}[{k}:v]xfade=transition=fade:duration={x:.3f}:offset={offsets[k - 1]:.3f}{out}')
        last = out
    if fade_in > 0:
        parts.append(f'{last}fade=t=in:st=0:d={fade_in:.3f}[vfin]')
        last = '[vfin]'
    if fade_out > 0:
        parts.append(f'{last}fade=t=out:st={max(0.0, duration_sec - fade_out):.3f}:d={fade_out:.3f}[vfout]')
        last = '[vfout]'
    if parts:
        cmd += ['-filter_complex', ';'.join(parts)]
    cmd += ['-map', last if parts else '0:v', '-map', f'{len(segments)}:a', '-t', f'{duration_sec:.3f}',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-r', str(FPS),
            *AUDIO_OUT, '-movflags', '+faststart', dst]
    return cmd


# ---------- loudness and size ----------

def loudness_gain_db(measured_lufs, target_lufs=LOUDNESS_TARGET_LUFS):
    """One gain for the whole: turning a knob, not compressing (the song's own quiet and loud parts stay)."""
    return round(target_lufs - measured_lufs, 2)


def build_loudness_command(src, dst, gain_db, ceil_dbtp=TRUE_PEAK_CEIL_DBTP):
    """Re-make only the sound. The limiter runs 4x oversampled (192 kHz) to catch peaks between samples, and with
    level=0 (otherwise alimiter raises the output to its limit and decides the loudness itself)."""
    limit = 10 ** (ceil_dbtp / 20)
    achain = (f'volume={gain_db:.2f}dB,aresample=192000,'
              f'alimiter=limit={limit:.4f}:attack=5:release=50:level=0,aresample=48000')
    return ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', src, '-map', '0:v:0', '-map', '0:a:0',
            '-c:v', 'copy', '-af', achain, *AUDIO_OUT, '-movflags', '+faststart', dst]


def parse_ebur128_summary(text):
    """(integrated LUFS, true peak dBTP) from the Summary of ffmpeg's ebur128=peak=true."""
    tail = text[text.rfind('Summary:'):]
    i = re.search(r'I:\s+(-?[\d.]+|-inf) LUFS', tail)
    p = re.search(r'Peak:\s+(-?[\d.]+|-inf) dBFS', tail)
    if not i or not p:
        return None
    def to_f(s):
        return float('-inf') if s == '-inf' else float(s)
    return to_f(i.group(1)), to_f(p.group(1))


def measure_loudness(path):
    try:
        r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-vn', '-af', 'ebur128=peak=true',
                            '-f', 'null', '-'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    except OSError:
        return None
    return parse_ebur128_summary(r.stderr)


def normalize_loudness(path, work_tmp):
    """Bring the finished video (prologue, song and epilogue together) to the target, in place. If the limiter
    shaved off so much that the target is missed, add that and redo once (from the original)."""
    before = measure_loudness(path)
    if before is None or before[0] == float('-inf'):
        raise ConfigError([f'cannot measure the loudness of {path} (is the song silent?)'])
    gain = loudness_gain_db(before[0])
    after = None
    for _ in range(2):
        try:
            subprocess.check_call(build_loudness_command(path, work_tmp, gain))
        except (subprocess.CalledProcessError, OSError) as ex:
            if os.path.exists(work_tmp):
                os.remove(work_tmp)
            raise ConfigError([f'setting the loudness failed: {ex}'])
        after = measure_loudness(work_tmp)
        if after is None or abs(after[0] - LOUDNESS_TARGET_LUFS) <= LOUDNESS_TOLERANCE_LU:
            break
        gain = round(gain + (LOUDNESS_TARGET_LUFS - after[0]), 2)
    replace_file(work_tmp, path)
    print(f'  loudness: {before[0]:.1f} LUFS (peak {before[1]:+.1f}) -> {after[0]:.1f} LUFS '
          f'(peak {after[1]:+.1f}), gain {gain:+.2f} dB')
    if abs(after[0] - LOUDNESS_TARGET_LUFS) > 1.0 or after[1] > TRUE_PEAK_CEIL_DBTP + 0.5:
        print(f'  warning: outside the target ({LOUDNESS_TARGET_LUFS:.0f} LUFS, peaks at most '
              f'{TRUE_PEAK_CEIL_DBTP} dBTP); listen to it')
    return after


def shrink_commands(src, dst, duration, passlog):
    """Two passes to about TARGET_VIDEO_BYTES (the room player's limit is MAX_VIDEO_BYTES per video).
    The first pass writes an MP4 too (to the null device): with -f null its statistics differ and the size misses."""
    bps = int(TARGET_VIDEO_BYTES * 8 / duration) - AUDIO_BPS
    if bps < MIN_VIDEO_BPS:
        raise ConfigError([f'a {duration:.0f}-second video cannot fit in {TARGET_VIDEO_BYTES / 1e6:.0f} MB '
                           'with a watchable picture; make it shorter'])
    kbps = f'{bps // 1000}k'
    common = ['-map', '0:v:0', '-c:v', 'libx264', '-preset', 'slow', '-b:v', kbps, '-pix_fmt', 'yuv420p',
              '-passlogfile', passlog]
    return [['ffmpeg', '-v', 'error', '-y', '-i', src, *common, '-pass', '1', '-an', '-f', 'mp4', os.devnull],
            ['ffmpeg', '-v', 'error', '-y', '-i', src, *common, '-pass', '2', '-map', '0:a:0', '-c:a', 'copy',
             '-movflags', '+faststart', dst]]


def fit_for_player(path, cdir):
    """Re-encode a finished video that is over the room player's size limit. Returns the size in bytes."""
    size = os.path.getsize(path)
    if size <= MAX_VIDEO_BYTES:
        return size
    info = probe_media(path)
    if not info or not info[2]:
        raise ConfigError([f'cannot read the length of {path}'])
    tmp = os.path.join(cdir, '_small.mp4')
    print(f'  {size / 1e6:.0f} MB is over the room player\'s {MAX_VIDEO_BYTES / 1e6:.0f} MB: '
          f'two passes to about {TARGET_VIDEO_BYTES / 1e6:.0f} MB ...')
    try:
        for cmd in shrink_commands(path, tmp, info[2], os.path.join(cdir, '_pass')):
            subprocess.check_call(cmd)
    except (subprocess.CalledProcessError, OSError) as ex:
        raise ConfigError([f'making it smaller failed: {ex}'])
    replace_file(tmp, path)
    return os.path.getsize(path)


# ============================================================
# Dates taken (for the storyboard and --sort)
# ============================================================
def exif_datetime(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            exif = im.getexif()
            values = [exif.get(306)]
            try:
                sub = exif.get_ifd(0x8769)                   # DateTimeOriginal / Digitized live here
                values = [sub.get(36867), sub.get(36868)] + values
            except Exception:
                pass
            for v in values:
                if isinstance(v, str) and len(v) >= 10 and v[:4].isdigit() and 1990 <= int(v[:4]) <= 2100:
                    return v[:19]
    except Exception:
        pass
    return None


def fname_date(path):
    m = RE_FNAME_DATE.search(os.path.basename(path))
    if not m:
        return None
    y, mo, d = int(m.group(1) + m.group(2)), int(m.group(3)), int(m.group(4))
    return '%04d-%02d-%02d' % (y, mo, d) if 1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31 else None


def fname_datetime(path):
    """Date and time from a file name. Pixel phones (PXL_) write UTC: shown in this computer's time zone."""
    base = os.path.basename(path)
    m = RE_FNAME_TIME.search(base)
    if not m:
        return None
    try:
        t = datetime.datetime(*(int(m.group(k)) for k in range(1, 7)))
    except ValueError:
        return None
    if not 1990 <= t.year <= 2100:
        return None
    if base.upper().startswith('PXL_'):
        t = t.replace(tzinfo=datetime.timezone.utc).astimezone()
    return t.strftime('%Y-%m-%d'), t.strftime('%H:%M')


def folder_date(path):
    """A year (2020/) or year-month (2025-4/) from the folders, the deepest first."""
    for part in reversed(os.path.normpath(path).split(os.sep)):
        if re.fullmatch(r'(19|20)\d{2}', part):
            return part
        m = re.fullmatch(r'((19|20)\d{2})-(\d{1,2})', part)
        if m:
            return '%s-%02d' % (m.group(1), int(m.group(3)))
    return None


def video_datetime(path):
    """A video's creation_time (UTC) in this computer's time zone."""
    try:
        out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format_tags=creation_time',
                                       '-of', 'default=nw=1:nk=1', path], stderr=subprocess.DEVNULL)
        v = out.decode('utf-8', 'replace').strip()
        if len(v) >= 19 and v[:4].isdigit():
            t = datetime.datetime.strptime(v[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
            t = t.astimezone()
            return t.strftime('%Y-%m-%d'), t.strftime('%H:%M')
    except Exception:
        pass
    return None


def capture_datetime(path):
    """(date, time or None, where it came from): EXIF, name, video, folder, modified — the surest first.
    "modified" is a last resort (copying a file makes it today), so the storyboard says where a date came from."""
    when = exif_datetime(path)
    if when:
        return when[:10].replace(':', '-'), (when[11:16] if len(when) >= 16 else None), 'EXIF'
    dt = fname_datetime(path)
    if dt:
        return dt[0], dt[1], 'name'
    d = fname_date(path)
    if d:
        return d, None, 'name'
    if os.path.splitext(path)[1].lower() in VIDEO_EXT:
        dt = video_datetime(path)
        if dt:
            return dt[0], dt[1], 'video'
    d = folder_date(path)
    if d:
        return d, None, 'folder'
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d'), None, 'modified'


def capture_date(path):
    d, _t, origin = capture_datetime(path)
    return d, origin


def capture_label(path):
    d, t, origin = capture_datetime(path)
    return (d + ' ' + t) if t else d, origin


# ============================================================
# Probing
# ============================================================
def probe_media(path):
    """(width, height, seconds, rotation) of a video, or None."""
    try:
        out = subprocess.check_output(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height:stream_side_data=rotation',
             '-show_entries', 'format=duration', '-of', 'json', path], stderr=subprocess.DEVNULL)
        info = json.loads(out.decode('utf-8', 'replace'))
        st = info['streams'][0]
        rot = 0
        for sd in st.get('side_data_list', []) or []:
            if 'rotation' in sd:
                rot = int(sd['rotation'])
        return st.get('width'), st.get('height'), float(info.get('format', {}).get('duration', 0) or 0), rot
    except Exception:
        return None


def probe_duration(path):
    """Seconds of any media file (a song has no video stream, so probe_media cannot read it)."""
    try:
        out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                       '-of', 'csv=p=0', path], stderr=subprocess.DEVNULL)
        return float(out.decode('utf-8', 'replace').strip())
    except Exception:
        return None


def has_audio(path):
    try:
        out = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'a',
                                       '-show_entries', 'stream=index', '-of', 'csv=p=0', path],
                                      stderr=subprocess.DEVNULL)
        return bool(out.decode('utf-8', 'replace').strip())
    except Exception:
        return False


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as fp:
        for block in iter(lambda: fp.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


# ============================================================
# Files of a work
# ============================================================
def config_suffix(config):
    """One work can have two ending videos. The definition, the cache and the storyboard all follow the name
    together; two definitions sharing a cache would overwrite each other's segments (same seat numbers)."""
    return f'_{config}' if config else ''


def config_path(work_dir, config=None):
    return os.path.join(work_dir, f'ending_video{config_suffix(config)}.json')


def ending_dir(work_dir, config=None):
    return os.path.join(work_dir, f'ending{config_suffix(config)}')


def cache_dir(work_dir, config=None):
    return os.path.join(ending_dir(work_dir, config), 'cache')


def storyboard_paths(work_dir, config=None):
    """The storyboard JPEG and page: one pair, always made together."""
    d = ending_dir(work_dir, config)
    return os.path.join(d, 'storyboard.jpg'), os.path.join(d, 'storyboard.html')


def output_path(work_dir, data):
    return os.path.join(work_dir, 'videos', data['output'])


def load_config(work_dir, config=None):
    path = config_path(work_dir, config)
    name = os.path.basename(path)
    if not os.path.exists(path):
        raise ConfigError([f'{name} not found: {path}', '(--init makes one)'])
    try:
        with open(path, encoding='utf-8') as fp:
            data = json.load(fp)
    except ValueError as ex:
        raise ConfigError([f'{name} is not valid JSON: {ex}'])
    errors = validate_config(data)
    if errors:
        raise ConfigError([f'{name} has errors ({path}):'] + errors)
    return data


def save_config(work_dir, data, config=None):
    with open(config_path(work_dir, config), 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
        fp.write('\n')


def check_sources(data, work_dir, photo_root=None):
    """The files: present, clips long enough, the prologue/epilogue with sound, the song the very same file."""
    errors = []
    root = photo_root_of(data, work_dir, photo_root)
    if needs_photo_root(data) and root and not os.path.isdir(root):
        errors.append(f'the photo folder is not there: {root} (on another computer, give --photo-root)')
        return errors
    for f in data['frames']:
        p = resolve_src(f, root, work_dir)
        if not os.path.exists(p):
            errors.append(f'i={f["i"]}: file not found: {f["src"]}')
            continue
        if f.get('kind') == 'clip':
            info = probe_media(p)
            if not info:
                errors.append(f'i={f["i"]}: not a readable video: {f["src"]}')
            elif info[2]:
                for start, d in clip_play_plan(f):
                    if start + d > info[2] + 0.5:
                        errors.append(f'i={f["i"]}: the cut runs past the end of the video '
                                      f'({start:.1f}+{d:.1f} > {info[2]:.1f} s): {f["src"]}')
    for name in ('prologue', 'epilogue'):
        side = data.get(name)
        if not side:
            continue
        p = resolve_src(side, root, work_dir)
        if not os.path.exists(p):
            errors.append(f'{name}: file not found: {side["src"]}')
            continue
        info = probe_media(p)
        if not info:
            errors.append(f'{name}: not a readable video: {side["src"]}')
            continue
        start = float(side.get('start_sec', 0.0))
        if info[2] and start + float(side['dur']) > info[2] + 0.5:
            errors.append(f'{name}: the cut runs past the end of the video '
                          f'({start:.1f}+{float(side["dur"]):.1f} > {info[2]:.1f} s): {side["src"]}')
        if not has_audio(p):
            errors.append(f'{name}: the video has no sound ({side["src"]}); the {name} plays with its own sound')
    audio = os.path.join(work_dir, data['audio'])
    if not os.path.exists(audio):
        errors.append(f'song not found: {audio}')
    else:
        # The seats are timed to this one file. Another download of "the same song" is usually a little longer or
        # shorter, and every seat after the first difference would be off.
        if data.get('audio_sha256') and sha256_of(audio) != data['audio_sha256']:
            errors.append(f'the song is a different file now (sha256 differs): {data["audio"]}. The seats are timed '
                          'to the original file; put that one back')
        if data.get('audio_duration_sec'):
            got = probe_duration(audio)
            if got and abs(got - float(data['audio_duration_sec'])) > 0.05:
                errors.append(f'the song is {got:.3f} s long, not {float(data["audio_duration_sec"]):.3f} s: '
                              f'{data["audio"]}')
    return errors


# ============================================================
# Pictures (Pillow)
# ============================================================
def find_font(candidates, size):
    from PIL import ImageFont
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


def label_font(size=LABEL_PT):
    from PIL import ImageFont
    font = find_font(LABEL_FONTS, size)
    if font is None:
        print('  warning: no font with Japanese/Chinese/Korean letters found; such labels show as boxes')
        return ImageFont.load_default()
    return font


def prepare_photo(src, dst, final_still=None):
    """One picture at 3840x2160. EXIF orientation is applied first (phone photos lying on their side otherwise).
    A portrait photo sits on a blurred, darkened copy of itself. A closing picture is stretched to fill the frame
    (like a slide) and gets the title."""
    from PIL import Image, ImageFilter, ImageOps
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        if final_still:
            out = im.resize((BIG_W, BIG_H), Image.LANCZOS)
            draw_title(out, final_still)
            out.save(dst, format='JPEG', quality=92, optimize=True)
            return dst
        bg = ImageOps.fit(im, (BIG_W, BIG_H), method=Image.LANCZOS, centering=(0.5, 0.5))
        bg = bg.filter(ImageFilter.GaussianBlur(BLUR_SIGMA * BIG_W // OUT_W))
        bg = bg.point(lambda v: int(v * BG_DARKEN))
        fg = ImageOps.contain(im, (BIG_W, BIG_H), method=Image.LANCZOS)
        bg.paste(fg, ((BIG_W - fg.width) // 2, (BIG_H - fg.height) // 2))
        bg.save(dst, format='JPEG', quality=92, optimize=True)
    return dst


def draw_title(img, spec):
    """The title on the closing picture, placed in inches on a 13.333-inch-wide slide (like [Text] in script.md)."""
    from PIL import ImageDraw, ImageFont
    scale = img.width / (spec.get('slide_w_in', 13.333) * 72.0)      # px per pt
    size = max(1, int(round(spec.get('title_pt', 48) * scale)))
    font = None
    if spec.get('font'):
        font = find_font([spec['font']], size)
    font = font or find_font(TITLE_FONTS, size) or ImageFont.load_default()
    draw = ImageDraw.Draw(img)
    text = spec['title']
    left = spec.get('left_in', 0.5) * 72.0 * scale
    top = spec.get('top_in', 0.45) * 72.0 * scale
    width = spec.get('width_in', 12.3) * 72.0 * scale
    box = draw.textbbox((0, 0), text, font=font)
    x = left + (width - (box[2] - box[0])) / 2 - box[0]
    draw.text((x, top - box[1] + size * 0.18), text, font=font, fill=spec.get('color', '#24334A'))


# ============================================================
# Building
# ============================================================
def moves_camera(frame):
    kind = frame.get('kind', 'photo')
    if kind == 'clip':
        return False
    return bool(frame.get('zoom_from')) or float(frame.get('zoom', ZOOM_MAX)) > 1.0


def signature(frame, src_path, final_still_=None):
    """When a segment must be made again: its file, seconds and kind. Keys are added only when present, so that
    seats nobody touched keep their signature (and are not re-made). A moving seat carries the drawing generation:
    a segment drawn on whole pixels must never be reused."""
    st = os.stat(src_path)
    sig = [frame.get('kind', 'photo'), frame['src'], round(frame['dur'], 3),
           round(float(frame.get('xfade', 0.0)), 3), round(float(frame.get('clip_start_sec', 0)), 3),
           float(frame.get('zoom', ZOOM_MAX)), int(st.st_size), int(st.st_mtime), frame.get('rotate')]
    if moves_camera(frame):
        sig += [SUBPIXEL_TAG]
    if clip_hold(frame) > 0:
        sig += ['hold', round(clip_hold(frame), 3)]
    if clip_parts(frame):
        sig += ['parts'] + [[round(s, 3), round(d, 3)] for s, d in clip_parts(frame)]
    if frame.get('zoom_from'):
        sig += [round(float(frame['zoom_from']), 6), json.dumps(frame.get('zoom_center')), frame.get('ease', 'linear')]
    if final_still_ is not None:
        sig += [json.dumps(final_still_, sort_keys=True, ensure_ascii=False)]
    return sig


def to_part_command(cmd, dst):
    """Write to dst.part, then rename: a build stopped half-way (Ctrl-C, a killed process) would otherwise leave a
    broken segment that the next build reuses. -f mp4 is needed: ffmpeg picks the format from the extension."""
    tmp = dst + '.part'
    out = [tmp if a == dst else a for a in cmd]
    return tmp, out[:-1] + ['-f', 'mp4', out[-1]]


def usable_segment(path):
    """Existing is not the same as usable: a stopped build can leave a few dozen bytes behind."""
    try:
        return os.path.getsize(path) > 4096
    except OSError:
        return False


def render_segments(data, work_dir, photo_root=None, force=False, config=None):
    """One normalised MP4 (1920x1080, 30 fps, silent) per seat, reused when its signature is unchanged."""
    cdir = cache_dir(work_dir, config)
    segs_dir, imgs_dir = os.path.join(cdir, 'segs'), os.path.join(cdir, 'imgs')
    os.makedirs(segs_dir, exist_ok=True)
    os.makedirs(imgs_dir, exist_ok=True)
    sig_path = os.path.join(cdir, 'segments.json')
    old = {}
    if os.path.exists(sig_path) and not force:
        try:
            with open(sig_path, encoding='utf-8') as fp:
                old = json.load(fp)
        except ValueError:
            old = {}
    root = photo_root_of(data, work_dir, photo_root)
    new, segments, built, reused = {}, [], 0, 0
    for f in data['frames']:
        src = resolve_src(f, root, work_dir)
        dst = os.path.join(segs_dir, f'seg_{f["i"]:03d}.mp4')
        kind = f.get('kind', 'photo')
        final = data.get('final_still') if kind == 'final' else None
        sig = json.loads(json.dumps(signature(f, src, final)))
        new[str(f['i'])] = sig
        if not force and usable_segment(dst) and old.get(str(f['i'])) == sig:
            segments.append(dst)
            reused += 1
            continue
        if kind == 'clip':
            cmd, feed = build_clip_command(src, f, dst), None
        else:
            img = os.path.join(imgs_dir, f'img_{f["i"]:03d}.jpg')
            prepare_photo(src, img, final_still=final)
            cmd, feed = build_photo_command(img, f, dst)
        tmp, cmd = to_part_command(cmd, dst)
        try:
            run_render(cmd, feed)
        except (subprocess.CalledProcessError, OSError) as ex:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise ConfigError([f'making seat i={f["i"]} failed: {ex}', f'  file: {src}'])
        replace_file(tmp, dst)
        segments.append(dst)
        built += 1
        print(f'    i={f["i"]:3d} {kind:5s} {f["dur"]:5.2f} s  {f["src"][:56]}')
    with open(sig_path, 'w', encoding='utf-8') as fp:
        json.dump(new, fp, ensure_ascii=False, indent=1)
    print(f'  segments: {built} made, {reused} reused')
    return segments


def render_side(data, name, work_dir, photo_root=None, force=False, config=None):
    """The prologue or epilogue as one normalised MP4 with sound; reused when nothing changed."""
    side = data[name]
    cdir = cache_dir(work_dir, config)
    os.makedirs(cdir, exist_ok=True)
    dst = os.path.join(cdir, f'_{name}.mp4')
    src = resolve_src(side, photo_root_of(data, work_dir, photo_root), work_dir)
    st = os.stat(src)
    sig = [side['src'], round(float(side['dur']), 3), round(float(side.get('start_sec', 0.0)), 3),
           round(float(side.get('gain_db', 0.0)), 2), round(float(side.get('fade_in', 0.0)), 3),
           round(float(side.get('fade_out', 0.0)), 3), int(st.st_size), int(st.st_mtime), side.get('rotate')]
    sig_path = os.path.join(cdir, f'{name}.json')
    if not force and usable_segment(dst) and os.path.exists(sig_path):
        try:
            with open(sig_path, encoding='utf-8') as fp:
                if json.load(fp) == sig:
                    print(f'  {name}: reused, {float(side["dur"]):.2f} s')
                    return dst
        except ValueError:
            pass
    print(f'  {name} (with its sound): {float(side["dur"]):.2f} s  {side["src"][:56]}')
    tmp, cmd = to_part_command(build_side_command(src, side, dst), dst)
    try:
        subprocess.check_call(cmd)
    except (subprocess.CalledProcessError, OSError) as ex:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise ConfigError([f'making the {name} failed: {ex}', f'  file: {src}'])
    replace_file(tmp, dst)
    with open(sig_path, 'w', encoding='utf-8') as fp:
        json.dump(sig, fp, ensure_ascii=False)
    return dst


def build(work_dir, photo_root=None, force=False, config=None):
    data = load_config(work_dir, config)
    errors = check_sources(data, work_dir, photo_root)
    if errors:
        raise ConfigError(['the files have problems:'] + errors)
    dst = output_path(work_dir, data)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    cdir = cache_dir(work_dir, config)
    pro, epi = data.get('prologue'), data.get('epilogue')
    total = total_length(data)
    if pro or epi:
        parts = ([f'prologue {prologue_length(data):.2f} s'] if pro else []) + [f'song {data["duration_sec"]:.2f} s'] \
            + ([f'epilogue {epilogue_length(data):.2f} s'] if epi else [])
        print('  ' + ' + '.join(parts) + f' = {total:.2f} s')
    print(f'  {len(data["frames"])} seats, song {data["duration_sec"]:.2f} s')
    segments = render_segments(data, work_dir, photo_root, force=force, config=config)
    audio = os.path.join(work_dir, data['audio'])
    # With a prologue, the song part is made on its own and joined after it: its at/dur keep starting at 0.
    body = os.path.join(cdir, '_body.mp4') if (pro or epi) else dst
    print('  joining (cross-fades, song) ...')
    cmd = build_xfade_command(segments, data['frames'], audio, body, data['duration_sec'],
                              fade_in=float(pro.get('body_fade_in', 0.0)) if pro else 0.0,
                              fade_out=(float(epi.get('body_fade_out', 0.0)) if epi
                                        else float(data.get('video_fade_out', 0.0))))
    try:
        subprocess.check_call(cmd)
    except (subprocess.CalledProcessError, OSError) as ex:
        raise ConfigError([f'joining failed: {ex}'])
    if pro or epi:
        parts = ([render_side(data, 'prologue', work_dir, photo_root, force, config)] if pro else []) + [body] \
            + ([render_side(data, 'epilogue', work_dir, photo_root, force, config)] if epi else [])
        list_path = os.path.join(cdir, '_concat.txt')
        with open(list_path, 'w', encoding='utf-8') as fp:
            fp.write(concat_list_text(parts))
        print('  joining the prologue/epilogue (no re-encoding) ...')
        try:
            subprocess.check_call(build_concat_command(list_path, dst))
        except (subprocess.CalledProcessError, OSError) as ex:
            raise ConfigError([f'joining failed: {ex}'])
    normalize_loudness(dst, os.path.join(cdir, '_loudness.mp4'))
    size = fit_for_player(dst, cdir)
    info = probe_media(dst)
    if info:
        w, h, dur, _ = info
        drift = abs(dur - total)
        mark = '' if drift <= 0.5 else f'  warning: {drift:.2f} s off the definition'
        print(f'  -> {dst}  {w}x{h} {dur:.2f} s {size / 1e6:.1f} MB{mark}')
    print(f'  next: python {os.path.basename(__file__)} <work> --check, then check_smoothness.py <work>')
    return 0


# ============================================================
# --init: a first timeline
# ============================================================
def list_photos(folder):
    """Photos under a folder, sorted by date taken (then by path). Videos are left out: a clip needs a start."""
    items = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in PHOTO_EXT:
                full = os.path.join(dirpath, name)
                items.append((capture_date(full)[0], os.path.relpath(full, folder).replace('\\', '/')))
    return [rel for _d, rel in sorted(items)]


def sample_evenly(items, n):
    """n items spread evenly, in order. Too few items repeat: a repeat shows where the record is thin."""
    if n <= 0 or not items:
        return []
    if n == 1:
        return [items[len(items) // 2]]
    return [items[min(len(items) - 1, (k * len(items)) // n)] for k in range(n)]


def init_frames(duration_sec, seat_sec, sources, xfade=0.6):
    """Equal seats over the whole song, filled in order. The last seat does not cross-fade (nothing follows)."""
    n = max(1, int(round(duration_sec / seat_sec)))
    dur = round(duration_sec / n, 3)
    picks = sample_evenly(sources, n)
    frames = []
    for k in range(n):
        frames.append({'i': k + 1, 'at': round(k * dur, 3), 'dur': dur, 'xfade': xfade if k < n - 1 else 0.0,
                       'src': picks[k], 'status': 'placeholder'})
    frames[-1]['dur'] = round(duration_sec - frames[-1]['at'], 3)     # the rounding goes into the last seat
    if frames[-1]['dur'] <= xfade:
        frames[-1]['xfade'] = 0.0
    return frames


def cmd_init(work_dir, audio, photos, seat_sec, output, config=None):
    cfg = config_path(work_dir, config)
    if os.path.exists(cfg):
        raise ConfigError([f'{os.path.basename(cfg)} already exists; --init never overwrites a definition',
                           '  (move it away first if you really want to start again)'])
    audio_path = os.path.join(work_dir, audio)
    dur = probe_duration(audio_path)
    if not dur:
        raise ConfigError([f'cannot read the song: {audio_path} (put it in the work folder; ffprobe must be installed)'])
    if not os.path.isdir(photos):
        raise ConfigError([f'photo folder not found: {photos}'])
    sources = list_photos(photos)
    if not sources:
        raise ConfigError([f'no photos (.jpg .png .webp ...) under {photos}'])
    duration = round(dur, 3)
    # inside the work folder: relative (it travels with the work); elsewhere: as given (another computer: --photo-root)
    try:
        rel = os.path.relpath(photos, work_dir)
    except ValueError:                                   # another drive on Windows
        rel = '..'
    rel_root = photos if rel == '..' or rel.startswith('..' + os.sep) else rel
    data = {
        'audio': audio.replace('\\', '/'),
        'audio_sha256': sha256_of(audio_path),
        'audio_duration_sec': duration,
        'duration_sec': duration,
        'photo_root': rel_root.replace('\\', '/'),
        'output': output,
        'note': 'at/dur belong to the seats and never change when the content is replaced, moved or sorted.',
        'frames': init_frames(duration, seat_sec, sources),
    }
    errors = validate_config(data)
    if errors:
        raise ConfigError(['the new definition does not pass its own check (a bug):'] + errors)
    save_config(work_dir, data, config)
    print(f'  -> {cfg} ({len(data["frames"])} seats of about {data["frames"][0]["dur"]:.1f} s, {duration:.2f} s; '
          f'{len(sources)} photos found)')
    print('  every seat is a placeholder: the maker chooses. Next: --storyboard')
    return 0


# ============================================================
# Commands
# ============================================================
def mmss_at(sec):
    """Truncated like the storyboard, so a seat never shows two different seconds in two places."""
    m, s = divmod(int(sec), 60)
    return '%d:%02d' % (m, s)


def cmd_replace(work_dir, specs, config=None):
    data = load_config(work_dir, config)
    for spec in specs:
        m = RE_REPLACE.match(spec.strip())
        if not m:
            raise ConfigError([f'--replace takes N=FILE: {spec}', '  e.g. --replace 17=2016/bike.jpg'])
        i, src = int(m.group(1)), m.group(2).strip().strip('"')
        start = None
        m2 = RE_AT_SEC.match(src)
        if m2 and kind_for(m2.group(1)) == 'clip':
            src, start = m2.group(1), float(m2.group(2))
        f = apply_replace(data, i, src, clip_start_sec=start)
        extra = f' [video from {f["clip_start_sec"]:.1f} s]' if f.get('kind') == 'clip' else ''
        print(f'  i={i} -> {f["src"]} (at={f["at"]:.2f} dur={f["dur"]:.2f} unchanged){extra}')
        if f.get('pin'):
            print(f'     pinned seat: {f["pin"]}')
    errors = validate_config(data)
    if errors:
        raise ConfigError(['after replacing:'] + errors)
    save_config(work_dir, data, config)
    return 0


def cmd_move(work_dir, specs, config=None):
    data = load_config(work_dir, config)
    for spec in specs:
        m = RE_MOVE.match(spec.strip().strip('"'))
        if not m:
            raise ConfigError([f'--move takes N=M: {spec}', '  e.g. --move 14=2 (seat 14\'s content after seat 2), '
                               '--move 14=0 (to the front)'])
        i, after = int(m.group(1)), int(m.group(2))
        pins_before = pinned_seats(data)
        apply_move(data, i, after)
        print(f'  moved the content of {i} {"to the front" if after == 0 else f"after {after}"} '
              '(the seats\' at/dur do not move)')
        lo, hi = min(i, after or 1), max(i, after or 1)
        for n, why in pins_before.items():
            if lo <= n <= hi:                  # a pinned seat's picture changed: say so
                now = next(f for f in data['frames'] if f['i'] == n)
                print(f'     pinned seat {n} now holds {os.path.basename(now["src"])} ({why})')
    errors = validate_config(data)
    if errors:
        raise ConfigError(['after moving:'] + errors)
    save_config(work_dir, data, config)
    return 0


def cmd_sort(work_dir, spec, pin_spec, photo_root=None, config=None):
    data = load_config(work_dir, config)
    numbers = parse_numbers(spec)
    pinned = parse_numbers(pin_spec) if pin_spec else set()
    json_pins = pinned_seats(data)
    pinned |= {n for n in json_pins if n in numbers}
    known = {f['i'] for f in data['frames']}
    missing = sorted(n for n in numbers | pinned if n not in known)
    if missing:
        raise ConfigError([f'no such seats: {missing}'])
    root = photo_root_of(data, work_dir, photo_root)
    dates = {f['i']: capture_date(resolve_src(f, root, work_dir))[0] for f in data['frames'] if f['i'] in numbers}
    before = {f['i']: f['src'] for f in data['frames']}
    moved = apply_sort(data, numbers, lambda i: dates[i], pinned)
    if not moved:
        # doing nothing quietly is the hardest failure to notice
        raise ConfigError(['no seats to sort', f'  --sort {spec} --pin {pin_spec} (are the range and the pins the same?)'])
    errors = validate_config(data)
    if errors:
        raise ConfigError(['after sorting:'] + errors)
    save_config(work_dir, data, config)
    print(f'  sorted {len(moved)} seats by date taken' + (f' ({sorted(pinned)} pinned)' if pinned else ''))
    for n in sorted(pinned):
        print(f'  pinned {n}: {json_pins.get(n) or "(--pin, this time only)"}')
    for f in data['frames']:
        if f['i'] in numbers:
            shot, origin = capture_date(resolve_src(f, root, work_dir))
            mark = '' if before[f['i']] == f['src'] else '  <-'
            print('  %3d  %-11s %-8s %-30s%s' % (f['i'], shot, origin, os.path.basename(f['src'])[:30], mark))
    return 0


def cmd_status(work_dir, spec, status, config=None):
    data = load_config(work_dir, config)
    hit = apply_status(data, parse_numbers(spec), status)
    save_config(work_dir, data, config)
    print(f'  {hit} seats are now "{status}" ({spec})')
    return 0


def cmd_pins(work_dir, config=None):
    data = load_config(work_dir, config)
    pins = pinned_seats(data)
    if not pins:
        print('  no pinned seats. Pin one with: --pin-set 42="the first line of the chorus"')
        return 0
    by_i = {f['i']: f for f in data['frames']}
    print(f'  {len(pins)} pinned seats (--sort always leaves them alone)')
    for n, why in pins.items():
        print('  %3d  %s  %-30s  %s' % (n, mmss_at(by_i[n]['at']), os.path.basename(by_i[n]['src'])[:30], why))
    return 0


def cmd_pin_set(work_dir, specs, config=None):
    data = load_config(work_dir, config)
    for spec in specs:
        m = RE_PIN.match(spec.strip())
        if not m:
            raise ConfigError([f'--pin-set takes N=REASON: {spec}', '  e.g. --pin-set 42="the first line of the chorus"'])
        i, why = int(m.group(1)), m.group(2).strip().strip('"')
        before = apply_pin(data, i, why)
        print(f'  pinned {i}: {why}' + (f' (was: {before})' if before else ''))
    save_config(work_dir, data, config)
    return 0


def cmd_unpin(work_dir, spec, config=None):
    data = load_config(work_dir, config)
    numbers = parse_numbers(spec)
    missing = sorted(n for n in numbers if n not in {f['i'] for f in data['frames']})
    if missing:
        raise ConfigError([f'no such seats: {missing}'])
    for n in sorted(numbers):
        before = apply_unpin(data, n)
        print(f'  unpinned {n} ({before})' if before else f'  {n} was not pinned')
    save_config(work_dir, data, config)
    return 0


def cmd_check(work_dir, photo_root=None, config=None):
    data = load_config(work_dir, config)
    errors = check_sources(data, work_dir, photo_root)
    placeholders = sum(1 for f in data['frames'] if f.get('status', 'placeholder') == 'placeholder')
    print(f'  definition: OK ({len(data["frames"])} seats, song {data["duration_sec"]:.2f} s, '
          f'{placeholders} placeholders)')
    for name in ('prologue', 'epilogue'):
        if data.get(name):
            print(f'  {name}: {float(data[name]["dur"]):.2f} s with its sound  {data[name]["src"]}')
    total = total_length(data)
    if data.get('audio_sha256'):
        print(f'  song fingerprint: OK {data["audio_sha256"][:16]}...')
    out = output_path(work_dir, data)
    if os.path.exists(out):
        info = probe_media(out)
        size = os.path.getsize(out)
        if info:
            w, h, dur, _ = info
            ok = (w, h) == (OUT_W, OUT_H) and abs(dur - total) <= 0.5 and size <= MAX_VIDEO_BYTES
            print(f'  video: {"OK" if ok else "NG"} {w}x{h} {dur:.2f} s {size / 1e6:.1f} MB')
            if not ok:
                errors.append(f'the video is not as defined, or too large for the room player: '
                              f'{w}x{h} {dur:.2f} s {size / 1e6:.1f} MB')
    else:
        print('  video: not built yet')
    pins = pinned_seats(data)
    if pins:
        print(f'  pinned seats: {", ".join(str(n) for n in pins)} (reasons: --pins)')
    errors += check_storyboard_fresh(work_dir, data, photo_root, config)
    for e in errors:
        print('  x ' + e)
    return 1 if errors else 0


def storyboard_baseline(work_dir, data, photo_root=None, config=None):
    """The time the storyboard must be newer than: the definition, and every file it shows (a picture redrawn
    under the same name changes nothing in the definition)."""
    cfg = config_path(work_dir, config)
    if not os.path.exists(cfg):
        return None
    base = os.path.getmtime(cfg)
    root = photo_root_of(data, work_dir, photo_root)
    items = list(data.get('frames') or []) + [data[k] for k in ('prologue', 'epilogue') if isinstance(data.get(k), dict)]
    for f in items:
        if isinstance(f, dict) and isinstance(f.get('src'), str):
            try:
                base = max(base, os.path.getmtime(resolve_src(f, root, work_dir)))
            except OSError:
                pass
    return base


def check_storyboard_fresh(work_dir, data, photo_root=None, config=None):
    """The storyboard is what the maker looks at to point at seats. An old one makes them point at old pictures."""
    base = storyboard_baseline(work_dir, data, photo_root, config)
    if base is None:
        return []
    out = []
    for p, label in zip(storyboard_paths(work_dir, config), ('storyboard JPEG', 'storyboard page')):
        if not os.path.exists(p):
            print(f'  {label}: not made yet')
        elif os.path.getmtime(p) < base:
            out.append(f'the {label} is older than the definition or its files: run --storyboard again')
        else:
            print(f'  {label}: OK')
    return out


# ---------- the storyboard ----------

def thumbnail(path, box, is_clip=False, tmp_dir=None, at_sec=1.0, rotate=None):
    """One thumbnail; for a video, the frame at `at_sec` of the source, turned like the finished video."""
    from PIL import Image, ImageOps
    if is_clip:
        tmp = os.path.join(tmp_dir or os.curdir, '_thumb.jpg')
        os.makedirs(os.path.dirname(tmp) or '.', exist_ok=True)
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-max_error_rate', '1',
               '-ss', '%.3f' % max(0.0, float(at_sec)), '-i', path, '-frames:v', '1']
        if rotate:
            cmd += ['-vf', ROTATIONS[rotate]]
        subprocess.call(cmd + [tmp])
        path = tmp
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        return ImageOps.contain(im, box, method=Image.LANCZOS)


def storyboard_cells(data):
    """Everything that will be on screen, in order: P (prologue), the seats, E (epilogue)."""
    pro, epi = data.get('prologue'), data.get('epilogue')
    return (([dict(pro, i='P', at=0.0, kind='clip', clip_start_sec=float(pro.get('start_sec', 0.0)))] if pro else [])
            + list(data['frames'])
            + ([dict(epi, i='E', at=float(data['duration_sec']), kind='clip',
                     clip_start_sec=float(epi.get('start_sec', 0.0)))] if epi else []))


def make_storyboard(work_dir, data, photo_root=None, cols=6, thumb=320, config=None, mark=None):
    """The storyboard JPEG and its page, always together (an old page next to a new JPEG makes the maker point at
    old pictures). mark: seat numbers to open the page with already pointed at (from a correction sheet)."""
    pointed = sorted(mark or [])        # `mark` is reused below for each seat's status letter
    if pointed:
        seats = {f['i'] for f in data['frames']}
        unknown = sorted(set(pointed) - seats)
        if unknown:
            raise ConfigError([f'--mark: no seat {", ".join(map(str, unknown))} (seats are 1-{len(seats)})'])
    from PIL import Image, ImageDraw
    font = label_font()
    root = photo_root_of(data, work_dir, photo_root)
    cells = storyboard_cells(data)
    cell = (thumb, thumb * 3 // 4)
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell[0], rows * (cell[1] + 26)), '#111')
    draw = ImageDraw.Draw(sheet)
    tmp_dir = cache_dir(work_dir, config)
    for k, f in enumerate(cells):
        full = resolve_src(f, root, work_dir)
        cx, cy = (k % cols) * cell[0], (k // cols) * (cell[1] + 26)
        try:
            t = thumbnail(full, cell, is_clip=(f.get('kind') == 'clip'), tmp_dir=tmp_dir,
                          at_sec=clip_thumb_sec(f), rotate=f.get('rotate'))
            sheet.paste(t, (cx + (cell[0] - t.width) // 2, cy + (cell[1] - t.height) // 2))
            shot, origin = capture_label(full)
        except Exception:
            shot, origin = 'missing', ''
        mark = {'placeholder': '.', 'picked': 'o', 'confirmed': '*'}.get(f.get('status', 'placeholder'), '.')
        when = {'P': 'before', 'E': 'after'}.get(f['i']) or mmss_at(f['at'])
        draw.text((cx + 4, cy + cell[1] + 5),
                  f'{mark}{f["i"]:>3}  {when}  {f["dur"]:.1f}s  {shot}' + (f' ({origin})' if origin not in ('EXIF', '') else ''),
                  fill='#ddd', font=font)
    out = storyboard_paths(work_dir, config)[0]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out, quality=88)
    print(f'  -> {out} ({len(cells)} cells)')
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import storyboard_page
    storyboard_page.make_page(work_dir, data, photo_root=photo_root, config=config, mark=pointed)
    opt = f'--config {config} ' if config else ''
    print(f'  to replace a seat: {opt}--replace 17=2016/bike.jpg')
    return 0


# ============================================================
# Entry
# ============================================================
def main(argv=None):
    parser = argparse.ArgumentParser(description='Build an ending video: photos and videos on one song.')
    parser.add_argument('work', help='the work folder (it holds ending_video.json)')
    parser.add_argument('--config', help='the name of a second definition (ending_video_NAME.json)')
    parser.add_argument('--photo-root', help='the photo folder on this computer (overrides photo_root)')
    act = parser.add_mutually_exclusive_group()
    act.add_argument('--init', action='store_true', help='make a first definition (with --audio and --photos)')
    act.add_argument('--check', action='store_true', help='check the definition and its files')
    act.add_argument('--storyboard', action='store_true', help='make the storyboard (JPEG and page)')
    act.add_argument('--replace', action='append', metavar='N=FILE[@SEC]', help='put another file in seat N')
    act.add_argument('--move', action='append', metavar='N=M', help='move the content of seat N after seat M')
    act.add_argument('--sort', metavar='RANGE', help='sort these seats by date taken')
    act.add_argument('--pin-set', action='append', metavar='N=REASON', help='pin a seat, with the reason')
    act.add_argument('--unpin', metavar='RANGE')
    act.add_argument('--pins', action='store_true', help='list the pinned seats')
    act.add_argument('--pick', metavar='RANGE', help='mark seats as picked')
    act.add_argument('--confirm', metavar='RANGE', help='mark seats as confirmed')
    parser.add_argument('--pin', metavar='RANGE', help='with --sort: also leave these seats alone this time')
    parser.add_argument('--mark', metavar='RANGE', help='with --storyboard: open the page with these seats already '
                                                        'pointed at (the seats of a correction sheet)')
    parser.add_argument('--audio', help='with --init: the song, relative to the work folder')
    parser.add_argument('--photos', help='with --init: the folder of photos to start from')
    parser.add_argument('--seat', type=float, default=5.0, help='with --init: seconds per seat (default 5)')
    parser.add_argument('--output', default='ending.mp4', help='with --init: the video\'s file name in videos/')
    parser.add_argument('--force', action='store_true', help='make every segment again')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # a Japanese Windows console cannot show every character
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')

    work_dir = os.path.abspath(args.work)
    if not os.path.isdir(work_dir):
        print(f'error: work folder not found: {args.work}', file=sys.stderr)
        return 2
    if args.config is not None and not RE_CONFIG.match(args.config):
        print(f'error: --config {args.config!r}: letters, digits, _ and - only', file=sys.stderr)
        return 2
    print(f'ending video: {os.path.basename(work_dir)}' + (f' [{args.config}]' if args.config else ''))
    cfg, root = args.config, args.photo_root
    try:
        if args.init:
            if not args.audio or not args.photos:
                raise ConfigError(['--init needs --audio (the song in the work folder) and --photos (a folder)'])
            if args.seat <= 0:
                raise ConfigError(['--seat must be more than 0'])
            return cmd_init(work_dir, args.audio, os.path.abspath(args.photos), args.seat, args.output, cfg)
        if args.replace:
            return cmd_replace(work_dir, args.replace, cfg)
        if args.move:
            return cmd_move(work_dir, args.move, cfg)
        if args.sort:
            return cmd_sort(work_dir, args.sort, args.pin, root, cfg)
        if args.pin_set:
            return cmd_pin_set(work_dir, args.pin_set, cfg)
        if args.unpin:
            return cmd_unpin(work_dir, args.unpin, cfg)
        if args.pins:
            return cmd_pins(work_dir, cfg)
        if args.pick:
            return cmd_status(work_dir, args.pick, 'picked', cfg)
        if args.confirm:
            return cmd_status(work_dir, args.confirm, 'confirmed', cfg)
        if args.check:
            return cmd_check(work_dir, root, cfg)
        if args.mark and not args.storyboard:
            raise ConfigError(['--mark goes with --storyboard'])
        if args.storyboard:
            return make_storyboard(work_dir, load_config(work_dir, cfg), photo_root=root, config=cfg,
                                   mark=sorted(parse_numbers(args.mark)) if args.mark else None)
        return build(work_dir, root, force=args.force, config=cfg)
    except ConfigError as ex:
        for line in ex.messages:
            print('  ' + line, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
