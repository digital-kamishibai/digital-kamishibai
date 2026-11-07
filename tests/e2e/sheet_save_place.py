"""修正票の［ファイルに保存］が、作品フォルダで開くかを語り手の画面で確かめる（手で動かす確認。Edge が要る）:
    python tests/e2e/sheet_save_place.py [作業フォルダ]
 フォルダを選ぶ画面（showDirectoryPicker）と保存画面（showSaveFilePicker）は、ヘッドレスでは押せないので差し替える。
選んだフォルダは、このページの専用の保存場所（OPFS）に作品の写しを置いたもの。
1. 作品フォルダを選ぶ → 保存画面の最初の場所（startIn）が作品フォルダ・票がそこに書かれる
2. 作品フォルダの親を選ぶ → startIn は work.json のあるフォルダ。読み直したあとも同じ
3. フォルダを選ぶ画面が無いブラウザ（いままでの input）→ 読めて、startIn は付かない
実機で、保存画面が作品フォルダの外で開き、票が作品の外に保存された（2026-11-07）。作業用リポジトリの見本は変えない（写しで行う）。"""
import argparse
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
ap.add_argument('here', nargs='?', help='作業フォルダ（写し）。無ければ一時フォルダ')
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


# OPFS の parent/work/... に作品の写しを置き、フォルダを選ぶ画面と保存画面を差し替える
STAGE = """(async (files) => {
  const root = await navigator.storage.getDirectory();
  await root.removeEntry('parent', { recursive: true }).catch(() => {});
  const parent = await root.getDirectoryHandle('parent', { create: true });
  for (const f of files) {
    const parts = f.rel.split('/');
    let d = parent;
    for (const p of parts.slice(0, -1)) d = await d.getDirectoryHandle(p, { create: true });
    const w = await (await d.getFileHandle(parts.at(-1), { create: true })).createWritable();
    await w.write(await (await fetch(f.url, { cache: 'no-store' })).blob());
    await w.close();
  }
  window.__picked = null;
  window.showDirectoryPicker = async () => window.__picked;
  window.__saveOpts = [];
  window.showSaveFilePicker = async (opts) => {
    window.__saveOpts.push({ startIn: opts.startIn ? opts.startIn.name : null, suggestedName: opts.suggestedName });
    return (opts.startIn || parent).getFileHandle(opts.suggestedName, { create: true });
  };
  window.__pick = async (which) => {
    const p = await (await navigator.storage.getDirectory()).getDirectoryHandle('parent');
    window.__picked = which === 'parent' ? p : await p.getDirectoryHandle('work');
  };
  window.__sheetsIn = async () => {
    const w = await (await (await navigator.storage.getDirectory()).getDirectoryHandle('parent')).getDirectoryHandle('work');
    const names = [];
    for await (const [k] of w.entries()) if (k.includes('-corrections-')) names.push(k);
    return names;
  };
  return true;
})"""
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


def fresh():
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); true")
    ev(f"{STAGE}({json.dumps(listing())})")
    wait("typeof window.__pick === 'function'", 'stage')


def save():
    ev("window.__saveOpts = []; if (document.getElementById('sheetPanel').hidden) document.getElementById('sheetBtn').click(); true")
    time.sleep(0.3)
    ev("document.getElementById('sheetSave').click(); true")
    wait("window.__saveOpts.length > 0", 'saved')
    time.sleep(0.3)
    return json.loads(ev("JSON.stringify(window.__saveOpts[0])"))


def correct_and_save():
    """1枚目にひとことを書いて、修正票をファイルに保存する → 保存画面に渡したもの"""
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    ev("document.getElementById('editBtn').click(); true")
    time.sleep(0.3)
    ev("document.getElementById('editComment').value = 'a little slower'; document.getElementById('editDone').click(); true")
    time.sleep(0.3)
    return save()


try:
    # 1. 作品フォルダを選ぶ
    fresh()
    ev("window.__pick('work').then(() => document.getElementById('pickWork').click()); true")
    o = correct_and_save()
    print('1. 作品フォルダを選んだ:', o)
    assert o['startIn'] == 'work', o
    names = ev("window.__sheetsIn()")
    print('   作品フォルダの票:', names)
    assert names == [o['suggestedName']], names
    # 2. 親を選ぶ → work.json のあるフォルダ。読み直したあとも同じ
    fresh()
    ev("window.__pick('parent').then(() => document.getElementById('pickWork').click()); true")
    o = correct_and_save()
    print('2. 親のフォルダを選んだ:', o)
    assert o['startIn'] == 'work', o
    ev("document.getElementById('reloadNote').textContent = ''; true")
    ev("window.__pick('work').then(() => document.getElementById('reloadWork').click()); true")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    o = save()
    print('   読み直したあと:', o)
    assert o['startIn'] == 'work', o
    # 3. フォルダを選ぶ画面が無いブラウザ
    fresh()
    ev("window.showDirectoryPicker = undefined; true")
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    o = correct_and_save()
    print('3. いままでの選び方:', o)
    assert o['startIn'] is None, o
    errs = ev("JSON.stringify(window.__errs)")
    assert errs == '[]', errs
    print('OK')
finally:
    b.close()
    server.shutdown()
