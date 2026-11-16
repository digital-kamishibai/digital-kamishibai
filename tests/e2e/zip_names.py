"""作品の zip を、準備の画面の「保存した版・作品の zip を開く」で開く（docs/work-format.md §1 Zip）を確かめる（Edge が要る）:
    python tests/e2e/zip_names.py [ほかの道具で作った作品の zip ...]
 見本（examples/sample-story）の写しを zip にして開く → 作品として開き、足りない素材が無い。
 日本語のファイル名の作品（絵のファイル名の2バイト目に '\\' と同じ 0x5C を含む）を、UTF-8 の印付きと、
 印なしの Shift_JIS（日本語の Windows の「圧縮フォルダー」の書き方）で詰めて開く → どちらも素材が見つかる。
 引数の zip（例: エクスプローラーで作ったもの）も同じように開く。zip はページへ直に渡すので、DK_E2E_BASE の箱でも回せる。
 ページに例外が無いこと。"""
import base64
import functools
import http.server
import io
import json
import os
import sys
import threading
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


class SjisInfo(zipfile.ZipInfo):
    """名前を Shift_JIS で書き、UTF-8 の印を付けない（日本語の Windows の「圧縮フォルダー」と同じ）"""
    def _encodeFilenameFlags(self):
        return self.filename.encode('cp932'), self.flag_bits & ~0x800


def work_zip(top, names, sjis=False):
    """見本の作品を、絵のファイル名を names で替えて zip に詰める（絵の無い枚と合図は外す: 見本に動画のファイルは無い）"""
    src = REPO / 'examples' / 'sample-story'
    work = json.loads((src / 'work.json').read_text(encoding='utf-8'))
    work['slides'] = [s for s in work['slides'] if s['picture']]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        def put(path, data):
            info = (SjisInfo if sjis else zipfile.ZipInfo)(f'{top}/{path}', (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
        for s in work['slides']:
            if s['picture']:
                put(names.get(s['picture'], s['picture']), (src / s['picture']).read_bytes())
                s['picture'] = names.get(s['picture'], s['picture'])
            s['cues'] = []
        put('work.json', json.dumps(work, ensure_ascii=False))
    return buf.getvalue()


JP = {'pictures/01.jpg': '絵/表紙.jpg', 'pictures/02.png': '絵/あらし.png', 'pictures/03.png': '絵/朝ソ能.png'}
zips = [
    ('見本の写しの zip（ASCII の名前）', 'my-work.zip', work_zip('my-work', {})),
    ('日本語のファイル名・UTF-8 の印付き', 'utf8.zip', work_zip('わたしの話', JP)),
    ('日本語のファイル名・印なしの Shift_JIS', 'sjis.zip', work_zip('わたしの話', JP, sjis=True)),
]
for arg in sys.argv[1:]:
    p = Path(arg)
    zips.append((f'引数の zip（{p.name}）', p.name, p.read_bytes()))

for title, _, data in zips:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        print(f'{title}: ' + ', '.join(f'{"UTF-8 の印" if i.flag_bits & 0x800 else "印なし"}' for i in z.infolist()[:1]))


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(REPO / 'player')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = os.environ.get('DK_E2E_BASE', '').rstrip('/') or f'http://localhost:{server.server_address[1]}'
print(f'base: {base}')
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")


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


def open_prep(b):
    b.call('Page.navigate', {'url': base + '/narrator.html?test'}, session=True)
    wait(b, "location.search === '?test' && window.__dk && __dk.site() === null && __dk.screen() === 'prep'", 'prep')
    b.evaluate(TRAP)


nar = burn.Browser(burn.find_browser())
try:
    nar.call('Emulation.setLocaleOverride', {'locale': 'ja-JP'}, session=True)
    for title, name, data in zips:
        open_prep(nar)
        nar.evaluate(f"(() => {{ const b = Uint8Array.from(atob({json.dumps(base64.b64encode(data).decode())}), (c) => c.charCodeAt(0)); "
                     f"const dt = new DataTransfer(); dt.items.add(new File([b], {json.dumps(name)}, {{ type: 'application/zip' }})); "
                     "const i = document.getElementById('openScript'); i.files = dt.files; i.dispatchEvent(new Event('change')); })(); true")
        opened = wait(nar, "document.getElementById('workTitle').textContent.length > 0 && __dk.screen() !== 'prep'", name, 1200)
        ok(f'{title}: 作品として開き、足りない素材が無い',
           opened and nar.evaluate("document.getElementById('missing').hidden && document.getElementById('loadError').hidden"),
           nar.evaluate("document.getElementById('missing').textContent + document.getElementById('loadError').textContent"))
        ok(f'{title}: ページに例外が無い', not nar.evaluate("window.__errs"), json.dumps(nar.evaluate("window.__errs"), ensure_ascii=False))
finally:
    nar.close()
    server.shutdown()

print('\n' + ('すべて OK' if not failures else f'NG {len(failures)} 件: ' + ', '.join(failures)))
sys.exit(1 if failures else 0)
