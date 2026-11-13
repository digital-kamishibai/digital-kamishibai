"""上演の画面が、ページをスクロールせずに語れる配置かを、いろいろな画面の大きさで確かめる（Edge が要る。素材は Release site-media から取り込む）:
    python tests/e2e/show_layout.py [作業フォルダ]
 サイトの見本（?sample=six-friends-smoothie）を練習で開く → PC・横向き／縦向きのタブレット・スマホの大きさごとに:
 ページが縦にも横にもスクロールしない・戻る／次へ・次の絵・台本が画面の中に見える（境目を広げても・低い画面でも）・横長は左右に並び、縦向きは 絵 → 台本 → 戻る／次へ の順 →
 字を大きくすると台本の枠の中だけでスクロールし、↓ で送れる・→ で枚が進むと台本は頭へ戻る → 字の大きさは読み込み直しても残る。
 縦積みでは札・練習の欄が畳まれていて、押すと開く。ページに例外が無いこと。各大きさの画面を作業フォルダに撮る。"""
import base64
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
ROOT = HERE / 'rt'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


# ---------- 準備: 見本を取り込み、player を写す（site_sample.py と同じ） ----------
r = subprocess.run(['node', str(REPO / 'scripts' / 'fetch-samples.mjs')], capture_output=True, text=True, encoding='utf-8', errors='replace')
assert r.returncode == 0, r.stdout + r.stderr
shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'player', ROOT / 'player')


class Site(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Site, directory=str(ROOT / 'player')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = os.environ.get('DK_E2E_BASE', '').rstrip('/') or f'http://localhost:{server.server_address[1]}'
print(f'base: {base}')
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

# 名前・幅・高さ・タッチの端末か・縦積みになるはずか
SIZES = [
    ('pc-1920', 1920, 1080, False, False),
    ('pc-1366', 1366, 768, False, False),
    ('tablet-land-1180', 1180, 820, True, False),
    ('tablet-land-1024', 1024, 768, True, False),
    ('tablet-port-820', 820, 1180, True, True),
    ('tablet-port-768', 768, 1024, True, True),
    ('phone-land-844', 844, 390, True, False),
    ('phone-port-390', 390, 844, True, True),
]

# 画面の中に見えているか（上下左右とも viewport の内側。1px の誤差は許す）
SEEN = """((id) => { const r = document.getElementById(id).getBoundingClientRect();
  return r.width > 0 && r.height > 0 && r.top >= -1 && r.left >= -1 && r.bottom <= innerHeight + 1 && r.right <= innerWidth + 1; })"""
NOSCROLL = ("(() => { const m = document.querySelector('main'); const d = document.scrollingElement;"
            " return { page: d.scrollHeight - innerHeight, wide: d.scrollWidth - innerWidth, main: m.scrollHeight - m.clientHeight }; })()")


def wait(b, js, what, tries=600, step=0.05):
    for _ in range(tries):
        try:
            if b.evaluate(js):
                return True
        except burn.BurnError:
            pass
        time.sleep(step)
    print('  timeout: ' + what)
    return False


def key(b, k, code):
    for t in ('keyDown', 'keyUp'):
        b.call('Input.dispatchKeyEvent', {'type': t, 'key': k, 'code': code, 'windowsVirtualKeyCode': {'ArrowDown': 40, 'ArrowRight': 39}[k]}, session=True)


def size(b, w, h, touch):
    b.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': touch}, session=True)
    time.sleep(0.3)


def opened(b):
    b.call('Page.navigate', {'url': base + '/narrator.html?test&sample=six-friends-smoothie&lang=ja'}, session=True)
    time.sleep(0.3)
    b.evaluate(TRAP)
    return wait(b, "window.__dk && __dk.site() && __dk.screen() === 'show' && !!document.getElementById('next').getAttribute('src')", 'sample opened')


exe = burn.find_browser()
nar = burn.Browser(exe)
try:
    nar.call('Emulation.setLocaleOverride', {'locale': 'ja-JP'}, session=True)
    try:
        nar.evaluate("localStorage.removeItem('dk-notes-size'); true")
    except burn.BurnError:
        pass
    size(nar, 1600, 1000, False)
    ok('見本を練習で開いた', opened(nar))
    nar.evaluate("localStorage.removeItem('dk-notes-size'); true")

    for name, w, h, touch, stacked in SIZES:
        print(f'{name}（{w}×{h}）')
        size(nar, w, h, touch)
        nar.evaluate("document.getElementById('notes').scrollTop = 0; true")
        sc = nar.evaluate(NOSCROLL)
        ok('ページが縦にも横にもスクロールしない', sc['page'] <= 1 and sc['wide'] <= 1 and sc['main'] <= 1, json.dumps(sc))
        sw = nar.evaluate("document.getElementById('screenShow').getBoundingClientRect().width")
        ok('上演の画面が横いっぱいに広がる', sw >= w - 60, round(sw))
        for el in ('prev', 'nextBtn', 'next', 'notes', 'stageFrame'):
            ok(f'#{el} が画面の中に見える', nar.evaluate(f"{SEEN}('{el}')"))
        pos = nar.evaluate("""(() => { const y = (id) => document.getElementById(id).getBoundingClientRect();
          const f = y('stageFrame'), n = y('notes'), v = y('nextBtn'), x = y('next');
          return { sideBySide: n.left >= f.right - 1, notesBelowFrame: n.top >= f.bottom - 1, navBelowNotes: v.top >= n.bottom - 1,
                   nextBesideBtn: x.left >= v.right - 1 && x.top < v.bottom && x.bottom > v.top,
                   more: getComputedStyle(document.getElementById('sideMoreBtn')).display !== 'none',
                   moreOpen: getComputedStyle(document.getElementById('sideMore')).display !== 'none' }; })()""")
        if stacked:
            ok('縦積み: 絵 → 台本 → 戻る／次へ', pos['notesBelowFrame'] and pos['navBelowNotes'], json.dumps(pos))
            ok('縦積み: 札・練習の欄は畳んだ1行', pos['more'] and not pos['moreOpen'], json.dumps(pos))
        else:
            ok('横長: 絵と台本が左右に並ぶ', pos['sideBySide'], json.dumps(pos))
            ok('横長: 札・練習の欄は開いたまま（畳む行は出ない）', not pos['more'] and pos['moreOpen'], json.dumps(pos))
        ok('次の絵は「次へ」の横', pos['nextBesideBtn'], json.dumps(pos))
        (HERE / f'show-{name}.png').write_bytes(base64.b64decode(nar.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))

    print('境目を広げても、低い画面でも、次の絵と次へは見える（全画面で聞き手の画面を大きくしたとき）')
    for w, h in [(1920, 1080), (1536, 864), (1280, 720)]:
        size(nar, w, h, False)
        for split in (42, 65):
            nar.evaluate(f"document.getElementById('showGrid').style.setProperty('--split', '{split}%'); true")
            time.sleep(0.2)
            seen = all(nar.evaluate(f"{SEEN}('{el}')") for el in ('next', 'nextBtn', 'stageFrame'))
            ok(f'{w}×{h}・境目 {split}%: 次の絵・次へ・聞き手の画面が見える', seen)
        nar.evaluate("document.getElementById('soundToggle').click(); true")
        time.sleep(0.2)
        ok(f'{w}×{h}・境目 65%・音の欄を開いても見える', all(nar.evaluate(f"{SEEN}('{el}')") for el in ('next', 'nextBtn')))
        nar.evaluate("document.getElementById('soundToggle').click(); true")
    nar.evaluate("document.getElementById('showGrid').style.setProperty('--split', '42%'); true")

    print('字を大きくして台本を送る（1366×768）')
    size(nar, 1366, 768, False)
    before = nar.evaluate("parseFloat(getComputedStyle(document.getElementById('notes')).fontSize)")
    for _ in range(10):
        nar.evaluate("document.getElementById('notesBigger').click(); true")
    after = nar.evaluate("parseFloat(getComputedStyle(document.getElementById('notes')).fontSize)")
    ok('A+ で台本の字が大きくなる（上限で止まる）', after > before and abs(after - 2.6 * 16) < 0.5, f'{before} → {after}')
    sc = nar.evaluate(NOSCROLL)
    ok('字を大きくしてもページはスクロールしない', sc['page'] <= 1 and sc['main'] <= 1, json.dumps(sc))
    ok('台本の枠の中はスクロールできる', nar.evaluate("(() => { const n = document.getElementById('notes'); return n.scrollHeight > n.clientHeight; })()"))
    slide = nar.evaluate("document.getElementById('navNo').textContent")
    nar.evaluate("document.body.focus(); document.activeElement && document.activeElement.blur(); true")
    key(nar, 'ArrowDown', 'ArrowDown')
    top = nar.evaluate("document.getElementById('notes').scrollTop")
    ok('↓ で台本が送られ、枚は変わらない', top > 0 and nar.evaluate("document.getElementById('navNo').textContent") == slide, f'scrollTop {top}')
    key(nar, 'ArrowRight', 'ArrowRight')
    ok('→ で枚が進み、台本は頭へ戻る',
       wait(nar, f"document.getElementById('navNo').textContent !== {json.dumps(slide)} && document.getElementById('notes').scrollTop === 0", 'next slide'))
    ok('読み込み直しても字の大きさが残る', opened(nar) and abs(nar.evaluate("parseFloat(getComputedStyle(document.getElementById('notes')).fontSize)") - after) < 0.5)
    for _ in range(10):
        nar.evaluate("document.getElementById('notesSmaller').click(); true")
    ok('A− で下限まで小さくなる', abs(nar.evaluate("parseFloat(getComputedStyle(document.getElementById('notes')).fontSize)") - 16) < 0.5)
    nar.evaluate("localStorage.removeItem('dk-notes-size'); true")

    print('縦積みの折りたたみ（390×844）')
    size(nar, 390, 844, True)
    nar.evaluate("document.getElementById('sideMoreBtn').click(); true")
    ok('押すと札・練習の欄が開く', nar.evaluate("getComputedStyle(document.getElementById('sideMore')).display !== 'none' && document.getElementById('sideMoreBtn').getAttribute('aria-expanded') === 'true'"))
    sc = nar.evaluate(NOSCROLL)
    ok('開いてもページはスクロールせず、戻る／次へが見える', sc['page'] <= 1 and nar.evaluate(f"{SEEN}('nextBtn')"), json.dumps(sc))
    (HERE / 'show-phone-port-390-open.png').write_bytes(base64.b64decode(nar.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))
    nar.evaluate("document.getElementById('sideMoreBtn').click(); true")

    print('ほかの画面はいままでどおり（準備の画面はページがスクロールしてよい）')
    nar.evaluate("document.querySelector('[data-screen=prep]').click(); true")
    ok('準備の画面では上演の画面の印が外れる', nar.evaluate("document.body.dataset.screen === 'prep' && getComputedStyle(document.body).overflow !== 'hidden'"))
    ok('ページに例外が無い', not nar.evaluate("window.__errs || []"), json.dumps(nar.evaluate("window.__errs || []"), ensure_ascii=False))
finally:
    nar.close()
    server.shutdown()

print()
print('すべて OK' if not failures else f'NG {len(failures)} 件: ' + ' / '.join(failures))
sys.exit(1 if failures else 0)
