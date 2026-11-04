"""絵の作り直しを頼む1往復をまるごと通す（手で動かす確認。Edge・Pillow が要る。Gemini は使わない＝費用なし）:
    python tests/e2e/picture_redo.py [作業フォルダ]
 練習中に3枚目の絵へ「作り直したい」と書く → 修正票（## [Slide 3] picture・Comment:）→ check_sheet は look →
候補を作る（ここでは Gemini の代わりに pictures/_candidates/03-1.png を手で置く）→ 練習用の版を作り直して読み直す →
まだ「未反映」（候補を作っただけでは絵は変わらない）→ 作り手の代わりに gen_images.py --use 3 で選ぶ →
練習用の版を作り直して読み直す → 「変わった（見て消す）」で残る（自分では消えない）。
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

from PIL import Image, ImageEnhance

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
N = 3
ASK = 'the lamp should be dark — the storm has put it out'
WANT = [f'## [Slide {N}] picture', f'Comment: {ASK}']


def run(*a):
    r = subprocess.run([PY, *map(str, a)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {Path(str(a[0])).name} {" ".join(map(str, a[1:]))}  -> {r.returncode}')
    for line in (r.stdout + r.stderr).strip().splitlines()[-6:]:
        print('    ' + line)
    return r


# ---------- 準備: 見本の写し ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0
w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
assert w.get('draft') is True
PIC = w['slides'][N - 1]['picture']
assert PIC == f'pictures/{N:02d}.png', PIC  # --use は pictures/NN.png に置く（[Picture] の行がほかの名前なら書き替えが要る）

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
  return key ? m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 9, 26, 16, 0)) : '';
})()"""
STORED = "JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'))))"

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


def shot(name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


def reload_and_list(step):
    ev("document.getElementById('reloadNote').textContent = ''; true")
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print(f'{step} 読み直し:', ev("document.getElementById('reloadNote').textContent"))
    if ev("document.getElementById('sheetPanel').hidden"):
        ev("document.getElementById('sheetBtn').click(); true")
        time.sleep(0.3)
    lst = ev("document.getElementById('sheetList').innerText")
    print('   修正票の一覧:', lst.replace('\n', ' | '))
    return lst


def type_ask(text):
    ev(f"(() => {{ const i = document.getElementById('picComment'); i.value = {json.dumps(text)}; "
       "i.dispatchEvent(new Event('input')); return true; })()")


try:
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1300, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

    # ---------- 1. 練習: 3枚目の絵に「作り直したい」と書く ----------
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    for _ in range(N - 1):
        ev("document.getElementById('nextBtn').click(); true")
        time.sleep(0.15)
    assert not ev("document.getElementById('picBar').hidden"), '絵の頼みの欄が出ていない'
    print('1. 欄:', ev("document.getElementById('picSheet').textContent"))
    assert ev("document.getElementById('picAsk').disabled"), '文が空なのに押せる（文は必須）'
    type_ask('make it darker')
    ev("document.getElementById('picAsk').click(); true")
    time.sleep(0.2)
    # 書き直すと置き換わる（1枚に1件）
    print('   ボタン:', ev("document.getElementById('picAsk').textContent"))
    type_ask(ASK)
    ev("document.getElementById('picAsk').click(); true")
    time.sleep(0.2)
    print('   欄:', ev("document.getElementById('picSheet').textContent"))
    btn = ev("document.getElementById('sheetBtn').textContent")
    print('   ボタン:', btn)
    assert btn in ('修正票（未反映 1）', 'Correction sheet (1 not done)'), btn
    shot('picture_asked.png')
    md = ev(SHEET)
    print('   修正票:\n' + '\n'.join('     ' + line for line in md.strip().splitlines()))
    got = md.strip().split('\n\n', 1)[1].splitlines()
    assert got == WANT, f'\n got  {got}\n want {WANT}'
    item = ev(STORED)['items'][0]
    print('   保存（Markdown には書かない）:', {k: item[k] for k in ('path', 'file')})
    assert item['path'] == PIC and item['file']['size'] == (WORK / PIC).stat().st_size
    sheet = HERE / 'rt' / 'sheet.md'
    sheet.write_text(md, encoding='utf-8')

    # ---------- 2. 書き戻しの確認: 絵は作り手が選ぶまで look（PENDING に数えない） ----------
    r = run(CHECK, WORK, sheet)
    assert r.returncode == 0 and f'look      [Slide {N}] picture' in r.stdout

    # ---------- 3. 候補を作る（Gemini の代わりに手で置く）: 絵は変わらないので「未反映」のまま ----------
    time.sleep(1.1)  # 絵の更新日時が確実に変わるように
    cand = WORK / 'pictures' / '_candidates' / f'{N:02d}-1.png'
    cand.parent.mkdir(parents=True, exist_ok=True)
    ImageEnhance.Brightness(Image.open(WORK / PIC).convert('RGB')).enhance(0.45).save(cand)
    assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0
    lst = reload_and_list('3.')
    assert ('未反映' in lst or 'not done yet' in lst) and '変わった' not in lst and 'changed' not in lst, '候補を作っただけで変わったことになった'

    # ---------- 4. 作り手が選ぶ（ここでは代わりに --use）: 「変わった（見て消す）」で残る ----------
    r = run(GEN, WORK, '--use', N)
    assert r.returncode == 0 and (WORK / PIC).is_file() and any((WORK / 'pictures' / '_replaced').glob(f'{N:02d}-*.png'))
    assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0
    lst = reload_and_list('4.')
    assert '変わった' in lst or 'changed' in lst
    btn = ev("document.getElementById('sheetBtn').textContent")
    print('   ボタン:', btn)
    assert btn in ('修正票（未反映 0・見て消す 1）', 'Correction sheet (0 not done · 1 to check)'), btn  # 直った後も「まだ」に読めない
    assert ev("Object.keys(localStorage).filter(k => k.startsWith('dk-corrections:')).length") == 1, '自分で消えてはいけない'
    # 「変わった」件は Markdown に書かない（Claude にもう一度頼ませない）
    copied = ev("""(async () => {
      let got = '';
      navigator.clipboard.writeText = async (s) => { got = s; };
      document.getElementById('sheetCopy').click();
      await new Promise(r => setTimeout(r, 200));
      return got;
    })()""")
    assert 'picture' not in copied, copied
    shot('picture_after_use.png')
    errs = ev("window.__errs")
    print('ページの例外:', errs)
    assert not errs
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
