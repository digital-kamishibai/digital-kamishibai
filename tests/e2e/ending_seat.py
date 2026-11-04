"""エンディング動画のコマを指す1往復をまるごと通す（手で動かす確認。Edge・ffmpeg が要る）:
    python tests/e2e/ending_seat.py [作業フォルダ]
 練習で止めて指す → 修正票 → 印つきの絵コンテ → 作り手が選ぶ（ここでは代わりに1つ選ぶ）→
エンディング動画と練習用の版を作り直す → 書き戻しの確認 → プレイヤーで読み直して「変わった」。
作業用リポジトリの見本は変えない（写しで行う）。"""
import base64
import functools
import http.server
import json
import shutil
import subprocess
import sys
import threading
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for stream in (sys.stdout, sys.stderr):        # 日本語の Windows のコンソールでは出せない文字がある（· — など）
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
# 作業場所（見本の写し・撮った画面）。引数で渡さなければ一時フォルダ
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
WORK = HERE / 'rt' / 'sample'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

LADDER = REPO / 'ladder' / 'ending-video' / 'build_ending_video.py'
BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
CHECK = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'check_sheet.py'


def run(*args):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {" ".join(Path(str(a)).name if i == 0 else str(a) for i, a in enumerate(args))}  -> {r.returncode}')
    for line in (r.stdout + r.stderr).strip().splitlines()[-4:]:
        print('    ' + line)
    return r


# ---------- 準備: 見本の写し・曲・エンディング動画・練習用の版 ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
(WORK / 'sounds').mkdir()
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=18',
                '-af', 'volume=0.3', str(WORK / 'sounds' / 'ending.mp3')], check=True)
assert run(LADDER, WORK).returncode == 0
assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0

site = HERE / 'rt' / 'site'
shutil.copytree(REPO / 'player', site / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(HERE / 'rt')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'


def listing():
    """作品フォルダのファイル（URL のパスと、本当の更新日時）。プレイヤーには webkitRelativePath で渡す"""
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


def wait(js, what, tries=300):
    for _ in range(tries):
        try:
            if ev(js):
                return
        except burn.BurnError:
            pass
        time.sleep(0.05)
    raise SystemExit(f'timeout: {what}')


def shot(name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


try:
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1300, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

    # ---------- 1. 練習: 最後の枚でエンディング動画を止めて、コマ2を指す ----------
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    for _ in range(3):
        ev("document.getElementById('nextBtn').click(); true")
        time.sleep(0.2)
    wait("document.getElementById('nvideo').readyState >= 1", 'video')
    ev("(async () => { const v = document.getElementById('nvideo'); v.currentTime = 9; "
       "await new Promise(r => v.addEventListener('seeked', r, { once: true })); return true; })()")
    time.sleep(0.3)
    print('1. 止めた位置:', ev("document.getElementById('seatNow').textContent"))
    ev("document.getElementById('seatComment').value = 'too dark'; document.getElementById('seatPoint').click(); true")
    time.sleep(0.2)
    md = ev("""(async () => {
      const m = await import('/site/player/js/corrections.js');
      const key = Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'));
      return m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 9, 26, 16, 0));
    })()""")
    sheet = HERE / 'rt' / 'sheet.md'
    sheet.write_text(md, encoding='utf-8')
    print('   修正票:\n' + '\n'.join('     ' + l for l in md.strip().splitlines()))

    # ---------- 2. 書き戻し（Skill の手順どおり）: まだ選んでいない ----------
    r = run(CHECK, WORK, sheet)
    assert 'look' in r.stdout and r.returncode == 0
    assert run(LADDER, WORK, '--storyboard', '--mark', '2').returncode == 0
    page = (WORK / 'ending' / 'storyboard.html').read_text(encoding='utf-8')
    assert 'const MARK = [2];' in page

    # ---------- 3. 作り手が選ぶ（印つきの絵コンテを開いて確かめ、コピーされるコマンドを見る） ----------
    b2 = burn.Browser(burn.find_browser())
    try:
        b2.call('Page.navigate', {'url': (WORK / 'ending' / 'storyboard.html').as_uri()}, session=True)
        time.sleep(1.5)
        print('3. 絵コンテの印:', b2.evaluate("[...document.querySelectorAll('.card')].map(c => c.dataset.id + ':' + c.getAttribute('aria-pressed')).join(' ')"))
        print('   コピーされる行:', b2.evaluate("replaceLines()"))
    finally:
        b2.close()
    time.sleep(1.1)  # 動画の更新日時が確実に変わるように
    assert run(LADDER, WORK, '--replace', '2=pictures/01.jpg').returncode == 0
    assert run(LADDER, WORK).returncode == 0
    assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0
    r = run(CHECK, WORK, sheet)
    assert 'changed' in r.stdout and r.returncode == 0

    # ---------- 4. プレイヤーで作品を読み直す ----------
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('4. 読み直し:', ev("document.getElementById('reloadNote').textContent"))
    ev("document.getElementById('sheetBtn').click(); true")
    time.sleep(0.3)
    print('   修正票の一覧:', ev("document.getElementById('sheetList').innerText").replace('\n', ' | '))
    md2 = ev("""(async () => {
      const m = await import('/site/player/js/corrections.js');
      const key = Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'));
      return JSON.parse(localStorage.getItem(key)).items.length;
    })()""")
    print('   保存された件数:', md2)
    shot('rt_after_reload.png')
    errs = ev("window.__errs")
    print('ページの例外:', errs)
    assert '変わった' in ev("document.getElementById('sheetList').innerText") or 'changed' in ev("document.getElementById('sheetList').innerText")
    assert not errs
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
