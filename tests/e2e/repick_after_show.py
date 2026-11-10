"""開演したあとに作品フォルダを選び直すと、開演の前に戻ることを確かめる（1台。Edge・ffmpeg が要る）:
    python tests/e2e/repick_after_show.py [作業フォルダ]
 見本の写しを2つ（1枚目の BGM が違う）作る → 1つ目を選んで練習で開演（本物のクリック）→
 「作品を読み直す」のあとも「上演中」のまま BGM が鳴り続ける →
 準備の画面で2つ目を選び直す → 開演のボタンが押せる・BGM が止まる・時計が消える →
 もう一度開演すると、2つ目の1枚目の曲が鳴る。
 ⚠️ 開演は本物のクリックで押す（JS の click() では engine.unlock() の resume が終わらず、開演まで進まない）。
 作品フォルダの選び方（showDirectoryPicker）は差し替え、input の change で渡す。"""
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

REPO = Path(__file__).resolve().parents[2]
for stream in (sys.stdout, sys.stderr):        # 日本語の Windows のコンソールでは出せない文字がある
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
ROOT = HERE / 'rt'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

# 開演でマイクを開くので、偽のマイクで許可の確認を出さない（触れる前の音は止めたまま。開演は本物のクリックで押す）
_real = subprocess.Popen
burn.subprocess = types.SimpleNamespace(
    Popen=lambda a, **kw: _real([a[0], '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', *a[1:]], **kw),
    DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)
BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


def make_work(name, title, freq):
    """見本の写し。題を変え、1枚目に BGM（sounds/<name>.mp3）を足す"""
    w = ROOT / name
    shutil.copytree(REPO / 'examples' / 'sample-story', w)
    (w / 'sounds').mkdir(exist_ok=True)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency={freq}:duration=60', '-af', 'volume=-14dB',
                    '-ac', '2', '-c:a', 'libmp3lame', str(w / 'sounds' / f'{name}.mp3')], check=True)
    script = (w / 'script.md').read_text(encoding='utf-8')
    script = script.replace('## [Slide 1] Cover\n', f'## [Slide 1] Cover\n\n> [BGM] sounds/{name}.mp3\n', 1)
    lines = script.split('\n')
    head = next(i for i, x in enumerate(lines) if x.startswith('# '))
    lines[head] = f'# {title}'
    (w / 'script.md').write_text('\n'.join(lines), encoding='utf-8')
    r = subprocess.run([sys.executable, str(BUILD), str(w), '--skip-text'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert r.returncode == 0, r.stdout + r.stderr
    return [{'url': '/' + p.relative_to(ROOT).as_posix(), 'rel': p.relative_to(ROOT).as_posix(), 'mtime': int(p.stat().st_mtime * 1000)}
            for p in w.rglob('*') if p.is_file()]


shutil.rmtree(ROOT, ignore_errors=True)
ROOT.mkdir(parents=True)
shutil.copytree(REPO / 'player', ROOT / 'player')
FILES_A = make_work('first', 'Repick first', 330)
FILES_B = make_work('second', 'Repick second', 550)


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://localhost:{server.server_address[1]}'
PICK = """(async (id, files) => {
  const list = [];
  for (const f of files) {
    const blob = await (await fetch(f.url, { cache: 'no-store' })).blob();
    const file = new File([blob], f.rel.split('/').pop(), { lastModified: f.mtime });
    Object.defineProperty(file, 'webkitRelativePath', { value: f.rel });
    list.push(file);
  }
  const input = document.getElementById(id);
  Object.defineProperty(input, 'files', { value: list, configurable: true });
  input.dispatchEvent(new Event('change'));
  return true;
})"""
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")
BUTTONS = "[...['startShow', 'startShowBar']].map((id) => { const b = document.getElementById(id); return { disabled: b.disabled, text: b.textContent }; })"


def wait(b, js, what, tries=400, step=0.05):
    for _ in range(tries):
        try:
            if b.evaluate(js):
                return True
        except burn.BurnError:
            pass
        time.sleep(step)
    print('  timeout: ' + what)
    return False


def real_click(b, id_):
    """本物のクリック（ブラウザは触れた操作の中でだけ音を出させる）"""
    x, y = b.evaluate(f"(() => {{ const r = document.getElementById('{id_}').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()")
    for kind in ('mousePressed', 'mouseReleased'):
        b.call('Input.dispatchMouseEvent', {'type': kind, 'x': x, 'y': y, 'button': 'left', 'buttons': 1, 'clickCount': 1}, session=True)


def pick(b, id_, files, title):
    b.evaluate(f"{PICK}('{id_}', {json.dumps(files)})")
    return wait(b, f"document.getElementById('workTitle').textContent === {json.dumps(title)}", 'work ' + title)


nar = burn.Browser(burn.find_browser())
try:
    nar.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1100, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    nar.call('Page.navigate', {'url': base + '/player/narrator.html?test'}, session=True)
    time.sleep(1.5)
    nar.evaluate(TRAP)
    nar.evaluate("localStorage.clear(); true")
    before = nar.evaluate(BUTTONS)[0]['text']   # 開演前のボタンの文字

    # ---------- 1つ目を開いて、練習で開演 ----------
    ok('1つ目の作品が開く', pick(nar, 'pickWork', FILES_A, 'Repick first'))
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    real_click(nar, 'startShowBar')
    idA = nar.evaluate("__dk.audioId('sounds/first.mp3')")
    ok('開演すると1つ目の1枚目の曲が鳴る', wait(nar, f"__dk.audio().playing && __dk.audio().bgm === {json.dumps(idA)}", 'bgm A'),
       json.dumps(nar.evaluate("__dk.audio()")))
    started = nar.evaluate(BUTTONS)
    ok('開演のボタンは両方とも「上演中」で押せない', all(b['disabled'] and b['text'] != before for b in started), json.dumps(started, ensure_ascii=False))
    ok('上演の時計が進む', wait(nar, "document.getElementById('clock').textContent.length > 0", 'clock'))

    # ---------- 作品を読み直す（E10）: 開演を続ける ----------
    nar.evaluate(f"{PICK}('reloadWork', {json.dumps(FILES_A)})")
    time.sleep(1.5)
    ok('読み直したあとも「上演中」のまま', nar.evaluate(BUTTONS) == started, json.dumps(nar.evaluate(BUTTONS), ensure_ascii=False))
    ok('読み直したあとも開演済みで、曲が鳴り続ける',
       nar.evaluate("__dk.session().audio.started") and wait(nar, f"__dk.audio().playing && __dk.audio().bgm === {json.dumps(idA)}", 'bgm A again'),
       json.dumps(nar.evaluate("__dk.audio()")))
    ok('読み直したあとも時計が続く', nar.evaluate("document.getElementById('clock').textContent.length > 0"))

    # ---------- 準備の画面で2つ目を選び直す: 開演の前に戻る ----------
    nar.evaluate("document.querySelector('[data-screen=prep]').click(); true")
    time.sleep(0.3)
    ok('2つ目の作品が開く', pick(nar, 'pickWork', FILES_B, 'Repick second'))
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    after = nar.evaluate(BUTTONS)
    ok('開演のボタンが両方とも押せる・開演前の文字に戻る', all(not b['disabled'] and b['text'] == before for b in after), json.dumps(after, ensure_ascii=False))
    ok('開演前に戻る（session.audio）', not nar.evaluate("__dk.session().audio.started"), json.dumps(nar.evaluate("__dk.session().audio")))
    ok('語り手の端末の BGM が止まる', wait(nar, "__dk.audio().bgm === null", 'bgm off'), json.dumps(nar.evaluate("__dk.audio()")))
    ok('時計が消える', nar.evaluate("document.getElementById('clock').textContent === ''"), nar.evaluate("document.getElementById('clock').textContent"))
    ok('話し声で BGM を下げていない', not nar.evaluate("__dk.audio().talking"))

    # ---------- もう一度開演: 2つ目の1枚目の曲が鳴る ----------
    real_click(nar, 'startShowBar')
    idB = nar.evaluate("__dk.audioId('sounds/second.mp3')")
    ok('もう一度開演すると2つ目の1枚目の曲が鳴る', wait(nar, f"__dk.audio().playing && __dk.audio().bgm === {json.dumps(idB)}", 'bgm B'),
       json.dumps(nar.evaluate("__dk.audio()")))
    ok('もう一度「上演中」になる', all(b['disabled'] for b in nar.evaluate(BUTTONS)))
    ok('時計がまた進む', wait(nar, "document.getElementById('clock').textContent.length > 0", 'clock again'))
    ok('ページに例外が0件', nar.evaluate("window.__errs.length") == 0, json.dumps(nar.evaluate("window.__errs")))
finally:
    nar.close()
    server.shutdown()

print('ALL OK' if not failures else f'NG {len(failures)}: ' + ' / '.join(failures))
sys.exit(1 if failures else 0)
