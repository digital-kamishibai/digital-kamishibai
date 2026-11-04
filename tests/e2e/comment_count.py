"""ひとことの数え方を、語り手の画面で確かめる（手で動かす確認。Edge が要る）:
    python tests/e2e/comment_count.py [作業フォルダ]
 見本の写しで、1枚目にひとことを書く → 「修正票（未反映 1）」→ 同じ作品のまま読み直しても未反映 →
台本を直して作り直し、読み直す → 「未反映 0・見て消す 1」・一覧に「作品が変わった（見て消す）」・自分では消えない。
ひとことはプレイヤーが判定できないので、書いたときの作品のしるし（workSig）と、読み直した作品のしるしで数える（2026-10-26）。
作業用リポジトリの見本は変えない（写しで行う）。"""
import argparse
import base64
import functools
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser()
ap.add_argument('here', nargs='?', help='作業フォルダ（写し・撮った画面）。無ければ一時フォルダ')
args = ap.parse_args()
for stream in (sys.stdout, sys.stderr):        # 日本語の Windows のコンソールでは出せない文字がある（— など）
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
HERE = Path(args.here).resolve() if args.here else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
WORK = HERE / 'rt' / 'work'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
CHECK = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'check_sheet.py'
GEN = REPO / 'ladder' / 'images' / 'gen_images.py'

def run(*a):
    r = subprocess.run([PY, *map(str, a)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert r.returncode == 0, r.stdout + r.stderr


shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
run(BUILD, WORK, '--draft', '--skip-text')
site = HERE / 'rt' / 'site'
shutil.copytree(REPO / 'player', site / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(HERE / 'rt')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'


def listing():
    return [{'url': '/' + p.relative_to(HERE / 'rt').as_posix(), 'rel': p.relative_to(WORK.parent).as_posix(),
             'mtime': int(p.stat().st_mtime * 1000)} for p in WORK.rglob('*') if p.is_file()]


PICK = """(async (inputId, files) => {
  const list = [];
  for (const f of files) {
    const blob = await (await fetch(f.url, { cache: 'no-store' })).blob();
    const file = new File([blob], f.rel.split('/').pop(), { lastModified: f.mtime });
    Object.defineProperty(file, 'webkitRelativePath', { value: f.rel });
    list.push(file);
  }
  const input = document.getElementById(inputId);
  Object.defineProperty(input, 'files', { value: list, configurable: true });
  input.dispatchEvent(new Event('change'));
  return true;
})"""
b = burn.Browser(burn.find_browser())
ev = b.evaluate


def wait(js, what, tries=600):
    for _ in range(tries):
        try:
            if ev(js):
                return
        except burn.BurnError:
            pass
        time.sleep(0.05)
    raise SystemExit(f'timeout: {what}')


btn = lambda: ev("document.getElementById('sheetBtn').textContent")
try:
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); true")
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    ev("document.getElementById('editBtn').click(); true")
    time.sleep(0.3)
    ev("document.getElementById('editComment').value = 'the music ends with applause'; document.getElementById('editDone').click(); true")
    time.sleep(0.3)
    print('1. ひとことを書いた:', btn())
    assert btn() in ('修正票（未反映 1）', 'Correction sheet (1 not done)'), btn()
    # 同じ作品のまま読み直しても未反映のまま
    ev("document.getElementById('reloadNote').textContent = ''; true")
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('2. 同じ作品で読み直した:', btn())
    assert btn() in ('修正票（未反映 1）', 'Correction sheet (1 not done)'), btn()
    # 書き戻して作り直したことにする（別の枚の台本を直す）→ 作品が変わったので見て消す
    s = (WORK / 'script.md').read_text(encoding='utf-8')
    s = s.replace('And the lamp went out.', 'And then the lamp went out.', 1)
    (WORK / 'script.md').write_text(s, encoding='utf-8')
    run(BUILD, WORK, '--draft', '--skip-text')
    ev("document.getElementById('reloadNote').textContent = ''; true")
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('3. 作品が変わって読み直した:', btn())
    assert btn() in ('修正票（未反映 0・見て消す 1）', 'Correction sheet (0 not done · 1 to check)'), btn()
    ev("document.getElementById('sheetBtn').click(); true")
    time.sleep(0.3)
    lst = ev("document.getElementById('sheetList').innerText")
    print('   一覧:', lst.replace('\n', ' | '))
    assert 'ひとことを書いたあと、作品が変わった' in lst or 'the work has changed' in lst
    assert 'the music ends with applause' in lst, '自分では消さない'
    # 前回のひとことの枚で語りを直す（2026-10-29 実際の作品で）: ひとことの欄は空・前回のひとことは別の行に出る。
    # 欄に触れずに閉じても、前回のひとことは今回の直しの Comment: にならない
    ev("document.getElementById('editBtn').click(); true")
    time.sleep(0.3)
    assert ev("document.getElementById('editComment').value") == '', '前回のひとことを欄に入れない'
    assert not ev("document.getElementById('editOldComment').hidden"), '前回のひとことの行が出る'
    assert ev("document.getElementById('editOldText').textContent") == 'the music ends with applause'
    ev("const n = document.getElementById('editNotes'); n.value = n.value + '\\n\\nOne more line.'; document.getElementById('editDone').click(); true")
    time.sleep(0.3)
    print('4. 前回のひとことの枚で語りを直した:', btn())
    assert btn() in ('修正票（未反映 1・見て消す 1）', 'Correction sheet (1 not done · 1 to check)'), btn()
    ev("window.__md = null; navigator.clipboard.writeText = async (t) => { window.__md = t; }; true")
    ev("document.getElementById('sheetCopy').click(); true")
    wait("window.__md !== null", 'copied')
    md = ev('window.__md')
    print('   修正票:', md.replace('\n', ' | '))
    assert 'One more line.' in md and 'the music ends with applause' not in md, md
    # 新しく書けば、今回の直しの理由になる
    ev("document.getElementById('editBtn').click(); true")
    time.sleep(0.3)
    ev("document.getElementById('editComment').value = 'slower here'; document.getElementById('editDone').click(); true")
    time.sleep(0.3)
    ev("window.__md = null; document.getElementById('sheetCopy').click(); true")
    wait("window.__md !== null", 'copied again')
    md = ev('window.__md')
    assert 'Comment: slower here' in md and 'the music ends with applause' not in md, md
    print('5. 書き替えたひとことは今回の直しに付く:', btn())
    assert not ev('window.__errs')
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
