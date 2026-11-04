"""中継の枠を使い切ったとき（/api/ice が turn:false・reason:month を返す）、語り手の受付に案内が出て、
直接つながる端末はそのまま入れることを確かめる（手で動かす確認。Edge が要る）:
    python tests/e2e/relay_note.py [作業フォルダ]
理由ごとの文言と聞き手の案内は tests/player/ice.test.js の relayNote・tests/player/i18n.test.js で見る。"""
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


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass

    def do_GET(self):
        # 中継の見張りが「今月の枠を超えた」と印を付けた Worker の返事を真似る
        if self.path.startswith('/api/ice'):
            body = json.dumps({'iceServers': [{'urls': ['stun:stun.cloudflare.com:3478']}], 'turn': False, 'reason': 'month'}).encode()
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
ROUTE = "/直接|direct|中継|via relay/.exec(document.getElementById('listeners').textContent)?.[0] || ''"


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
print(f'$ build_work.py -> {r.returncode}')
NOTE = "(() => { const e = document.getElementById('relayNote'); return e && !e.hidden ? e.textContent : ''; })()"
nar, lis = burn.Browser(exe), burn.Browser(exe)
try:
    page(nar, base + '/player/narrator.html?test')
    nar.evaluate(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, "/\d/.test(document.getElementById('code').textContent)", 'code'))
    note = nar.evaluate(NOTE)
    ok('受付に「今月の中継の枠」の案内が出る', ('今月の中継の枠' in note) or ('This month' in note and 'relay' in note), note[:60])
    shot(nar, 'relay_note_room.png')
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    page(lis, base + '/player/listen.html?test', 900, 600)
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'tester'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request')
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('直接つながる端末はそのまま入れる', wait(lis, "!!document.querySelector('#pic, img') && window.__dkl", 'approved'))
    ok('道は「直接」', wait(nar, ROUTE, 'route', tries=240) and nar.evaluate(ROUTE) in ('直接', 'direct'), nar.evaluate(ROUTE))
    errs = [nar.evaluate('window.__errs'), lis.evaluate('window.__errs')]
    ok('ページに例外が無い', not any(errs), errs)
finally:
    nar.close()
    lis.close()
    server.shutdown()
print(f'{sum(1 for _, good in results if good)}/{len(results)} OK')
sys.exit(0 if all(good for _, good in results) else 1)
