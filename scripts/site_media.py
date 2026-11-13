"""サイトの見本の目録（examples/<slug>/<lang>/site.json）を作り、Release `site-media` に上げるファイルをそろえる。
定義は docs/work-format.md §1「Samples on the site」。取り込みは scripts/fetch-samples.mjs。

    python scripts/site_media.py <素材のある見本のフォルダ> examples/<slug>/<lang>

- 台本（work.json・script.md）と穴の手引き（holes.md。段3の「AI に相談」が読む）と絵のプロンプト（plan.md。段4a の
  「AI と台本を書く」が絵の説明を読む）は examples/<slug>/<lang>/ から
  （改行を LF にそろえる）。素材は見本のフォルダから。
  載せるのは work.json が指す絵・音・動画だけ
- 25 MiB を超える動画は 720p・H.264 約1.0Mbps の2パスで作り直す。音は作り直さず写す（作り直すと音が悪くなった）。
  作り直したものは元の SHA-256 で .cache/site-media/encoded/ に残し、2回目からは作り直さない（x264 は毎回同じ
  バイトになるとは限らないので、作り直すたびに版が上がってしまう）
- BGM の大きさ（LUFS）を ffmpeg の ebur128 で量り、目録の levels に書く（語り手が曲を丸ごと読み解かずに済む）
- 前の版と1つでも違えば版を1つ上げて足す。同じなら目録を変えない。古い版は消さない（サイトの版は増えるだけ）
- 上げるファイルは .cache/site-media/<SHA-256>.<拡張子>。最後に、上げるコマンドを出す（公開用への書き込みは持ち主が打つ）
ffmpeg が要る。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'site-media'
MAX_FILE = 25 * 1024 * 1024
REPO = 'digital-kamishibai/digital-kamishibai'
TAG = 'site-media'


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def text_bytes(p):
    return p.read_bytes().replace(b'\r\n', b'\n')


def media_paths(work):
    """work.json が指す絵・音・動画のパス（重ねずに、出てくる順）"""
    out = []
    for s in work['slides']:
        if s.get('picture'):
            out.append(s['picture'])
        for c in s.get('cues', []):
            if c.get('file'):
                out.append(c['file'])
    return list(dict.fromkeys(out))


def bgm_paths(work):
    return list(dict.fromkeys(c['file'] for s in work['slides'] for c in s.get('cues', [])
                              if c.get('type') == 'bgm' and c.get('file')))


def encode_video(src, path):
    """25 MiB を超える動画を 720p で作り直す（元の SHA-256 で覚えておく）"""
    key = sha256(src.read_bytes())
    out = CACHE / 'encoded' / f'{key}.mp4'
    if out.exists():
        print(f'{path}: over 25 MiB — using the 720p copy made before')
        return out
    print(f'{path}: over 25 MiB — making a 720p copy')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, 'pass')
        common = ['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-vf', 'scale=-2:720:flags=lanczos',
                  '-c:v', 'libx264', '-preset', 'slow', '-b:v', '1000k', '-pix_fmt', 'yuv420p',
                  '-profile:v', 'high', '-g', '60', '-passlogfile', log]
        subprocess.run(common + ['-pass', '1', '-an', '-f', 'mp4', os.devnull], check=True)
        part = os.path.join(tmp, 'out.mp4')
        subprocess.run(common + ['-pass', '2', '-c:a', 'copy', '-movflags', '+faststart', part], check=True)
        shutil.move(part, out)
    return out


def loudness(src):
    """統合ラウドネス（LUFS）。ffmpeg の ebur128 の Summary の I:"""
    r = subprocess.run(['ffmpeg', '-nostats', '-hide_banner', '-i', str(src), '-af', 'ebur128', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    hits = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)
    if r.returncode or not hits:
        raise SystemExit(f'ffmpeg could not measure {src}')
    return round(float(hits[-1]), 1)


def stage(path, data):
    """上げるファイルを .cache/site-media/<SHA-256>.<拡張子> に置き、目録の1行を返す"""
    h = sha256(data)
    ext = os.path.splitext(path)[1].lower()
    dest = CACHE / f'{h}{ext}'
    if not dest.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return {'path': path, 'size': len(data), 'sha256': h}, dest


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('media', type=Path, help='素材のある見本のフォルダ（公開用の zip を解凍したもの）')
    ap.add_argument('example', type=Path, help='examples/<slug>/<lang>')
    a = ap.parse_args()
    ex = a.example.resolve()
    work = json.loads((ex / 'work.json').read_text(encoding='utf-8'))

    files, staged = [], []
    for name in ('work.json', 'script.md', 'holes.md', 'plan.md'):
        if (ex / name).exists():
            row, dest = stage(name, text_bytes(ex / name))
            files.append(row)
            staged.append(dest)
    for p in media_paths(work):
        src = a.media / p
        if not src.is_file():
            raise SystemExit(f'missing in {a.media}: {p}')
        if src.suffix.lower() == '.mp4' and src.stat().st_size > MAX_FILE:
            src = encode_video(src, p)
        data = src.read_bytes()
        if len(data) > MAX_FILE:
            raise SystemExit(f'{p}: still over 25 MiB ({len(data)} bytes)')
        row, dest = stage(p, data)
        files.append(row)
        staged.append(dest)
    levels = {p: loudness(a.media / p) for p in bgm_paths(work)}

    site_file = ex / 'site.json'
    site = json.loads(site_file.read_text(encoding='utf-8')) if site_file.exists() else {'card': {'line': ''}, 'versions': []}
    new = {'files': files, 'levels': levels} if levels else {'files': files}
    last = site['versions'][-1] if site['versions'] else None
    if last and last['files'] == files and last.get('levels') == new.get('levels'):
        print(f'{site_file.relative_to(ROOT)}: no change (version {last["version"]})')
    else:
        site['versions'].append({'version': len(site['versions']) + 1, **new})
        site_file.write_text(json.dumps(site, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(f'{site_file.relative_to(ROOT)}: version {len(site["versions"])}')

    names = ' '.join(f'.cache/site-media/{d.name}' for d in staged)
    print('\nUpload (the owner runs it in PowerShell, as digital-kamishibai-team; files already there are the same bytes):')
    print('  $env:GH_TOKEN = gh auth token --user digital-kamishibai-team')
    print(f'  gh release upload {TAG} -R {REPO} --clobber {names}')
    print('  Remove-Item Env:GH_TOKEN')


if __name__ == '__main__':
    main()
