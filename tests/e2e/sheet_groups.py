"""修正票の見出しとボタンの数が合うかを、語り手の画面で確かめる（手で動かす確認。Edge が要る）:
    python tests/e2e/sheet_groups.py [作業フォルダ]
 見本の写しで、2枚目と3枚目の台本を直し、2枚目にひとことを書く → 一覧は「未反映 2件」の見出しの下に2件・ひとことも見える →
2枚目だけ書き戻して作り直し → ページを開き直して「作品を選ぶ」から開く（読み直すではない）→ 反映済みの2枚目は消え、
ボタン「未反映 1」と一覧の見出し「未反映 1件」が合う。ボタンの意味は見出しごと（未反映＝取り下げる）。
2026-10-27 練習した人「ボタンの数と詳細の関係が分からない」——開き直したときは照合していなかったので、反映済みが「未反映」の札で残っていた。"""
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
lst = lambda: ev("document.getElementById('sheetList').innerText")


def open_page():
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); true")
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)


def edit(old, new, comment=''):
    ev("document.getElementById('editBtn').click(); true")
    time.sleep(0.3)
    ev(f"(() => {{ const t = document.getElementById('editNotes'); t.value = t.value.replace({json.dumps(old)}, {json.dumps(new)}); "
       f"document.getElementById('editComment').value = {json.dumps(comment)}; document.getElementById('editDone').click(); return true; }})()")
    time.sleep(0.3)


def show_sheet():
    if ev("document.getElementById('sheetPanel').hidden"):
        ev("document.getElementById('sheetBtn').click(); true")
    time.sleep(0.3)
    return lst()


try:
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    ev("localStorage.clear(); true")
    open_page()
    ev("document.getElementById('nextBtn').click(); true")
    time.sleep(0.3)
    edit('And the lamp went out.', 'And then the lamp went out.', 'the music is too loud here')
    ev("document.getElementById('nextBtn').click(); true")
    time.sleep(0.3)
    edit('a small boat on the beach', 'a little boat on the beach')
    l1 = show_sheet()
    print('1. 2件直した:', btn(), '|', l1.replace(chr(10), ' | '))
    assert btn() in ('修正票（未反映 2）', 'Correction sheet (2 not done)'), btn()
    assert '未反映 2件' in l1 or 'Not done yet: 2' in l1, l1
    assert 'the music is too loud here' in l1, 'ひとことが一覧に見えない'
    assert l1.count('取り下げる') + l1.count('Withdraw') == 2, l1
    # 2枚目だけ書き戻して作り直す
    s = (WORK / 'script.md').read_text(encoding='utf-8')
    (WORK / 'script.md').write_text(s.replace('And the lamp went out.', 'And then the lamp went out.', 1), encoding='utf-8')
    run(BUILD, WORK, '--draft', '--skip-text')
    # ページを開き直して「作品を選ぶ」から（練習した人の手順: Ctrl+F5 → 作品を選ぶ）
    open_page()
    note = ev("document.getElementById('reloadNote').textContent")
    l2 = show_sheet()
    print('2. 開き直した:', btn(), '|', note, '|', l2.replace(chr(10), ' | '))
    assert btn() in ('修正票（未反映 1）', 'Correction sheet (1 not done)'), btn()
    assert '未反映 1件' in l2 or 'Not done yet: 1' in l2, l2
    assert 'And then the lamp' not in l2, '反映済みが残った'
    assert 'a little boat' in l2
    assert '1' in note, note
    assert not ev('window.__errs'), ev('window.__errs')
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    (HERE / 'sheet_groups.png').write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
