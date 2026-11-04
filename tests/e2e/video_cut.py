"""上演中の動画の区間を直す1往復をまるごと通す（手で動かす確認。Edge・ffmpeg が要る）:
    python tests/e2e/video_cut.py [作業フォルダ]                       # 見本の写しに、区間2つの短い動画を足して通す
    python tests/e2e/video_cut.py [作業フォルダ] --work <作品フォルダ>   # 練習用に書き出した作品の写しで通す
 練習で動画を止めて「いまの位置を開始に／終わりに」→ 修正票（From・To・元の動画の秒）→ check_sheet は look →
動画を切り直したことにしてファイルを替え、作品を読み直す → 「変わった」で残る（自分では消えない）。
--work では、元の区間（source_segments）を持つ最初の動画で通す（区間が2つ以上ある動画があればそれを選ぶ）。
渡した作品フォルダ・作業用リポジトリの見本は変えない（写しで行う）。"""
import argparse
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser()
ap.add_argument('here', nargs='?', help='作業フォルダ（写し・撮った画面）。無ければ一時フォルダ')
ap.add_argument('--work', type=Path, help='練習用に書き出した作品フォルダ（写して使う）')
args = ap.parse_args()
for stream in (sys.stdout, sys.stderr):        # 日本語の Windows のコンソールでは出せない文字がある（— など）
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
HERE = Path(args.here).resolve() if args.here else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
WORK = HERE / 'rt' / 'work'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
CHECK = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'check_sheet.py'


def run(*a):
    r = subprocess.run([PY, *map(str, a)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f'$ {Path(str(a[0])).name} {" ".join(map(str, a[1:]))}  -> {r.returncode}')
    for line in (r.stdout + r.stderr).strip().splitlines()[-6:]:
        print('    ' + line)
    return r


def ffmpeg(*a):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *map(str, a)], check=True)


def clock(sec):
    """corrections.js の clock() と同じ（m:ss.s）"""
    tenths = round(max(0.0, sec) * 10)
    m = tenths // 600
    return f'{m}:{(tenths - m * 600) / 10:04.1f}'


def to_source(segs, t, at_end=False):
    """work.js の toSource() と同じ決め方（境目ちょうど: From は後ろの区間の頭・To は前の区間の終わり）"""
    head = 0.0
    for k, g in enumerate(segs):
        end = head + g['dur']
        if at_end and t > head and abs(t - end) <= 1e-6:
            return g['start'] + g['dur']
        if t < end or (k == len(segs) - 1 and t <= end + 1e-6):
            return g['start'] + (t - head)
        head = end
    return None


# ---------- 準備: 作品の写し ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
SAMPLE = args.work is None
if SAMPLE:
    # 見本の3枚目に、20秒の動画を足す。「元の動画の 0:30〜0:38 と 1:40〜1:52 をつないだもの」とする
    shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
    (WORK / 'videos').mkdir(exist_ok=True)
    ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=20', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=20',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', WORK / 'videos' / 'clip.mp4')
    script = (WORK / 'script.md').read_text(encoding='utf-8')
    script = script.replace('> [Picture] pictures/03.png\n', '> [Picture] pictures/03.png\n\n> [Video] videos/clip.mp4\n', 1)
    (WORK / 'script.md').write_text(script, encoding='utf-8')
    assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0
    # 家族の作品のビルダーは元の区間を知らない（切ったのは編集アプリ）。区間を知っている道具が書いた想定で足す
    w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
    cue = next(c for c in w['slides'][2]['cues'] if c.get('file') == 'videos/clip.mp4')
    cue['source_segments'] = [{'start': 30, 'dur': 8}, {'start': 100, 'dur': 12}]
    (WORK / 'work.json').write_text(json.dumps(w, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
else:
    shutil.copytree(args.work.resolve(), WORK)

w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
assert w.get('draft') is True, '練習用の版（--draft）で通す'
targets = []
for s in w['slides']:
    vids = [c for c in s['cues'] if c['type'] == 'video']
    for k, c in enumerate(vids, 1):
        if c.get('source_segments'):
            targets.append((len(c['source_segments']), s['number'], k, c))
assert targets, '元の区間（source_segments）を持つ動画が無い'
_, N, K, CUE = max(targets, key=lambda x: (x[0] >= 2, -x[1]))
SEGS = CUE['source_segments']
print(f'通す動画: スライド{N} の {K}本目 {CUE["file"]}  区間 {SEGS}')
# 1つ目の区間の真ん中を開始に、最後の区間の真ん中を終わりに（区間が1つなら 1/3 と 2/3）
if len(SEGS) >= 2:
    T_FROM = round(SEGS[0]['dur'] / 2, 1)
    T_TO = round(sum(g['dur'] for g in SEGS[:-1]) + SEGS[-1]['dur'] / 2, 1)
else:
    T_FROM, T_TO = round(SEGS[0]['dur'] / 3, 1), round(SEGS[0]['dur'] * 2 / 3, 1)
WANT = [f'## [Slide {N}] video {K}',
        f'From {clock(T_FROM)} (source {clock(to_source(SEGS, T_FROM))})',
        f'To {clock(T_TO)} (source {clock(to_source(SEGS, T_TO, True))})',
        'Comment: start later']

site = HERE / 'rt' / 'site'
shutil.copytree(REPO / 'player', site / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
    # ⚠️ Windows では .js が text/javascript で返らないことがある（モジュールが読めない）
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(HERE / 'rt')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'


def listing():
    """作品フォルダのファイル（URL のパスと、本当の更新日時）。プレイヤーには webkitRelativePath で渡す"""
    return [{'url': '/' + p.relative_to(HERE / 'rt').as_posix(), 'rel': p.relative_to(WORK.parent).as_posix(),
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
SHEET = """(async () => {
  const m = await import('/site/player/js/corrections.js');
  const key = Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'));
  return key ? m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 9, 26, 16, 0)) : '';
})()"""

b = burn.Browser(burn.find_browser())
ev = b.evaluate


def wait(js, what, tries=600):
    for _ in range(tries):
        try:
            if ev(js):
                return
        except burn.BurnError:
            pass
        time.sleep(0.05)
    raise SystemExit(f'timeout: {what}')


def seek(t):
    ev(f"(async () => {{ const v = document.getElementById('nvideo'); v.currentTime = {t}; "
       "await new Promise(r => v.addEventListener('seeked', r, { once: true })); return true; })()")
    time.sleep(0.3)


def shot(name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


try:
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1300, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

    # ---------- 1. 練習: その枚の動画を止めて、開始と終わりを入れる ----------
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    for _ in range(N - 1):
        ev("document.getElementById('nextBtn').click(); true")
        time.sleep(0.15)
    if not ev("document.getElementById('videoPick').hidden"):
        ev(f"document.querySelectorAll('#videoPick button')[{K - 1}].click(); true")
        time.sleep(0.2)
    wait("document.getElementById('nvideo').readyState >= 1", 'video')
    assert not ev("document.getElementById('cutBar').hidden"), '区間のバーが出ていない'
    assert ev("document.getElementById('seatBar').hidden"), '上演中の動画にコマのバーが出た'
    seek(T_FROM)
    print('1. 止めた位置:', ev("document.getElementById('cutNow').textContent"))
    ev("document.getElementById('cutFrom').click(); true")
    seek(T_TO)
    print('   止めた位置:', ev("document.getElementById('cutNow').textContent"))
    ev("document.getElementById('cutComment').value = 'start later'; document.getElementById('cutTo').click(); true")
    time.sleep(0.2)
    print('   バー:', ev("document.getElementById('cutSheet').textContent"))
    shot('cut_marked.png')
    md = ev(SHEET)
    print('   修正票:\n' + '\n'.join('     ' + line for line in md.strip().splitlines()))
    got = md.strip().split('\n\n', 1)[1].splitlines()
    assert got == WANT, f'\n got  {got}\n want {WANT}'
    sheet = HERE / 'rt' / 'sheet.md'
    sheet.write_text(md, encoding='utf-8')

    # ---------- 2. 書き戻しの確認: 区間は作り手が切り直すまで look（PENDING に数えない） ----------
    r = run(CHECK, WORK, sheet)
    if SAMPLE:
        assert r.returncode == 0 and f'look      [Slide {N}] video {K}' in r.stdout
    elif f'[Slide {N}] video {K}' not in r.stdout:
        print('   ⚠️ check_sheet がこの作品を読めなかった（台本を作業用リポジトリのビルダーで作っていない作品）')

    # ---------- 3. 作り手が切り直したことにする: 開始を後ろへずらした動画に替え、元の区間も直す ----------
    time.sleep(1.1)  # 動画の更新日時が確実に変わるように
    clip = WORK / CUE['file']
    tmp = clip.with_name('_recut.mp4')
    ffmpeg('-ss', T_FROM, '-i', clip, '-c', 'copy', tmp)
    tmp.replace(clip)
    w = json.loads((WORK / 'work.json').read_text(encoding='utf-8'))
    c = [x for x in w['slides'][N - 1]['cues'] if x['type'] == 'video'][K - 1]
    c['source_segments'][0] = {'start': SEGS[0]['start'] + T_FROM, 'dur': SEGS[0]['dur'] - T_FROM}
    (WORK / 'work.json').write_text(json.dumps(w, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # ---------- 4. プレイヤーで作品を読み直す ----------
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('4. 読み直し:', ev("document.getElementById('reloadNote').textContent"))
    ev("document.getElementById('sheetBtn').click(); true")
    time.sleep(0.3)
    lst = ev("document.getElementById('sheetList').innerText")
    print('   修正票の一覧:', lst.replace('\n', ' | '))
    assert '変わった' in lst or 'changed' in lst
    assert ev("Object.keys(localStorage).filter(k => k.startsWith('dk-corrections:')).length") == 1, '自分で消えてはいけない'
    shot('cut_after_reload.png')
    errs = ev("window.__errs")
    print('ページの例外:', errs)
    assert not errs
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
