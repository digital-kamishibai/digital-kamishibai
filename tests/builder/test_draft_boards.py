"""Tests for skills/digital-kamishibai/scripts/draft_boards.py (plain boards for a first draft)."""
import importlib.util
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'skills' / 'digital-kamishibai' / 'scripts'
_spec = importlib.util.spec_from_file_location('draft_boards', SCRIPTS / 'draft_boards.py')
db = importlib.util.module_from_spec(_spec)
sys.modules['draft_boards'] = db
_spec.loader.exec_module(db)

SCRIPT = """# Boards

> Language: en

## [Slide 1] Cover

Once.

---

## [Slide 2] Has a picture

Twice.

---

## [Slide 3] Named picture
> [Picture] pictures/lamp.png

Three times.

---

## [Slide 4] A video
> [Video] videos/sea.mp4

Four times.

---
"""


def work(tmp_path):
    (tmp_path / 'script.md').write_text(SCRIPT, encoding='utf-8')
    (tmp_path / 'pictures').mkdir()
    (tmp_path / 'pictures' / '02.jpg').write_bytes(b'not really a picture')
    (tmp_path / 'videos').mkdir()
    (tmp_path / 'videos' / 'sea.mp4').write_bytes(b'')
    return tmp_path


def test_only_slides_without_a_picture_get_a_board(tmp_path):
    w = work(tmp_path)
    assert db.missing_pictures(w) == ['pictures/01.png', 'pictures/lamp.png']


def test_check_writes_nothing(tmp_path, capsys):
    w = work(tmp_path)
    assert db.main([str(w), '--check']) == 0
    assert not (w / 'pictures' / '01.png').exists()
    assert '2 board(s) to place' in capsys.readouterr().out


def test_boards_are_placed_and_existing_pictures_kept(tmp_path):
    w = work(tmp_path)
    assert db.main([str(w)]) == 0
    assert (w / 'pictures' / '02.jpg').read_bytes() == b'not really a picture'
    for name in ('01.png', 'lamp.png'):
        data = (w / 'pictures' / name).read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n'
        width, height, depth, colour = struct.unpack('>IIBB', data[16:26])
        assert (width, height, depth, colour) == (1600, 900, 8, 2)   # 16:9, RGB, no alpha
    assert db.missing_pictures(w) == []


def test_board_pixels(tmp_path):
    data = db.board_png()
    idat = data[data.index(b'IDAT') + 4:data.index(b'IEND') - 8]
    raw = zlib.decompress(idat)
    stride = 1 + 1600 * 3
    px = lambda x, y: tuple(raw[y * stride + 1 + x * 3:y * stride + 1 + x * 3 + 3])
    assert px(0, 0) == db.BOARD
    assert px(800, 450) == db.BOARD
    assert px(800, db.EDGE_AT) == db.EDGE          # the frame
    assert px(db.EDGE_AT + 2, 450) == db.EDGE
