#!/usr/bin/env python3
"""Check that this computer has what the Digital Kamishibai tools need. It only looks: nothing is installed or changed.

    python doctor.py                                  # the basic path: build a work and draw the words on the screen
    python doctor.py --for basic --for ending-video   # what a maker who builds works and ending videos needs
    python doctor.py --for pictures --for claude      # the picture ladder (paid) and Claude Code
    python doctor.py --for codex                      # Codex instead of Claude Code

    basic          Python 3.10+; Microsoft Edge or Google Chrome (to draw [Text] into the pictures)
    ending-video   Pillow, ffmpeg and ffprobe (ladder/ending-video)
    pictures       Pillow and a Gemini API key in GEMINI_API_KEY (ladder/images; paid; the key holder runs it)
    claude         the `claude` command (Claude Code)
    codex          the `codex` command (Codex)

Exit code 0 when everything asked for is there, 1 when something is missing (each by name, with what it is for).
The key's value is never printed: only whether it is set. Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                      # skills/digital-kamishibai/scripts -> the repository
NEEDS = ('basic', 'ending-video', 'pictures', 'claude', 'codex')


def check_python():
    ok = sys.version_info >= (3, 10)
    return ok, f'Python {sys.version.split()[0]}', 'Python 3.10 or later (python.org)'


def check_browser():
    sys.path.insert(0, str(HERE))
    try:
        import burn
        found = burn.find_browser()
    except Exception:                       # noqa: BLE001  (a broken import is "not found" here)
        found = None
    return bool(found), (found or 'none'), 'Microsoft Edge or Google Chrome (draws the words on the screen)'


def check_pillow():
    ok = importlib.util.find_spec('PIL') is not None
    return ok, 'Pillow' if ok else 'none', 'Pillow: python -m pip install pillow'


def check_program(name, purpose):
    path = shutil.which(name)
    if not path:
        return False, 'none', f'{name} on the PATH ({purpose})'
    try:
        out = subprocess.run([path, '-version'], capture_output=True, text=True, errors='replace', timeout=20)
        first = (out.stdout or out.stderr).strip().splitlines()[0][:60]
    except (OSError, subprocess.SubprocessError, IndexError):
        first = path
    return True, first, f'{name} on the PATH ({purpose})'


def check_key():
    ok = bool(os.environ.get('GEMINI_API_KEY', '').strip())
    return ok, 'set' if ok else 'not set', 'GEMINI_API_KEY in this computer\'s environment (never in a file)'


def check_command(name, what):
    path = shutil.which(name)
    return bool(path), (path or 'none'), f'{what} (the `{name}` command)'


def check_file(rel, purpose):
    ok = (REPO / rel).is_file()
    return ok, rel if ok else 'not found', f'{rel} ({purpose}); get the whole repository again'


def checks_for(need):
    if need == 'basic':
        return [('Python', check_python), ('Builder', lambda: check_file(
                    'skills/digital-kamishibai/scripts/build_work.py', 'builds a work')),
                ('Browser', check_browser)]
    if need == 'ending-video':
        return [('Pillow', check_pillow),
                ('ffmpeg', lambda: check_program('ffmpeg', 'makes the video')),
                ('ffprobe', lambda: check_program('ffprobe', 'reads videos and songs')),
                ('Ending-video ladder', lambda: check_file('ladder/ending-video/build_ending_video.py', 'the tool'))]
    if need == 'pictures':
        return [('Pillow', check_pillow), ('Gemini API key', check_key),
                ('Picture ladder', lambda: check_file('ladder/images/gen_images.py', 'the tool'))]
    if need == 'claude':
        return [('Claude Code', lambda: check_command('claude', 'Claude Code'))]
    if need == 'codex':
        return [('Codex', lambda: check_command('codex', 'Codex'))]
    raise ValueError(need)


def run(needs):
    """[(need, name, ok, found, what)] without repeats (Pillow is asked by two needs)."""
    seen, rows = set(), []
    for need in needs:
        for name, check in checks_for(need):
            if name in seen:
                continue
            seen.add(name)
            ok, found, what = check()
            rows.append((need, name, ok, found, what))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check this computer for the Digital Kamishibai tools (installs nothing).')
    parser.add_argument('--for', dest='needs', action='append', choices=NEEDS,
                        help='what to check for (repeatable; default: basic)')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    needs = args.needs or ['basic']
    rows = run(needs)
    missing = [r for r in rows if not r[2]]
    for need, name, ok, found, _what in rows:
        print(f'  {"ok     " if ok else "MISSING"}  {name:20s} {found}  [{need}]')
    if missing:
        print('\nMissing (nothing was installed):')
        for _need, name, _ok, _found, what in missing:
            print(f'  - {name}: {what}')
        return 1
    print('\nEverything for ' + ', '.join(needs) + ' is here.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
