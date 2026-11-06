"""見本作品の zip を解凍したフォルダで、上演を通す（手で動かす確認。Edge が要り、受付はインターネット上の紹介役を使う）:
    python tests/e2e/sample_zip.py <解凍したフォルダ> [作業フォルダ]
解凍したフォルダは変えない（写しで動かす）。
語り手が作品を開く → 受付を開く → 別のブラウザの聞き手が合言葉で入る → 承認 → 全部の枚を送り、聞き手に毎回絵が届く。
あわせて、作品の音（BGM・効果音）と動画を語り手のページで実際に読み込み、長さが取れることを見る。
語り手・聞き手のページに例外が無いこと。"""
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
import types
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
REPO = Path(__file__).resolve().parents[2]
if len(sys.argv) < 2:
    raise SystemExit(__doc__)
SRC = Path(sys.argv[1]).resolve()
HERE = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(tempfile.mkdtemp(prefix='dk-e2e-sample-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
ROOT = HERE / 'fam'
WORK = ROOT / 'sample'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

_real = subprocess.Popen
EXTRA = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required']
# プレイヤーの表示の言葉はブラウザの言語で決まる（i18n.js）。作品の言語に合わせて起動する（英語の見本の画面を英語で撮るため）
if json.loads((SRC / 'work.json').read_text(encoding='utf-8')).get('language') != 'ja':
    EXTRA.append('--lang=en-US')
burn.subprocess = types.SimpleNamespace(Popen=lambda args, **kw: _real([args[0], *EXTRA, *args[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)

results = []


def ok(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('  OK  ' if cond else '  NG  ') + name + (f'  [{detail}]' if detail else ''))


shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(SRC, WORK)
shutil.copytree(REPO / 'player', ROOT / 'player')
work = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
n_slides = len(work['slides'])
media = sorted({c['file'] for s in work['slides'] for c in s.get('cues', [])})


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
# 音は Audio、動画は video で読み込み、長さ（秒）を返す。読めなければ -1
PROBE = """(async (url, isVideo) => new Promise((res) => {
  const el = isVideo ? Object.assign(document.createElement('video'), { muted: true, preload: 'auto' }) : new Audio();
  el.preload = 'auto';
  el.onloadedmetadata = () => res(el.duration);
  el.onerror = () => res(-1);
  setTimeout(() => res(-2), 20000);
  el.src = url;
}))"""


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
print(f'== {work["title"]}（{n_slides}枚・音と動画 {len(media)}本）')
nar, lis = burn.Browser(exe), burn.Browser(exe)
try:
    page(nar, base + '/player/narrator.html')
    nar.evaluate(f"{PICK}('pickWork', {json.dumps(listing())})")
    ok('語り手が作品を開ける', wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work'),
       nar.evaluate("document.getElementById('workTitle').textContent"))
    for f in media:
        d = nar.evaluate(f"{PROBE}({json.dumps('/sample/' + f)}, {json.dumps(f.endswith('.mp4'))})")
        ok(f'{f} が読み込めて長さが取れる', isinstance(d, (int, float)) and d > 0, d)
    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; document.getElementById('openRoom').click(); true")
    ok('受付が開き、合言葉が出る', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code'))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    page(lis, base + '/player/listen.html', 900, 600)
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'tester'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    ok('承認の依頼が語り手に届く', wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request'))
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('承認すると聞き手に1枚目の絵が出る', wait(lis, "!document.getElementById('picture').hidden && document.getElementById('picture').naturalWidth > 0", 'listener picture'))
    shot(lis, 'listener_01.png')
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    shot(nar, 'narrator_01.png')
    for k in range(2, n_slides + 1):
        before = lis.evaluate("document.getElementById('picture').src")
        nar.evaluate("document.getElementById('nextBtn').click(); true")
        ok(f'{k}枚目で聞き手の絵が変わる', wait(lis, f"document.getElementById('picture').src !== {json.dumps(before)} && document.getElementById('picture').naturalWidth > 0", f'slide {k}'))
        shot(lis, f'listener_{k:02d}.png')
        shot(nar, f'narrator_{k:02d}.png')
    ok('語り手が最後の枚まで進む', wait(nar, f"document.getElementById('navNo').textContent.startsWith('{n_slides}')", 'last'))
    shot(nar, 'narrator_last.png')
    ok('聞き手の画面に台本が無い', work['slides'][0]['notes'].split('\n')[-1][:12] not in lis.evaluate("document.body.innerText"))
    ok('語り手・聞き手のページに例外が無い', nar.evaluate("window.__errs.length") == 0 and lis.evaluate("window.__errs.length") == 0,
       json.dumps([nar.evaluate("window.__errs"), lis.evaluate("window.__errs")], ensure_ascii=False))
finally:
    nar.close()
    lis.close()
    server.shutdown()

bad = [n for n, c in results if not c]
print(f'\n{len(results) - len(bad)}/{len(results)} OK' + (f'  NG: {bad}' if bad else ''))
sys.exit(1 if bad else 0)
