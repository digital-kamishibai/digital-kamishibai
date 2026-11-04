"""絵の候補を、プレイヤーで見くらべて選ぶ1往復をまるごと通す（手で動かす確認。Edge・Pillow が要る。Gemini は使わない＝費用なし）:
    python tests/e2e/picture_choose.py [作業フォルダ]
 2枚目（画面の文字のある枚）に候補を2つ置く（02-1 は 16:9・02-2 は 4:3）→ 練習用の版を作る → 2枚目に「候補が 2 枚」→
組み立て直して読み直しても、作り直しの頼みは未反映のまま（Issue #5）→ 見くらべる（新しい 02-2 が先・候補の上にも文字が重なる・4:3 は黒地に全体）→ 作り直しの頼みを書いたあとで 02-1 を選ぶ（頼みを置き換える）→
修正票に Use → check_sheet は PENDING → gen_images.py --use 2-1 → check_sheet は done → 作り直して読み直す →
反映済みで自分で消える・残りの候補は 02-2 の1枚。作業用リポジトリの見本は変えない（写しで行う）。"""
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

from PIL import Image, ImageEnhance, ImageOps

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
N = 2
C1 = f'pictures/_candidates/{N:02d}-1.png'
C2 = f'pictures/_candidates/{N:02d}-2.png'


def run(*a):
    r = subprocess.run([PY, *map(str, a)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {Path(str(a[0])).name} {" ".join(map(str, a[1:]))}  -> {r.returncode}')
    for line in (r.stdout + r.stderr).strip().splitlines()[-6:]:
        print('    ' + line)
    return r


# ---------- 準備: 見本の写しと、候補2つ ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
src = Image.open(WORK / 'pictures' / f'{N:02d}.png').convert('RGB')
(WORK / 'pictures' / '_candidates').mkdir(parents=True)
ImageEnhance.Brightness(src).enhance(0.5).save(WORK / C1)
ImageOps.mirror(src).resize((1200, 900)).save(WORK / C2)           # 4:3（黒地に全体で見せる）
assert run(BUILD, WORK, '--draft').returncode == 0
w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
assert w['slides'][N - 1].get('overlay_layout'), '2枚目に画面の文字が無い（見本が変わった？）'

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
  return key ? m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 9, 29, 20, 0)) : '';
})()"""
STORED = "JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'))) || 'null')"

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
    raise SystemExit(f'timeout: {what}')


def shot(name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


try:
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

    # ---------- 1. 練習: 候補の無い枚には出ない・2枚目に「候補が 2 枚」 ----------
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.2)
    assert hidden('candBar'), '候補の無い1枚目に出ている'
    click('nextBtn')
    time.sleep(0.2)
    assert not hidden('candBar'), '2枚目に候補の欄が出ていない'
    print('1. 欄:', text('candNow'))
    assert text('candNow') in ('この絵の候補が 2 枚あります（見くらべて選べます）', '2 candidate(s) for this picture — compare and choose')

    # 先に作り直しの頼みを書いておく（選ぶと置き換わる）
    ev("(() => { const i = document.getElementById('picComment'); i.value = 'darker'; i.dispatchEvent(new Event('input')); return true; })()")
    click('picAsk')
    time.sleep(0.2)

    # ---------- 1b. 組み立て直しただけ（絵は同じ・文字を載せた絵だけ書き直される）: 頼みは未反映のまま（Issue #5） ----------
    time.sleep(1.1)  # 組み立てた絵の更新日時が確実に変わるように
    assert run(BUILD, WORK, '--draft').returncode == 0
    ev("document.getElementById('reloadNote').textContent = ''; true")
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded after a rebuild')
    item = ev(STORED)['items']
    assert len(item) == 1 and item[0]['comment'] == 'darker', item
    btn = ev("document.getElementById('sheetBtn').textContent")
    print('1b. 組み立て直して読み直し:', text('reloadNote'), '/ ボタン:', btn)
    # 「見て消す」になると、コピー・保存する修正票から抜ける
    assert btn in ('修正票（未反映 1）', 'Correction sheet (1 not done)'), f'組み立て直しただけで、絵の頼みが未反映でなくなった: {btn}'

    # ---------- 2. 見くらべる: 新しい 02-2 が先・4:3 は黒地に全体・候補の上にも文字 ----------
    click('candOpen')
    wait("!document.getElementById('candPanel').hidden && document.getElementById('candImg').complete "
         "&& document.getElementById('candImg').naturalWidth > 0", 'candidate shown')
    time.sleep(0.3)
    print('2. 見出し:', text('candTitle'), '/', text('candCap'))
    assert '02-2' in text('candCap'), '新しい候補が先に出ていない'
    assert not ev("document.getElementById('candImg').classList.contains('fill')"), '4:3 を引き伸ばしている'
    boxes = ev("document.getElementById('candBoxes').children.length")
    words = ev("document.getElementById('candBoxes').innerText")
    print('   候補の上の文字:', boxes, repr(words))
    assert boxes >= 1 and words.strip(), '候補の上に画面の文字が無い'
    assert ev("document.getElementById('candCur').naturalWidth > 0"), 'いまの絵が出ていない'
    shot('candidates_02-2.png')
    # 見くらべの間は、矢印で枚が動かない（候補が動く）
    ev("document.getElementById('candPanel').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); true")
    wait("document.getElementById('candImg').classList.contains('fill')", '16:9 candidate fitted')
    print('   →', text('candCap'), '/ 枚:', text('navNo'))
    assert '02-1' in text('candCap') and ev("document.getElementById('candNext').disabled")
    shot('candidates_02-1.png')

    # ---------- 3. 選ぶ: 修正票に Use（頼みを置き換える） ----------
    click('candUse')
    time.sleep(0.2)
    print('3. ボタン:', text('candUse'), '/ 欄:', text('picSheet'))
    assert ev("document.getElementById('candUse').disabled")
    item = ev(STORED)['items']
    assert len(item) == 1 and item[0]['use'] == C1 and 'comment' not in item[0], item
    md = ev(SHEET)
    print('   修正票:\n' + '\n'.join('     ' + line for line in md.strip().splitlines()))
    assert md.strip().split('\n\n', 1)[1].splitlines() == [f'## [Slide {N}] picture', f'Use {C1}']
    click('candClose')
    assert hidden('candPanel')
    sheet = HERE / 'rt' / 'sheet.md'
    sheet.write_text(md, encoding='utf-8')

    # ---------- 4. 書き戻し: 候補が残っている間は PENDING → --use → done ----------
    r = run(CHECK, WORK, sheet)
    assert r.returncode == 1 and f'PENDING   [Slide {N}] picture' in r.stdout
    time.sleep(1.1)  # 更新日時が確実に変わるように
    assert run(GEN, WORK, '--use', f'{N}-1').returncode == 0
    r = run(CHECK, WORK, sheet)
    assert r.returncode == 0 and f'done      [Slide {N}] picture' in r.stdout
    assert run(BUILD, WORK, '--draft').returncode == 0

    # ---------- 5. 読み直す: 反映済みで自分で消える・残りの候補は 02-2 ----------
    ev("document.getElementById('reloadNote').textContent = ''; true")
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('5. 読み直し:', text('reloadNote'))
    stored = ev(STORED)
    assert not stored or not stored['items'], f'反映済みが残っている: {stored}'
    print('   欄:', text('candNow'))
    assert text('candNow') in ('この絵の候補が 1 枚あります（見くらべて選べます）', '1 candidate(s) for this picture — compare and choose')

    # ---------- 6. どれもちがう: 見くらべを閉じて、作り直しの欄へ ----------
    click('candOpen')
    wait("!document.getElementById('candPanel').hidden", 'opened again')
    click('candNone')
    assert hidden('candPanel') and ev("document.activeElement && document.activeElement.id") == 'picComment'
    errs = ev("window.__errs")
    print('ページの例外:', errs)
    assert not errs
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
