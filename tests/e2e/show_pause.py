"""上演の一時停止・再開・最初からを、語り手と聞き手の端末で鳴っている音・動画で確かめる（2台。Edge・ffmpeg・インターネット（PeerJS の仲介）が要る）:
    python tests/e2e/show_pause.py [作業フォルダ]
 見本の写しに BGM（1枚目から・4枚目から）と動画（3枚目）を足す → 聞き手を1台つなぐ → 開演 → 2枚目 →
 一時停止: 両方の BGM が止まり、時計が進まない → 再開: 止めた位置から → 3枚目で動画を流す途中で一時停止: 両方の動画が止まる →
 再開: 動画が止めた位置から → 一時停止 → 最初から: 聞き手はつながったまま1枚目・無音、ボタンは「開演」 →
 もう一度開演: 表紙の曲が頭から。設計: plans/show-pause.md。作業用リポジトリの見本は変えない（写しで行う）。"""
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
WORK = ROOT / 'work'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

# 触れる前の音をブラウザが止めないように
_real = subprocess.Popen
burn.subprocess = types.SimpleNamespace(Popen=lambda a, **kw: _real([a[0], '--autoplay-policy=no-user-gesture-required', *a[1:]], **kw),
                                        DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)
BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
failures = []


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


def ffmpeg(*a):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *map(str, a)], check=True)


# ---------- 準備: 見本の写しに BGM 2曲と動画1本 ----------
shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
shutil.copytree(REPO / 'player', ROOT / 'player')
(WORK / 'sounds').mkdir(exist_ok=True)
(WORK / 'videos').mkdir(exist_ok=True)
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=330:duration=120', '-c:a', 'libmp3lame', WORK / 'sounds' / 'first.mp3')
ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=550:duration=120', '-c:a', 'libmp3lame', WORK / 'sounds' / 'next.mp3')
ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15:duration=40', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=40',
       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', WORK / 'videos' / 'clip.mp4')
script = (WORK / 'script.md').read_text(encoding='utf-8')
script = script.replace('## [Slide 1] Cover\n', '## [Slide 1] Cover\n\n> [BGM] sounds/first.mp3\n', 1)
script = script.replace('> [Picture] pictures/03.png\n', '> [Picture] pictures/03.png\n\n> [Video] videos/clip.mp4\n', 1)
script = script.replace('## [Slide 4] The end\n', '## [Slide 4] The end\n\n> [BGM] sounds/next.mp3\n', 1)
(WORK / 'script.md').write_text(script, encoding='utf-8')
r = subprocess.run([sys.executable, str(BUILD), str(WORK), '--draft', '--skip-text'], capture_output=True, text=True, encoding='utf-8', errors='replace')
assert r.returncode == 0, r.stdout + r.stderr
w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
assert [c['type'] for c in w['slides'][2]['cues']].count('video') == 1 and w['slides'][0]['cues'][0]['type'] == 'bgm'

# ---------- 配る: player/_headers を当てる ----------
HEADERS = {}
for line in (REPO / 'player' / '_headers').read_text(encoding='utf-8').splitlines():
    if line.startswith('  ') and ':' in line:
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


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Site, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://localhost:{server.server_address[1]}'
files = [{'url': '/' + p.relative_to(ROOT).as_posix(), 'rel': p.relative_to(ROOT).as_posix(), 'mtime': int(p.stat().st_mtime * 1000)}
         for p in WORK.rglob('*') if p.is_file()]
PICK = """(async (files) => {
  const list = [];
  for (const f of files) {
    const blob = await (await fetch(f.url, { cache: 'no-store' })).blob();
    const file = new File([blob], f.rel.split('/').pop(), { lastModified: f.mtime });
    Object.defineProperty(file, 'webkitRelativePath', { value: f.rel });
    list.push(file);
  }
  const input = document.getElementById('pickWork');
  Object.defineProperty(input, 'files', { value: list, configurable: true });
  input.dispatchEvent(new Event('change'));
  return true;
})"""
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")


def open_page(b, url, w, h):
    b.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': url}, session=True)
    time.sleep(1.5)
    b.evaluate(TRAP)


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


exe = burn.find_browser()
nar, lis = burn.Browser(exe), burn.Browser(exe)
FIRST = None
NA = "__dk.audio()"
LA = "__dkl.audio()"
BTN = "(() => { const b = document.getElementById('startShowBar'); return { text: b.textContent, phase: b.dataset.phase, restart: !document.getElementById('restartShowBar').hidden }; })()"
try:
    open_page(nar, base + '/player/narrator.html?test', 1600, 1100)
    nar.evaluate(f"localStorage.clear(); {PICK}({json.dumps(files)})")
    wait(nar, "document.getElementById('workTitle').textContent.length > 0", 'work')
    FIRST = nar.evaluate("__dk.audioId('sounds/first.mp3')")
    NEXT = nar.evaluate("__dk.audioId('sounds/next.mp3')")

    nar.evaluate("document.querySelector('[data-goto=room]').click(); document.getElementById('expected').value = 1; "
                 "document.getElementById('openRoom').click(); true")
    ok('受付が開く', wait(nar, "/\\d/.test(document.getElementById('code').textContent)", 'code', 600))
    code = nar.evaluate("document.getElementById('code').textContent").replace(' ', '')
    open_page(lis, base + '/player/listen.html?test', 900, 506)
    lis.evaluate(f"document.getElementById('code').value = '{code}'; document.getElementById('name').value = 'far'; "
                 "document.querySelector('input[name=mic][value=listen]').checked = true; "
                 "document.getElementById('joinForm').requestSubmit(); true")
    wait(nar, "document.querySelectorAll('#requests button').length > 0", 'request', 600)
    nar.evaluate("document.querySelector('#requests button').click(); true")
    ok('聞き手に1枚目の絵が出る', wait(lis, "!document.getElementById('picture').hidden && document.getElementById('picture').naturalWidth > 0", 'picture', 600))
    nar.evaluate("document.querySelector('[data-goto=show]').click(); true")
    time.sleep(0.3)
    b0 = nar.evaluate(BTN)
    ok('開演前: ボタンは「開演」・「最初から」は出ない', b0['phase'] == 'before' and not b0['restart'], json.dumps(b0, ensure_ascii=False))

    # ---------- 開演 → 2枚目 → 一時停止 ----------
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('開演: 聞き手の端末で表紙の曲が鳴る', wait(lis, f"{LA}.playing && {LA}.bgm === '{FIRST}'", 'listener bgm', 600), json.dumps(lis.evaluate(LA)))
    b1 = nar.evaluate(BTN)
    ok('上演中: ボタンは「一時停止」・「最初から」は出ない', b1['phase'] == 'playing' and not b1['restart'], json.dumps(b1, ensure_ascii=False))
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    time.sleep(3)
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('一時停止: 語り手の端末の BGM が止まる', wait(nar, f"!{NA}.playing && {NA}.bgm === '{FIRST}'", 'narrator paused'), json.dumps(nar.evaluate(NA)))
    ok('一時停止: 聞き手の端末の BGM が止まる', wait(lis, f"!{LA}.playing && {LA}.bgm === '{FIRST}'", 'listener paused', 600), json.dumps(lis.evaluate(LA)))
    b2 = nar.evaluate(BTN)
    ok('一時停止中: ボタンは「再開」・横に「最初から」', b2['phase'] == 'paused' and b2['restart'], json.dumps(b2, ensure_ascii=False))
    time.sleep(0.5)
    p_nar, p_lis, c1 = nar.evaluate(f"{NA}.pos"), lis.evaluate(f"{LA}.pos"), nar.evaluate("document.getElementById('clock').textContent")
    time.sleep(2.5)
    p_lis2, c2 = lis.evaluate(f"{LA}.pos"), nar.evaluate("document.getElementById('clock').textContent")
    ok('一時停止中: 聞き手の BGM の位置が進まない', abs(p_lis2 - p_lis) < 0.05, f'{p_lis:.2f} → {p_lis2:.2f}')
    ok('一時停止中: 時計が進まない', c1 == c2 and c1 != '', f'{c1} / {c2}')

    # ---------- 再開 ----------
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('再開: 聞き手の端末で同じ曲が鳴る', wait(lis, f"{LA}.playing && {LA}.bgm === '{FIRST}'", 'listener resumed', 600), json.dumps(lis.evaluate(LA)))
    time.sleep(0.3)
    p_lis3 = lis.evaluate(f"{LA}.pos")
    ok('再開: 止めた位置から（±1秒）', abs(p_lis3 - p_lis) < 1.0, f'止めた {p_lis:.2f} → 再開 {p_lis3:.2f}（語り手 {p_nar:.2f}）')
    ok('再開: ボタンは「一時停止」に戻る', nar.evaluate(BTN)['phase'] == 'playing')

    # ---------- 3枚目の動画の途中で一時停止 ----------
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    wait(nar, "document.getElementById('nvideo').readyState >= 1", 'video')
    # 聞き手が動画を受け取り終えるまで、語り手の再生は待たされる（受け渡しの途中で流すと止められる）
    ok('聞き手に動画が届く', wait(lis, "(() => { const r = __dkl.view() && __dkl.view().recv; return !!r && r.all > 0 && r.got >= r.all; })()", 'listener received', 1200),
       json.dumps(lis.evaluate("__dkl.view()")))
    # ⚠️ 2台目の窓が前に出ると、語り手のページは隠れた扱い（visibilityState: hidden）になり、ブラウザが音を消した動画を自分で止める
    #    （JS からの pause は0件だった）。語り手の窓を前に出し、動画の音も消さない
    nar.call('Page.bringToFront', {}, session=True)
    nar.evaluate("(async () => { await document.getElementById('nvideo').play(); return true; })()")
    ok('語り手の動画が流れる', wait(nar, "!document.getElementById('nvideo').paused && document.getElementById('nvideo').currentTime > 0.5", 'narrator video play'),
       json.dumps(nar.evaluate("({ p: __dk.session().playback, paused: document.getElementById('nvideo').paused, t: document.getElementById('nvideo').currentTime, err: String(document.getElementById('nvideo').error && document.getElementById('nvideo').error.message) })")))
    ok('聞き手の端末で動画が流れる', wait(lis, "!document.getElementById('lvideo').paused && document.getElementById('lvideo').currentTime > 1", 'listener video play', 600),
       json.dumps(lis.evaluate("({ paused: document.getElementById('lvideo').paused, t: document.getElementById('lvideo').currentTime, hidden: document.getElementById('lvideo').hidden })")))
    time.sleep(2)
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('一時停止: 語り手の動画が止まる', wait(nar, "document.getElementById('nvideo').paused", 'narrator video paused'))
    ok('一時停止: 聞き手の動画が止まる', wait(lis, "document.getElementById('lvideo').paused", 'listener video paused', 600))
    time.sleep(0.5)
    v_nar = nar.evaluate("document.getElementById('nvideo').currentTime")
    v_lis = lis.evaluate("document.getElementById('lvideo').currentTime")
    time.sleep(2)
    v_lis2 = lis.evaluate("document.getElementById('lvideo').currentTime")
    ok('一時停止中: 聞き手の動画の位置が進まない', abs(v_lis2 - v_lis) < 0.05, f'{v_lis:.2f} → {v_lis2:.2f}（語り手 {v_nar:.2f}）')
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('再開: 語り手の動画が流れ直す', wait(nar, "!document.getElementById('nvideo').paused", 'narrator video resumed'))
    ok('再開: 聞き手の動画が流れ直す', wait(lis, "!document.getElementById('lvideo').paused", 'listener video resumed', 600))
    time.sleep(0.3)
    v_lis3 = lis.evaluate("document.getElementById('lvideo').currentTime")
    ok('再開: 動画は止めた位置から（±1秒）', abs(v_lis3 - v_lis) < 1.0, f'止めた {v_lis:.2f} → 再開 {v_lis3:.2f}')

    # ---------- 一時停止中に枚を動かす（止めたまま） ----------
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    wait(nar, "document.getElementById('nvideo').paused", 'paused again')
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    time.sleep(1.5)
    ok('一時停止中に別の曲の枚へ: 聞き手は鳴らさない', not lis.evaluate(f"{LA}.playing"), json.dumps(lis.evaluate(LA)))
    ok('一時停止中に枚を動かしても、ボタンは「再開」のまま', nar.evaluate(BTN)['phase'] == 'paused')

    # ---------- 最初から ----------
    nar.evaluate("document.getElementById('restartShowBar').click(); true")
    ok('最初から: 語り手は1枚目', wait(nar, "__dk.session().slide === 1", 'narrator slide 1'))
    ok('最初から: 聞き手はつながったまま1枚目', wait(lis, "__dkl.view() && __dkl.view().slide === 1", 'listener slide 1', 600), json.dumps(lis.evaluate("__dkl.view()")))
    ok('最初から: 聞き手の BGM は無音', wait(lis, f"!{LA}.playing", 'listener silent', 600), json.dumps(lis.evaluate(LA)))
    ok('最初から: 語り手の BGM も無音', wait(nar, f"!{NA}.playing", 'narrator silent'), json.dumps(nar.evaluate(NA)))
    b3 = nar.evaluate(BTN)
    ok('最初から: ボタンは「開演」・「最初から」は隠れる', b3['phase'] == 'before' and not b3['restart'], json.dumps(b3, ensure_ascii=False))
    ok('最初から: 時計は消える', nar.evaluate("document.getElementById('clock').textContent") == '')
    ok('最初から: 聞き手は承認済みのまま', nar.evaluate("[...__dk.session().peers.values()].filter((p) => p.status === 'approved').length") == 1)

    # ---------- もう一度開演 ----------
    time.sleep(2.5)   # 聞き手の古い曲がフェードアウトし終わるまで
    nar.evaluate("document.getElementById('startShowBar').click(); true")
    ok('もう一度開演: 聞き手の端末で表紙の曲が鳴る', wait(lis, f"{LA}.playing && {LA}.bgm === '{FIRST}'", 'listener bgm again', 600), json.dumps(lis.evaluate(LA)))
    time.sleep(0.3)
    ok('もう一度開演: 表紙の曲は頭から（2秒以内）', lis.evaluate(f"{LA}.pos") < 2.0, f"{lis.evaluate(f'{LA}.pos'):.2f}")
    ok('語り手・聞き手のページに例外が0件', nar.evaluate("window.__errs.length") == 0 and lis.evaluate("window.__errs.length") == 0,
       json.dumps([nar.evaluate("window.__errs"), lis.evaluate("window.__errs")]))
finally:
    nar.close()
    lis.close()
    server.shutdown()

print('ALL OK' if not failures else f'NG {len(failures)}: ' + ' / '.join(failures))
sys.exit(1 if failures else 0)
