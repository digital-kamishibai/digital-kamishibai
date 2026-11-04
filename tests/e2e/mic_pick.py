"""語り手の画面でマイクを選ぶ（手で動かす確認。Edge が要る。テスト用のマイク2つ＝--use-fake-device-for-media-stream）:
    python tests/e2e/mic_pick.py [作業フォルダ]
 マイク2を選んで受付を開く → 使っているマイクがマイク2 → 途中でマイク1に替える → 使っているマイクが
マイク1に替わる → ページを開き直しても選んだマイクを覚えている。
2026-10-26: カメラのマイクとヘッドセットのどちらで拾っているか分からず、録画の声が小さかった。"""
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
nar = burn.Browser(exe)
try:
    run(BUILD, WORK)
    page(nar, base + '/player/narrator.html?test')
    nar.evaluate("localStorage.clear(); true")
    page(nar, base + '/player/narrator.html?test')
    opts = nar.evaluate("[...document.querySelectorAll('#micPick option')].map(o => o.textContent)")
    ok('マイクの欄に既定と、つながっているマイクが並ぶ', len(opts) >= 3 and opts[0] in ('ブラウザの既定', 'Browser default'), opts)
    ok('まだマイクを使っていないと出る', 'まだ' in nar.evaluate("document.getElementById('micNow').textContent")
       or 'No microphone' in nar.evaluate("document.getElementById('micNow').textContent"))
    second = opts[2]
    nar.evaluate("(() => { const s = document.getElementById('micPick'); s.selectedIndex = 2; s.dispatchEvent(new Event('change')); return true; })()")
    nar.evaluate(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code'))
    wait(nar, f"document.getElementById('micNow').textContent.includes({json.dumps(second)})", 'mic 2', tries=100)
    ok('選んだマイク（2）を使っている', second in nar.evaluate("document.getElementById('micNow').textContent"),
       nar.evaluate("document.getElementById('micNow').textContent"))
    first = opts[1]
    nar.evaluate("(() => { const s = document.getElementById('micPick'); s.selectedIndex = 1; s.dispatchEvent(new Event('change')); return true; })()")
    wait(nar, f"document.getElementById('micNow').textContent.includes({json.dumps(first)})", 'mic 1', tries=100)
    ok('途中で選び直すと、使っているマイクが替わる（1）', first in nar.evaluate("document.getElementById('micNow').textContent"),
       nar.evaluate("document.getElementById('micNow').textContent"))
    page(nar, base + '/player/narrator.html?test')
    time.sleep(0.5)
    ok('開き直しても、選んだマイクを覚えている', nar.evaluate("document.getElementById('micPick').selectedIndex") == 1)
    ok('ページに例外が無い', not nar.evaluate('window.__errs'), nar.evaluate('window.__errs'))
finally:
    nar.close()
    server.shutdown()
print(f'{sum(1 for _, good in results if good)}/{len(results)} OK')
sys.exit(0 if all(good for _, good in results) else 1)
