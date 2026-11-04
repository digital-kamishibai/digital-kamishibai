"""画面の文字の色と下地の色を、プレイヤーで直す1往復をまるごと通す（手で動かす確認。Edge が要る）:
    python tests/e2e/layout_color.py [作業フォルダ]
見本の写しを練習用の版にする → 2枚目の枠を選ぶ → 色の欄（見本＝作品の色＋白・黒）・明暗差の目安が出る →
下地を黒→白にすると明暗差に印（選ぶのは止めない）→ 文字の色を自由に選ぶ → 閉じると修正票に color・fill →
**ページを読み込み直しても件が残る** → check_sheet は PENDING → §2.6 のとおり書き戻す → done → 作り直して読み直す → 自分で消える →
もう一度「下地なし」→ fill none → fill の語を消して書き戻す → done → 読み直して消える。作業用リポジトリの見本は変えない（写しで行う）。"""
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
N = 2
TEXT_LINE = '> [Text] place top size 44pt bold color #FFFFFF\n'


def run(*a):
    r = subprocess.run([PY, *map(str, a)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {Path(str(a[0])).name} {" ".join(map(str, a[1:]))}  -> {r.returncode}')
    for line in (r.stdout + r.stderr).strip().splitlines()[-6:]:
        print('    ' + line)
    return r


# ---------- 準備: 見本の写し（2枚目に [Text] が1つ・白い文字・下地なし） ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
script = WORK / 'script.md'
original = script.read_text(encoding='utf-8')
assert TEXT_LINE in original, '2枚目の [Text] の行が変わった（見本が変わった？）'
assert run(BUILD, WORK, '--draft').returncode == 0

site = HERE / 'rt' / 'site'
shutil.copytree(REPO / 'player', site / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    # ⚠️ Windows では .js が text/javascript で返らないことがある（モジュールが読めない）
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
SHEET = """(async () => {
  const m = await import('/site/player/js/corrections.js');
  const key = Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'));
  return key ? m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 9, 30, 10, 0)) : '';
})()"""
STORED = "JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'))) || 'null')"
BOX = "document.querySelector('#layBoxes .b')"

b = burn.Browser(burn.find_browser())
ev = b.evaluate
text = lambda i: ev(f"document.getElementById('{i}').textContent")  # noqa: E731
hidden = lambda i: ev(f"document.getElementById('{i}').hidden")      # noqa: E731
click = lambda i: ev(f"document.getElementById('{i}').click(); true")  # noqa: E731


def wait(js, what, tries=600):
    for _ in range(tries):
        try:
            if ev(js):
                return
        except burn.BurnError:
            pass
        time.sleep(0.05)
    shot('timeout.png')
    raise SystemExit(f'timeout: {what}')


def shot(name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


def mouse_click(x, y):
    for t in ('mousePressed', 'mouseReleased'):
        b.call('Input.dispatchMouseEvent', {'type': t, 'x': x, 'y': y, 'button': 'left', 'clickCount': 1}, session=True)


def open_page():
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork') && document.readyState === 'complete'", 'page')
    time.sleep(0.5)
    ev("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.2)
    click('nextBtn')
    time.sleep(0.2)


def open_box():
    """2枚目の直す欄を開き、絵の上の1つ目の枠を選ぶ"""
    click('editBtn')
    wait("!document.getElementById('layPane').hidden && document.getElementById('layBase').complete "
         f"&& document.getElementById('layBase').naturalWidth > 0 && !!{BOX}", 'layout pane')
    ev(f"{BOX}.scrollIntoView({{ block: 'center' }}); true")     # 2回目は欄が下へずれ、上の帯の陰に入る
    time.sleep(0.3)
    r = ev(f"(() => {{ const r = {BOX}.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }})()")
    mouse_click(*r)
    wait("!document.getElementById('layColors').hidden", 'colour fields')


def swatch(row, color):
    ev(f"document.querySelector('#{row} button[data-c=\"{color}\"]').click(); true")
    time.sleep(0.1)


def write_back(sheet_md, old, new):
    """修正票 → check_sheet は PENDING → script.md を §2.6 のとおり直す → done → 練習用の版を作り直す"""
    sheet = HERE / 'rt' / 'sheet.md'
    sheet.write_text(sheet_md, encoding='utf-8')
    r = run(CHECK, WORK, sheet)
    assert r.returncode == 1 and f'PENDING   [Slide {N}] layout 1' in r.stdout, r.stdout
    s = script.read_text(encoding='utf-8')
    assert old in s
    script.write_text(s.replace(old, new), encoding='utf-8')
    r = run(CHECK, WORK, sheet)
    assert r.returncode == 0 and f'done      [Slide {N}] layout 1' in r.stdout, r.stdout
    time.sleep(1.1)  # 更新日時が確実に変わるように
    assert run(BUILD, WORK, '--draft').returncode == 0


def reload_work():
    ev("document.getElementById('reloadNote').textContent = ''; true")
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('   読み直し:', text('reloadNote'))
    stored = ev(STORED)
    assert not stored or not stored['items'], f'反映済みが残っている: {stored}'


try:
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'first page')
    ev("localStorage.clear(); true")
    open_page()

    # ---------- 1. 色の欄: 見本＝作品の色＋白・黒・いまの色に印・明暗差の目安（下地なし＝下敷きの平均） ----------
    open_box()
    colours = ev("[...document.querySelectorAll('#layColorSw button')].map(b => b.dataset.c)")
    print('1. 文字の色の見本:', colours, '/ いま:', ev("document.querySelector('#layColorSw button.on')?.dataset.c"))
    assert colours == ['#FFFFFF', '#000000'], colours                 # 見本の作品の文字色は白だけ
    assert ev("document.querySelector('#layColorSw button.on').dataset.c") == '#FFFFFF'
    assert ev("document.getElementById('layFillNone').classList.contains('on')"), '下地なしに印が無い'
    assert not hidden('layContrast'), '明暗差が出ていない'
    print('   明暗差:', text('layContrast'))
    shot('colour_1_before.png')

    # ---------- 2. 下地を黒 → 白（白い文字に白い下地＝印。でも選べる）→ 文字の色を自由に選ぶ ----------
    swatch('layFillSw', '#000000')
    assert ev(f"getComputedStyle({BOX}).backgroundColor") == 'rgb(0, 0, 0)'
    assert not ev("document.getElementById('layContrast').classList.contains('low')")
    print('2. 黒い下地:', text('layContrast'))
    swatch('layFillSw', '#FFFFFF')
    assert ev("document.getElementById('layContrast').classList.contains('low')"), '白に白で印が付かない'
    print('   白い下地:', text('layContrast'))
    assert ev(f"getComputedStyle({BOX}).backgroundColor") == 'rgb(255, 255, 255)', '印が付いても選べること'
    ev("(() => { const i = document.getElementById('layColorPick'); i.value = '#1e2c4a'; i.dispatchEvent(new Event('input')); return true; })()")
    time.sleep(0.1)
    assert ev(f"getComputedStyle({BOX}.querySelector('p')).color") == 'rgb(30, 44, 74)'
    assert not ev("document.getElementById('layContrast').classList.contains('low')")
    assert ev(f"{BOX}.classList.contains('edited')"), '色だけ変えた枠に直した印が無い'
    print('   紺の文字:', text('layContrast'))
    shot('colour_2_after.png')
    click('editDone')
    time.sleep(0.2)
    item = ev(STORED)['items']
    assert item == [{'slide': N, 'kind': 'layout', 'at': 1,
                     'before': {'color': '#FFFFFF', 'fill': 'none'}, 'after': {'color': '#1E2C4A', 'fill': '#FFFFFF'}}], item

    # ---------- 3. ページを読み込み直しても、色の件は消えない ----------
    open_page()
    item = ev(STORED)['items']
    assert len(item) == 1 and item[0]['after'] == {'color': '#1E2C4A', 'fill': '#FFFFFF'}, f'読み込み直しで消えた: {item}'
    md = ev(SHEET)
    print('3. 修正票:\n' + '\n'.join('     ' + line for line in md.strip().splitlines()))
    assert f'## [Slide {N}] layout 1\n### Before\n```\ncolor #FFFFFF\nfill none\n```\n### After\n```\ncolor #1E2C4A\nfill #FFFFFF\n```' in md

    # ---------- 4. 書き戻す（color は置き換え・fill は足す）→ 読み直すと自分で消える ----------
    with_band = '> [Text] place top size 44pt bold color #1E2C4A fill #FFFFFF\n'
    write_back(md, TEXT_LINE, with_band)
    reload_work()

    # ---------- 5. 下地なし → fill none → fill の語を消して書き戻す ----------
    open_box()
    assert ev("document.querySelector('#layFillSw button.on')?.dataset.c") == '#FFFFFF'
    click('layFillNone')
    time.sleep(0.1)
    assert ev(f"getComputedStyle({BOX}).backgroundColor") == 'rgba(0, 0, 0, 0)', '下地が消えていない'
    click('editDone')
    time.sleep(0.2)
    item = ev(STORED)['items']
    assert item == [{'slide': N, 'kind': 'layout', 'at': 1, 'before': {'fill': '#FFFFFF'}, 'after': {'fill': 'none'}}], item
    md = ev(SHEET)
    print('5. 修正票:\n' + '\n'.join('     ' + line for line in md.strip().splitlines()))
    write_back(md, with_band, '> [Text] place top size 44pt bold color #1E2C4A\n')
    reload_work()

    errs = ev("window.__errs")
    print('ページの例外:', errs)
    assert not errs
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
