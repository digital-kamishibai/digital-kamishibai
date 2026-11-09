"""穴の語り（行頭 "~ "、docs/work-format.md §2.3）が、語り手の画面で薄い黄色の背景（字は普通のまま）になり、
合図の行（青い斜体）と見分けられること、聞き手の画面には台本が出ないことを確かめる（手で動かす確認。Edge が要る）:
    python tests/e2e/hole_mark.py [作業フォルダ]
見本の写しの台本に穴の語りを足して使う。作業用リポジトリの見本は変えない。"""
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

# マイクを使う画面なので、偽のマイクで許可の確認を出さない
_real = subprocess.Popen
EXTRA = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required']
burn.subprocess = types.SimpleNamespace(Popen=lambda args, **kw: _real([args[0], *EXTRA, *args[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)

results = []


def ok(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('  OK  ' if cond else '  NG  ') + name + (f'  [{detail}]' if detail else ''))


shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
shutil.copytree(REPO / 'player', ROOT / 'player')
# 1枚目に穴の語り（2行の段落）を足す
HOLE = ['Our own lamp story', 'goes here.']
script = (WORK / 'script.md').read_text(encoding='utf-8')
script = script.replace("Tonight's story is about a lamp.\n",
                        "Tonight's story is about a lamp.\n\n" + ''.join(f'~ {h}\n' for h in HOLE), 1)
assert HOLE[0] in script
(WORK / 'script.md').write_text(script, encoding='utf-8')


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass

    def do_GET(self):
        # 中継は使わない（同じ PC の2つのブラウザは直接つながる）
        if self.path.startswith('/api/ice'):
            body = json.dumps({'iceServers': [{'urls': ['stun:stun.cloudflare.com:3478']}], 'turn': False}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


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
r = subprocess.run([PY, str(BUILD), str(WORK)], capture_output=True, text=True, encoding='utf-8', errors='replace')
ok('ビルドが通り、印の警告が無い', r.returncode == 0 and "hole's narration" not in r.stdout + r.stderr, (r.stdout + r.stderr).strip()[-200:])
notes = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))['slides'][0]['notes']
ok('work.json の notes に穴の語りが印付きで残る', all(f'~ {h}' in notes for h in HOLE), notes)

# 語り手の画面の見た目: 穴の語りの行・合図の行・普通の語りの行
LOOK = """(() => {
  const st = (el) => { const c = getComputedStyle(el); return { bg: c.backgroundColor, color: c.color, style: c.fontStyle, size: c.fontSize }; };
  const box = document.getElementById('notes');
  const holes = [...box.querySelectorAll('.hole')];
  const cue = box.querySelector('.cue');
  const plain = [...box.children].find((d) => !d.className && d.textContent.trim());
  return { n: holes.length, texts: holes.map((d) => d.textContent), all: box.innerText,
           hole: holes.length ? st(holes[0].querySelector('span')) : null, holeDiv: holes.length ? st(holes[0]) : null,
           cue: cue && st(cue), plain: plain && st(plain) };
})()"""
nar, lis = burn.Browser(exe), burn.Browser(exe)
try:
    page(nar, base + '/player/narrator.html?test')
    nar.evaluate(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, r"/\d/.test(document.getElementById('code').textContent)", 'code'))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    page(lis, base + '/player/listen.html?test', 900, 600)
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'tester'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request')
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('聞き手が入り、絵が届く', wait(lis, "!document.getElementById('picture').hidden && document.getElementById('picture').naturalWidth > 0", 'listener picture'))
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)

    look = nar.evaluate(LOOK)
    ok('穴の語りの2行が .hole になる', look['n'] == 2 and look['texts'] == HOLE, look['texts'])
    ok('印の文字（~）が語り手の画面に出ない', '~' not in look['all'], look['all'][:120])
    h, c, p = look['hole'], look['cue'], look['plain']
    ok('穴の語りの背景は薄い黄色', h and h['bg'] == 'rgb(255, 245, 157)', h and h['bg'])
    ok('穴の語りの字は普通の語りと同じ色・大きさ・普通の字', h and p and h['color'] == p['color'] and h['size'] == p['size']
       and h['style'] == 'normal', (h, p))
    ok('合図の行（青い斜体）と見分けられる', c and c['style'] == 'italic' and c['color'] != h['color']
       and c['bg'] != h['bg'], (c, h))
    ok('普通の語りには背景が無い', p and p['bg'] == 'rgba(0, 0, 0, 0)', p and p['bg'])
    shot(nar, 'hole_mark_light.png')

    nar.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-color-scheme', 'value': 'dark'}]}, session=True)
    time.sleep(0.3)
    dark = nar.evaluate(LOOK)
    ok('ダークモードの穴の語りの背景は暗い黄色', dark['hole']['bg'] == 'rgb(92, 80, 0)', dark['hole']['bg'])
    ok('ダークモードでも字は普通の語りと同じ', dark['hole']['color'] == dark['plain']['color'], (dark['hole'], dark['plain']))
    shot(nar, 'hole_mark_dark.png')

    text = lis.evaluate("document.body.innerText")
    ok('聞き手の画面に台本（穴の語りも）が無い', not any(x in text for x in [*HOLE, 'about a lamp']), text[:120])
    ok('聞き手の画面に穴の印の見た目が無い', lis.evaluate("document.querySelectorAll('.hole').length") == 0)
    shot(lis, 'hole_mark_listener.png')
    errs = [nar.evaluate('window.__errs'), lis.evaluate('window.__errs')]
    ok('ページに例外が無い', not any(errs), errs)
finally:
    nar.close()
    lis.close()
    server.shutdown()
print(f'{sum(1 for _, good in results if good)}/{len(results)} OK')
sys.exit(0 if all(good for _, good in results) else 1)
