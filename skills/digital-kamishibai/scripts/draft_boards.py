#!/usr/bin/env python3
"""Put a plain board on every slide that has no picture yet, so a first draft can be practised in the room player.

    python draft_boards.py <work folder>            # place the boards
    python draft_boards.py <work folder> --check    # only list what would be placed

It reads script.md with build_work.py (next to this file) and writes pictures/NN.png — a plain, light board — only where
no picture is found. The slide title is not painted on the board: the script's `> [Text]` is drawn on it by the build.

- Pictures already in place (photos, a child's drawing, generated pictures) are never touched.
- A video slide (no picture line, a `[Video]`) gets no board: the player shows the video's first frame.
- The real pictures come later, once the script has settled (a `picture` correction from practice;
  references/correction-sheet.md). When a generated candidate is chosen with `--use`, the board moves to
  pictures/_replaced/.

Standard library only, like the builder.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_work  # noqa: E402

SIZE = (1600, 900)            # 16:9, the player's screen
BOARD = (238, 232, 220)       # off-white: dark words on it stay readable
EDGE = (214, 206, 190)
EDGE_AT, EDGE_WIDTH = 24, 6   # a thin frame, so a board is not mistaken for a broken picture


def missing_pictures(work: Path) -> list[str]:
    """The pictures to place, relative to the work folder."""
    result = build_work.Result()
    parsed = build_work.parse_script((work / 'script.md').read_text(encoding='utf-8'), result)
    if parsed is None:
        raise SystemExit('error: the script cannot be read:\n  ' + '\n  '.join(result.errors))
    build_work.resolve_media(parsed, work, result)
    out = []
    for slide in parsed['slides']:
        pic = slide['picture']
        if pic is None or (work / pic).is_file():
            continue
        path = Path(pic)
        if path.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
            continue
        # The default name (pictures/NN.jpg) is placed as .png; a name the script gives is kept.
        out.append(path.with_suffix('.png').as_posix() if pic == build_work.default_picture(slide['number']) else pic)
    return out


def board_png() -> bytes:
    """A plain board with a thin frame, as a PNG (8-bit RGB, no alpha)."""
    w, h = SIZE
    inner = bytes(BOARD) * w
    framed = bytes(BOARD) * EDGE_AT + bytes(EDGE) * EDGE_WIDTH + bytes(BOARD) * (w - 2 * (EDGE_AT + EDGE_WIDTH)) \
        + bytes(EDGE) * EDGE_WIDTH + bytes(BOARD) * EDGE_AT
    edge = bytes(BOARD) * EDGE_AT + bytes(EDGE) * (w - 2 * EDGE_AT) + bytes(BOARD) * EDGE_AT
    rows = []
    for y in range(h):
        if y < EDGE_AT or y >= h - EDGE_AT:
            row = inner
        elif y < EDGE_AT + EDGE_WIDTH or y >= h - EDGE_AT - EDGE_WIDTH:
            row = edge
        else:
            row = framed
        rows.append(b'\x00' + row)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):   # a console that cannot show a character must not stop the tool
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('work', type=Path, help='the work folder (where script.md is)')
    ap.add_argument('--check', action='store_true', help='only list what would be placed')
    args = ap.parse_args(argv)
    if not (args.work / 'script.md').is_file():
        print(f'error: no script.md in {args.work}', file=sys.stderr)
        return 1
    todo = missing_pictures(args.work)
    png = None if args.check else board_png()
    done = 0
    for rel in todo:
        if not rel.lower().endswith('.png'):
            print(f'skip {rel}: a board is a PNG; name the picture .png in the script, or put a picture there yourself')
            continue
        if png is not None:
            target = args.work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
        print(('would place ' if args.check else 'placed ') + rel)
        done += 1
    print(f'{done} board(s)' + (' to place' if args.check else ' placed'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
