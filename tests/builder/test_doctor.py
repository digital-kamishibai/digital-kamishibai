"""Tests for skills/digital-kamishibai/scripts/doctor.py: it names what is missing and never prints a key."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('doctor', ROOT / 'skills' / 'digital-kamishibai' / 'scripts' / 'doctor.py')
doctor = importlib.util.module_from_spec(_spec)
sys.modules['doctor'] = doctor
_spec.loader.exec_module(doctor)

KEY = 'secret-key-0123456789'


def test_the_tools_of_this_repository_are_found():
    for rel in ('skills/digital-kamishibai/scripts/build_work.py', 'ladder/ending-video/build_ending_video.py',
                'ladder/images/gen_images.py'):
        assert doctor.check_file(rel, 'x')[0]


def test_missing_things_are_named_and_the_exit_code_says_so(monkeypatch, capsys):
    monkeypatch.setattr(doctor.shutil, 'which', lambda name: None)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    assert doctor.main(['--for', 'ending-video', '--for', 'pictures', '--for', 'claude', '--for', 'codex']) == 1
    out = capsys.readouterr().out
    for name in ('ffmpeg', 'ffprobe', 'Gemini API key', 'Claude Code', 'Codex'):
        assert f'- {name}:' in out
    assert 'nothing was installed' in out
    assert sum(1 for line in out.splitlines() if ' Pillow ' in line) == 1   # asked by two needs, checked once


def test_the_key_is_never_printed(monkeypatch, capsys):
    monkeypatch.setenv('GEMINI_API_KEY', KEY)
    doctor.main(['--for', 'pictures'])
    out = capsys.readouterr().out
    assert KEY not in out and 'set' in out


def test_default_is_the_basic_path(monkeypatch, capsys):
    monkeypatch.setattr(doctor, 'check_browser', lambda: (True, 'edge', 'browser'))
    assert doctor.main([]) == 0
    assert '[basic]' in capsys.readouterr().out


def test_unknown_need_is_refused():
    with pytest.raises(SystemExit):
        doctor.main(['--for', 'everything'])


def test_codex_is_found_by_its_command(monkeypatch, capsys):
    monkeypatch.setattr(doctor.shutil, 'which', lambda name: '/bin/codex' if name == 'codex' else None)
    assert doctor.main(['--for', 'codex']) == 0
    assert '/bin/codex' in capsys.readouterr().out
