"""見本の写しで、上演・練習・修正票の書き戻しを通す（手で動かす確認。Edge が要り、受付はインターネット上の紹介役を使う）:
    python tests/e2e/family_basic.py [作業フォルダ]
作業用リポジトリの見本は変えない。
2a: 上演用にビルド → 語り手が受付を開く → 別のブラウザの聞き手が合言葉で入る → 承認 → 聞き手に絵が届き、枚送りがついてくる
2b: --draft でビルド（画面の文字を焼き込む）→ 練習で直す欄を開くと、絵の上で直す枠が出る
3 : 練習でノート・画面の文字・置き場所を直す → 修正票 → Skill の手順どおり script.md へ書き戻す → ビルド → check_sheet → 読み直して反映済み"""
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
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# 作業場所（見本の写し・撮った画面）。引数で渡さなければ一時フォルダ
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
ROOT = HERE / 'fam'
WORK = ROOT / 'sample'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
CHECK = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'check_sheet.py'

# マイクを使う画面なので、偽のマイクで許可の確認を出さない
_real = subprocess.Popen
EXTRA = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required']
burn.subprocess = types.SimpleNamespace(Popen=lambda args, **kw: _real([args[0], *EXTRA, *args[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)

results = []


def ok(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('  OK  ' if cond else '  NG  ') + name + (f'  [{detail}]' if detail else ''))


def run(*args):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {Path(str(args[0])).name} {" ".join(map(str, args[2:]))} -> {r.returncode}')
    return r


shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
shutil.copytree(REPO / 'player', ROOT / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'


def listing():
    return [{'url': '/' + p.relative_to(ROOT).as_posix(), 'rel': p.relative_to(ROOT).as_posix(),
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
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")


def wait(b, js, what, tries=600):
    for _ in range(tries):
        try:
            if b.evaluate(js):
                return True
        except burn.BurnError:
            pass
        time.sleep(0.05)
    print('  timeout: ' + what)
    return False


def page(b, url, w=1600, h=1300):
    b.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': url}, session=True)
    time.sleep(1.0)
    b.evaluate(TRAP)


def shot(b, name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


exe = burn.find_browser()

# ================= 2a: 上演 =================
print('== 2a: 上演用にビルドして、別のブラウザの聞き手で上演する')
r = run(BUILD, WORK)
ok('上演用のビルドが通る（画面の文字の焼き込み込み）', r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1])
nar, lis = burn.Browser(exe), burn.Browser(exe)
try:
    page(nar, base + '/player/narrator.html')
    nar.evaluate(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; document.getElementById('openRoom').click(); true")
    ok('受付が開き、合言葉が出る', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code'))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    page(lis, base + '/player/listen.html', 900, 600)
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'tester'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    ok('承認の依頼が語り手に届く', wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request'))
    ok('承認前の聞き手には絵が出ない', lis.evaluate("document.getElementById('picture').hidden || !document.getElementById('picture').src"))
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('承認すると聞き手に1枚目の絵が出る', wait(lis, "!document.getElementById('picture').hidden && document.getElementById('picture').naturalWidth > 0", 'listener picture'))
    first = lis.evaluate("document.getElementById('picture').src")
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    ok('次へで聞き手の絵が2枚目に変わる', wait(lis, f"document.getElementById('picture').src !== {json.dumps(first)} && document.getElementById('picture').naturalWidth > 0", 'next'))
    shot(lis, 'fam_listener_slide2.png')
    ok('聞き手の画面に台本が無い', 'One winter night' not in lis.evaluate("document.body.innerText"))
    # 大きな画面の全画面でも、左右を余らせずに広がる（2026-10-27 練習した人「中央部分だけしか表示されないのは、もったいない」）
    page_w = 2560
    nar.call('Emulation.setDeviceMetricsOverride', {'width': page_w, 'height': 1440, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    time.sleep(0.3)
    show_w = nar.evaluate("document.getElementById('screenShow').getBoundingClientRect().width")
    ok('2560px の画面で上演の画面が横いっぱいに広がる', show_w >= page_w - 60, round(show_w))
    shot(nar, 'fam_narrator_2560.png')
    nar.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1300, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    nar.evaluate("document.getElementById('nextBtn').click(); document.getElementById('nextBtn').click(); true")
    ok('最後の枚（エンディング動画・まだ無い）で語り手が止まらない', wait(nar, "document.getElementById('navNo').textContent.startsWith('4')", 'slide 4'))
    ok('語り手・聞き手のページに例外が無い', nar.evaluate("window.__errs.length") == 0 and lis.evaluate("window.__errs.length") == 0,
       json.dumps([nar.evaluate("window.__errs"), lis.evaluate("window.__errs")]))
finally:
    nar.close()
    lis.close()

# ================= 2b・3: 練習で直して、書き戻して、読み直す =================
print('== 2b・3: 練習用の版で直す → 修正票 → 書き戻し → 読み直し')
r = run(BUILD, WORK, '--draft')
ok('練習用のビルドが通る', r.returncode == 0)
wj = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
ok('練習用の版に画面の文字と置き場所が入る', wj['slides'][1].get('overlays') and wj['slides'][1].get('overlay_layout'))
nar = burn.Browser(exe)
try:
    page(nar, base + '/player/narrator.html')
    nar.evaluate("localStorage.clear(); true")
    nar.evaluate(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    nar.evaluate("document.querySelector('[data-goto=show]').click(); document.getElementById('nextBtn').click(); true")
    time.sleep(0.3)
    nar.evaluate("document.getElementById('editBtn').click(); true")
    ok('直す欄を開くと、絵の上で直す枠が出る（2b）', wait(nar, "!document.getElementById('layPane').hidden && document.querySelectorAll('#layBoxes > *').length === 1", 'layPane'))
    shot(nar, 'fam_edit.png')
    # ノートの2段落目・画面の文字の2段落目・枠の上の位置を直す
    nar.evaluate("""(() => {
      const n = document.getElementById('editNotes');
      n.value = n.value.replace('And the lamp went out.', 'And then the lamp went out.');
      const tas = [...document.querySelectorAll('#editBoxes textarea')];
      const w = tas.find((t) => t.value === 'winter');
      w.value = 'that winter'; w.dispatchEvent(new Event('input'));
      return true;
    })()""")
    rect = nar.evaluate("(() => { const b = document.querySelector('#layBoxes > *'); b.scrollIntoView({ block: 'center' }); const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
    for kind in ('mousePressed', 'mouseReleased'):
        nar.call('Input.dispatchMouseEvent', {'type': kind, 'x': rect[0], 'y': rect[1], 'button': 'left', 'buttons': 1, 'clickCount': 1}, session=True)
    time.sleep(0.2)
    sel = nar.evaluate("!document.getElementById('layFields').hidden")
    if sel:
        nar.evaluate("const t = document.getElementById('layTop'); t.value = '0.50'; t.dispatchEvent(new Event('input')); true")
    ok('枠を選ぶと数値の欄が出る', sel)
    nar.evaluate("document.getElementById('editDone').click(); true")
    time.sleep(0.2)
    md = nar.evaluate("""(async () => {
      const m = await import('/player/js/corrections.js');
      const key = Object.keys(localStorage).find((k) => k.startsWith('dk-corrections:'));
      return m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 9, 26, 17, 0));
    })()""")
    (ROOT / 'sheet.md').write_text(md, encoding='utf-8')
    print('   修正票:\n' + '\n'.join('     ' + l for l in md.strip().splitlines()))
    heads = [l for l in md.splitlines() if l.startswith('## ')]
    ok('修正票に3件（notes・overlay・layout）', heads == ['## [Slide 2] notes 2', '## [Slide 2] overlay 1', '## [Slide 2] layout 1'], heads)
    r = run(CHECK, WORK, ROOT / 'sheet.md')
    ok('書き戻す前の確認は PENDING', 'PENDING' in r.stdout and r.returncode == 1)

    # ---- 書き戻し（references/correction-sheet.md の手順どおり。Claude の役） ----
    s = (WORK / 'script.md').read_text(encoding='utf-8')
    s = s.replace('And the lamp went out.', 'And then the lamp went out.')
    s = s.replace("> [Text] place top size 44pt bold color #FFFFFF\n> The keeper's island\n>\n> winter",
                  "> [Text] left 0.50in top 0.50in width 12.33in height 1.20in size 44pt bold color #FFFFFF\n> The keeper's island\n>\n> that winter")
    (WORK / 'script.md').write_text(s, encoding='utf-8')
    r = run(BUILD, WORK, '--draft')
    ok('書き戻したあとのビルドが通る', r.returncode == 0)
    r = run(CHECK, WORK, ROOT / 'sheet.md')
    print('    ' + r.stdout.strip().replace('\n', '\n    '))
    ok('書き戻したあとの確認は3件とも done', r.returncode == 0 and r.stdout.count('done') == 3)

    nar.evaluate(f"{PICK}('reloadWork', {json.dumps(listing())})")
    ok('プレイヤーで読み直すと、反映済みの3件が消える', wait(nar, "/3/.test(document.getElementById('reloadNote').textContent)", 'reload'),
       nar.evaluate("document.getElementById('reloadNote').textContent"))
    left = nar.evaluate("(() => { const k = Object.keys(localStorage).find((k) => k.startsWith('dk-corrections:')); return k ? JSON.parse(localStorage.getItem(k)).items.length : 0; })()")
    ok('修正票が空になる', left == 0, left)
    shot(nar, 'fam_after_reload.png')
    ok('ページに例外が無い', nar.evaluate("window.__errs.length") == 0, json.dumps(nar.evaluate("window.__errs")))
finally:
    nar.close()
    server.shutdown()

print()
print(f'{sum(1 for _, v in results if v)}/{len(results)} OK')
sys.exit(0 if all(v for _, v in results) else 1)
