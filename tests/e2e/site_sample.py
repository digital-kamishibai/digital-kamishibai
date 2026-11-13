"""サイトの見本を1押しで開く（narrator.html?sample=…）ことを確かめる（Edge が要る。素材は Release site-media から取り込む）:
    python tests/e2e/site_sample.py [作業フォルダ]
 node scripts/fetch-samples.mjs で見本を取り込む → player の写しを手元のサーバーで配る →
 語り手が ?sample=six-friends-smoothie&lang=ja を開く → 素材をサイトから取り、上演の画面の練習に入る・足りない素材が無い・
 BGM の大きさは目録の値（曲を読み解かない）・開き直しても素材の id が同じ →
 受付を開き、聞き手を1台入れる → 聞き手は音と動画をサイトから取って保存し、語り手からは送られない（荷物用の接続が張られない）→
 開演して聞き手に BGM が鳴る →
 無い見本の名前なら、理由を出して止まる。ページに例外が無いこと。インターネット（PeerJS の仲介）が要る。
 設計: docs/work-format.md §1「Samples on the site」。"""
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
import types
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

# 触れる前の音をブラウザが止めないように（bgm_level.py と同じ）
_real = subprocess.Popen
burn.subprocess = types.SimpleNamespace(Popen=lambda a, **kw: _real([a[0], '--autoplay-policy=no-user-gesture-required', *a[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)

failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


# ---------- 準備: 見本を取り込み、player を写す ----------
r = subprocess.run(['node', str(REPO / 'scripts' / 'fetch-samples.mjs')], capture_output=True, text=True, encoding='utf-8', errors='replace')
assert r.returncode == 0, r.stdout + r.stderr
shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'player', ROOT / 'player')
site = json.loads((REPO / 'examples' / 'six-friends-smoothie' / 'ja' / 'site.json').read_text(encoding='utf-8'))
LEVEL = site['versions'][-1]['levels']['sounds/bgm.mp3']
NEWEST = site['versions'][-1]['version']

HEADERS = {}
for line in (REPO / 'player' / '_headers').read_text(encoding='utf-8').splitlines():
    if line.startswith('  ') and ':' in line and 'Cache-Control' not in line:
        k, v = line.strip().split(':', 1)
        HEADERS[k.strip()] = v.strip()


class Site(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def end_headers(self):
        for k, v in HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Site, directory=str(ROOT / 'player')))
threading.Thread(target=server.serve_forever, daemon=True).start()
# DK_E2E_BASE を置くと、手元の写しの代わりにその箱で確かめる（開発用の箱で: DK_E2E_BASE=https://…workers.dev）
base = os.environ.get('DK_E2E_BASE', '').rstrip('/') or f'http://localhost:{server.server_address[1]}'
print(f'base: {base}')
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")


def open_page(b, url):
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1100, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': url}, session=True)
    time.sleep(0.3)
    b.evaluate(TRAP)


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


def opened(b):
    open_page(b, base + '/narrator.html?test&sample=six-friends-smoothie&lang=ja')
    return wait(b, "window.__dk && __dk.site() && __dk.screen() === 'show'", 'sample opened')


exe = burn.find_browser()
nar = burn.Browser(exe)
lis = burn.Browser(exe)
try:
    print('0. 玄関に見本のカード（日本語の端末）')
    nar.call('Emulation.setLocaleOverride', {'locale': 'ja-JP'}, session=True)
    open_page(nar, base + '/index.html')
    ok('カードが出る', wait(nar, "!document.getElementById('samplesBox').hidden", 'cards'))
    cards = nar.evaluate("[...document.querySelectorAll('#samples .card')].map((c) => ({t: c.querySelector('strong').textContent, a: c.querySelector('a').getAttribute('href'), b: c.querySelector('a').textContent}))")
    ok('見本ごとに1枚・日本語の版', len(cards) == 1 and cards[0]['a'] == 'narrator.html?sample=six-friends-smoothie&lang=ja' and cards[0]['b'] == '1台で通して見る',
       json.dumps(cards, ensure_ascii=False))
    for w in (390, 1280):
        nar.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': w < 600}, session=True)
        time.sleep(0.3)
        ok(f'{w}px で横にはみ出さない', nar.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        (HERE / f'front-{w}.png').write_bytes(base64.b64decode(nar.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))
    nar.evaluate("document.querySelector('#samples a').click(); true")
    ok('押すと上演の画面の練習に入る', wait(nar, "/\\/narrator(\\.html)?$/.test(location.pathname) && window.__dk === undefined && !document.getElementById('practiceNote').hidden", 'via card'))
    ok('玄関・語り手のページに例外が無い', not nar.evaluate("window.__errs || []"))

    print('1. 見本を開く')
    t0 = time.time()
    ok('上演の画面の練習に入った', opened(nar), f'{time.time() - t0:.1f}s')
    st = nar.evaluate("({title: document.getElementById('workTitle').textContent, site: __dk.site(), missing: document.getElementById('missing').hidden,"
                      " note: document.getElementById('sampleNote').hidden, practice: !document.getElementById('practiceNote').hidden,"
                      " levels: __dk.levels(), errs: window.__errs})")
    print('   ', json.dumps({k: st[k] for k in ('title', 'site')}, ensure_ascii=False))
    ok('題が出る', st['title'].startswith('6人のなかまのスムージー'))
    ok(f'一番新しい版（{NEWEST}）の置き場', st['site']['base'] == f'samples/six-friends-smoothie/ja/{NEWEST}/')
    ok('足りない素材が無い', st['missing'])
    ok('取っている知らせは消えた', st['note'])
    ok('練習中と出る', st['practice'])
    look = nar.evaluate("({holes: document.querySelectorAll('#notes .hole').length, marks: [...document.querySelectorAll('#notes div')].filter((d) => /^~/.test(d.textContent)).length})")
    ok('穴の語り（~1）が黄色で出て、印は画面に残らない', look['holes'] >= 5 and look['marks'] == 0, json.dumps(look))
    ok('練習中の帯に「下読み」と「家族の端末をつなぐ」', nar.evaluate("!document.getElementById('practiceSample').hidden && !!document.querySelector('#practiceNote [data-goto=room]')"))
    ok('「作品を読み直す」は出ない（フォルダから読み直すものではない）', nar.evaluate("document.getElementById('reloadLabel').hidden"))
    bgm = [x for x in st['levels'] if x['key'] == 'sounds/bgm.mp3']
    ok('BGM の大きさは目録の値', bgm and bgm[0]['lufs'] == LEVEL, json.dumps(bgm))
    ok('ページに例外が無い', not st['errs'], json.dumps(st['errs'], ensure_ascii=False))
    ids1 = sorted(x['id'] for x in st['levels'])

    print('2. 開き直しても素材の id が同じ（聞き手の端末に残した分が使える）')
    ok('開き直した', opened(nar))
    ids2 = sorted(x['id'] for x in nar.evaluate('__dk.levels()'))
    ok('id が同じ', ids1 == ids2 and len(ids1) == 3, f'{ids1} / {ids2}')

    print('3. 聞き手は音と動画をサイトから取る（語り手からは送らない）')
    nar.evaluate("document.querySelector('[data-screen=room]').click(); document.getElementById('expected').value = 1; "
                 "document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code', 600))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    lis.call('Emulation.setDeviceMetricsOverride', {'width': 900, 'height': 506, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    lis.call('Page.navigate', {'url': base + '/listen.html?test'}, session=True)
    time.sleep(1.0)
    lis.evaluate(TRAP)
    lis.evaluate("navigator.storage.getDirectory().then((r) => r.removeEntry('dk-videos', { recursive: true })).catch(() => {}); true")
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'far'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request', 600)
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('聞き手に1枚目の絵が出る', wait(lis, "!document.getElementById('picture').hidden && document.getElementById('picture').naturalWidth > 0", 'picture', 600))
    ok('聞き手: 音と動画が全部そろう', wait(lis, "__dkl.vids().length === 4 && __dkl.vids().every((v) => v.ready)", 'vids', 1200),
       json.dumps(lis.evaluate("__dkl.vids()")))
    vs = lis.evaluate("__dkl.vids()")
    ok('聞き手: どれもサイトの道から', all(v['src'] and v['src'].startswith(f'samples/six-friends-smoothie/ja/{NEWEST}/') for v in vs), json.dumps([v['src'] for v in vs]))
    ok('語り手は荷物用の接続を張っていない（送っていない）', nar.evaluate("__dk.bulks()") == 0)
    nar.evaluate("document.querySelector('[data-screen=show]').click(); true")
    time.sleep(0.3)
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('開演: 聞き手の端末で BGM が鳴る', wait(lis, "__dkl.audio().playing", 'listener bgm', 600), json.dumps(lis.evaluate("__dkl.audio()")))
    ok('語り手・聞き手のページに例外が無い', not nar.evaluate("window.__errs") and not lis.evaluate("window.__errs"),
       json.dumps([nar.evaluate("window.__errs"), lis.evaluate("window.__errs")], ensure_ascii=False))

    print('4. 無い見本')
    open_page(nar, base + '/narrator.html?test&sample=no-such-sample')
    ok('理由を出して止まる', wait(nar, "!document.getElementById('loadError').hidden && document.getElementById('loadError').textContent.includes('no-such-sample')", 'error shown'))
    ok('作品は開いていない', nar.evaluate("__dk.site() === null && __dk.screen() === 'prep'"))
finally:
    nar.close()
    lis.close()
    server.shutdown()

print('\n' + ('すべて OK' if not failures else f'NG {len(failures)} 件: ' + ', '.join(failures)))
sys.exit(1 if failures else 0)
