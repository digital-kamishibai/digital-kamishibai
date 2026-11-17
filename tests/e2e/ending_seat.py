"""エンディング動画のコマを絵コンテのカードで直す1往復をまるごと通す（手で動かす確認。Edge・ffmpeg が要る）:
    python tests/e2e/ending_seat.py [作業フォルダ]
 絵コンテのカードで席を選ぶ（書きかけは席ごと・再生やシークで番号が変わらない）→「直したい」「外したい」（その場で取り消せる）→
動かない席（固定・閉じの絵）は外せない → 閉じたときの古い流れ（止めて指す）→ 修正票（見出しの remove）→
書き戻し（Skill の手順: 外す＝--move で詰めて --placeholder・移しすぎは道具が止める）→ 作り手が選ぶ（ここでは代わりに1つ選ぶ）→
エンディング動画と練習用の版を作り直す → プレイヤーで読み直して「変わった」。
作業用リポジトリの見本は変えない（写しで行う。写しの定義は6席に広げる: 5 は固定、6 は閉じの絵）。"""
import base64
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for stream in (sys.stdout, sys.stderr):        # 日本語の Windows のコンソールでは出せない文字がある（· — など）
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
# 作業場所（見本の写し・撮った画面）。引数で渡さなければ一時フォルダ
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='dk-e2e-'))
HERE.mkdir(parents=True, exist_ok=True)
print(f'work: {HERE}')
WORK = HERE / 'rt' / 'sample'
PY = sys.executable
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import burn  # noqa: E402

LADDER = REPO / 'ladder' / 'ending-video' / 'build_ending_video.py'
BUILD = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'
CHECK = REPO / 'skills' / 'digital-kamishibai' / 'scripts' / 'check_sheet.py'


def run(*args):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    print(f'$ {" ".join(Path(str(a)).name if i == 0 else str(a) for i, a in enumerate(args))}  -> {r.returncode}')
    for line in (r.stdout + r.stderr).strip().splitlines()[-4:]:
        print('    ' + line)
    return r


# ---------- 準備: 見本の写し（6席に広げる）・曲・エンディング動画・練習用の版 ----------
shutil.rmtree(HERE / 'rt', ignore_errors=True)
shutil.copytree(REPO / 'examples' / 'sample-story', WORK)
DEFINITION = WORK / 'ending_video.json'
data = json.loads(DEFINITION.read_text(encoding='utf-8'))
pics = ['pictures/02.png', 'pictures/03.png', 'pictures/01.jpg']
data['duration_sec'] = 30.0
data['frames'] = [{'i': n, 'at': 5.0 * (n - 1), 'dur': 5.0, 'xfade': 0.8 if n < 6 else 0.0, 'root': 'work',
                   'src': pics[(n - 1) % 3], 'status': 'picked'} for n in range(1, 7)]
data['frames'][4]['pin'] = 'the first line of the chorus'
data['frames'][5].update(kind='final', src='pictures/01.jpg', zoom=1.0, status='confirmed')
DEFINITION.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
(WORK / 'sounds').mkdir()
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=30',
                '-af', 'volume=0.3', str(WORK / 'sounds' / 'ending.mp3')], check=True)
assert run(LADDER, WORK).returncode == 0
assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0

site = HERE / 'rt' / 'site'
shutil.copytree(REPO / 'player', site / 'player')


class Quiet(http.server.SimpleHTTPRequestHandler):
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

b = burn.Browser(burn.find_browser())
ev = b.evaluate


def wait(js, what, tries=300):
    for _ in range(tries):
        try:
            if ev(js):
                return
        except burn.BurnError:
            pass
        time.sleep(0.05)
    raise SystemExit(f'timeout: {what}')


def shot(name):
    (HERE / name).write_bytes(base64.b64decode(b.call('Page.captureScreenshot', {'format': 'png'}, session=True)['data']))


def card(n):
    return f"document.querySelectorAll('.board-card')[{n - 1}]"


def click_card(n):
    ev(f"{card(n)}.click(); true")
    time.sleep(0.3)


def text(el):
    return ev(f"document.getElementById('{el}').textContent")


def prop(el, name):
    return ev(f"document.getElementById('{el}').{name}")


def click(el):
    ev(f"document.getElementById('{el}').click(); true")
    time.sleep(0.2)


def seek(sec):
    ev("(async () => { const v = document.getElementById('nvideo'); v.currentTime = %s; "
       "await new Promise(r => v.addEventListener('seeked', r, { once: true })); return true; })()" % sec)
    time.sleep(0.3)


def play():
    """ヘッドレスでは音のある再生が止められるので、音を消して流す（席の判定には音は要らない）"""
    assert ev("(async () => { const v = document.getElementById('nvideo'); v.muted = true; "
              "try { await v.play(); } catch (e) { return String(e); } return !v.paused; })()") is True
    time.sleep(0.5)


def note(s):
    ev("(() => { const c = document.getElementById('seatComment'); c.value = %s; "
       "c.dispatchEvent(new Event('input')); return true; })()" % json.dumps(s))


def sheet_markdown():
    return ev("""(async () => {
      const m = await import('/site/player/js/corrections.js');
      const key = Object.keys(localStorage).find(k => k.startsWith('dk-corrections:'));
      if (!key) return '';  // 件が無くなると保存ごと消える
      return m.sheetMarkdown(JSON.parse(localStorage.getItem(key)), new Date(2026, 10, 17, 16, 0));
    })()""")


try:
    b.call('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1300, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    b.call('Page.navigate', {'url': base + '/site/player/narrator.html'}, session=True)
    wait("!!document.getElementById('pickWork')", 'page')
    time.sleep(0.5)
    ev("localStorage.clear(); window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
       "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")

    # ---------- 1. 練習: 最後の枚でエンディング動画の絵コンテを開く ----------
    ev(f"{PICK}('pickWork', {json.dumps(listing())})")
    wait("document.getElementById('workTitle').textContent.length > 0", 'work loaded')
    ev("document.querySelector('[data-goto=show]').click(); true")
    for _ in range(3):
        ev("document.getElementById('nextBtn').click(); true")
        time.sleep(0.2)
    wait("document.getElementById('nvideo').readyState >= 1", 'video')
    click('boardBtn')
    wait("document.querySelectorAll('.board-card').length === 6", 'storyboard')
    print('1. 開いた直後:', text('seatNow'), '|', text('seatTarget'), text('seatPoint'), '|', text('seatRemove'))
    assert ev(f"{card(1)}.classList.contains('chosen')"), '開いた直後は映っている席（1）'

    # ---------- 2. カード 3 でひとことを書く → カード 4 では欄が空・ボタンは 4 → カード 3 に戻ると書きかけが戻る ----------
    click_card(3)
    note('too dark')
    click_card(4)
    assert prop('seatComment', 'value') == '', '前の席の書きかけを持ち越さない'
    assert text('seatTarget') == '4 番：', text('seatTarget')
    click_card(3)
    assert prop('seatComment', 'value') == 'too dark'
    print('2. 席ごとの書きかけ: ok |', text('seatTarget'), text('seatPoint'), '|', text('seatRemove'))

    # ---------- 3. 再生・シークしてもボタンの番号は選んだ席のまま（再生中でも押せる） ----------
    play()
    seek(1.5)
    assert not prop('nvideo', 'paused'), '再生したまま'
    assert text('seatTarget') == '3 番：' and not prop('seatRemove', 'disabled'), text('seatTarget')
    assert ev(f"{card(1)}.classList.contains('now') && {card(3)}.classList.contains('chosen')")
    # いま映っているコマ（青と ▶）は、選んだコマ（赤茶の輪）と別の色・別の印
    cue = ev("getComputedStyle(document.documentElement).getPropertyValue('--cue').trim()")
    bg = ev(f"getComputedStyle({card(1)}).backgroundColor")
    assert bg == ev("(() => { const d = document.createElement('div'); d.style.color = %s; document.body.append(d); "
                    "const c = getComputedStyle(d).color; d.remove(); return c; })()" % json.dumps(cue)), (bg, cue)
    assert bg != ev(f"getComputedStyle({card(3)}).backgroundColor")
    assert ev(f"getComputedStyle({card(1)}, '::before').content") == '"▶"'
    assert ev(f"getComputedStyle({card(3)}, '::before').content") == 'none'
    assert ev(f"{card(1)}.getAttribute('aria-current') === 'true' && !{card(3)}.hasAttribute('aria-current')")
    shot('rt_board_now.png')
    print('3. 再生・シークのあとも:', text('seatTarget'), '| 再生中:', not prop('nvideo', 'paused'), '| いまのコマ:', bg)
    # 3b. 再生中にカードを押すと、そのコマへ飛んで止まらずに流れ続ける
    click_card(2)
    assert not prop('nvideo', 'paused'), 'カードを押しても止めない'
    assert text('seatTarget') == '2 番：', text('seatTarget')
    assert ev(f"{card(2)}.classList.contains('now') && {card(2)}.classList.contains('chosen')")
    print('3b. 再生中にカード 2:', text('seatTarget'), '| 再生中:', not prop('nvideo', 'paused'))
    click_card(3)  # 段 4 は 3 番を選んだまま

    # ---------- 4. 「3 番を外したい」→ 🗑。カード 4 は「直したい」（移すはひとことで）→ ✎ ----------
    click('seatRemove')
    ev("document.getElementById('nvideo').pause(); true")
    # 止めているあいだ、いまのコマの札は ▶ でなく ❚❚
    wait("getComputedStyle(document.querySelector('.board-card.now'), '::before').content === '\"❚❚\"'", 'paused mark')
    assert ev(f"{card(3)}.classList.contains('gone')") and '🗑' in ev(f"{card(3)}.textContent")
    assert '外すのをやめる' in text('seatRemove') and prop('seatCancel', 'hidden'), text('seatRemove')
    # 4b. 「3 番を外すのをやめる」→ 🗑 が消える・修正票からも消える → もう一度外す
    click('seatRemove')
    assert not ev(f"{card(3)}.classList.contains('gone')") and '🗑' not in ev(f"{card(3)}.textContent")
    assert 'ending seat 3' not in sheet_markdown()
    assert text('seatRemove') == '外したい'
    click('seatRemove')
    assert ev(f"{card(3)}.classList.contains('gone')")
    print('4b. 外す → やめる → 外す: ok')
    click_card(4)
    note('2 の後ろへ')
    click('seatPoint')
    assert ev(f"{card(4)}.classList.contains('fix')") and '✎' in ev(f"{card(4)}.textContent")
    assert '2 の後ろへ' in ev(f"{card(4)}.title")
    # 4c. 「4 番の直したいを取り消す」→ ✎ が消え、ひとことが欄に戻る → 押し直して記録する
    assert not prop('seatCancel', 'hidden') and text('seatCancel') == '直したいを取り消す', text('seatCancel')
    assert ev("document.getElementById('seatPoint').nextElementSibling.id") == 'seatCancel', '取り消しは直したいのすぐ右'
    click('seatCancel')
    assert not ev(f"{card(4)}.classList.contains('fix')") and 'ending seat 4' not in sheet_markdown()
    assert prop('seatComment', 'value') == '2 の後ろへ' and prop('seatCancel', 'hidden')
    click('seatPoint')
    assert ev(f"{card(4)}.classList.contains('fix')")
    print('4c. 直したい → 取り消す（ひとことは欄に戻る）→ 記録し直す: ok')
    print('4. 印:', ev("[...document.querySelectorAll('.board-card')].map(c => c.textContent).join(' / ')"))
    shot('rt_board_marks.png')
    # ボタンの文字に番号を繰り返さない（番号は札に1回だけ）
    assert not any(ch.isdigit() for ch in text('seatPoint') + text('seatRemove') + text('seatCancel'))

    # ---------- 5. 固定の席・閉じの絵の席では「外したい」が押せない（直したいは押せる） ----------
    for n in (5, 6):
        click_card(n)
        assert prop('seatRemove', 'disabled') and not prop('seatPoint', 'disabled'), n
        print(f'5. 席 {n}: {text("seatTarget")}{text("seatRemove")} は押せない（{prop("seatRemove", "title")}）')

    # ---------- 5b. いまのコマが絵コンテの見える範囲の外へ出たら送る。自分で別の所を見ているあいだは引き戻さない ----------
    ev("(() => { const b = document.getElementById('board'); b.style.width = '280px'; b.style.maxHeight = '320px'; "
       "b.style.scrollBehavior = 'auto'; b.scrollTop = 0; return true; })()")
    inside = ("(() => { const b = document.getElementById('board').getBoundingClientRect(); "
              "const c = %s.getBoundingClientRect(); return c.top >= b.top - 1 && c.bottom <= b.bottom + 1; })()")
    seek(2.5)
    wait(inside % card(1), 'card 1 visible')
    assert not ev(inside % card(5)), '5 番は始めは見えない（3段に分かれていない）'
    seek(22.5)
    wait(inside % card(5), 'follow to card 5')
    print('5b. 5 番へ移ると送る: scrollTop', prop('board', 'scrollTop'))
    ev("document.getElementById('board').scrollTop = 0; true")
    time.sleep(0.3)
    seek(27.5)
    time.sleep(0.5)
    assert prop('board', 'scrollTop') == 0, '自分で上へ戻したあとは引き戻さない'
    print('5b. 上へ戻したあと 6 番へ移っても動かない: ok')
    ev("(() => { const b = document.getElementById('board'); b.removeAttribute('style'); return true; })()")

    # ---------- 6. 絵コンテを閉じたときの古い流れ: 止めて指す（再生中は押せない） ----------
    click('boardBtn')
    assert prop('seatComment', 'value') == '', '閉じると書きかけは消える'
    seek(2)
    assert text('seatTarget') == '1 番：' and not prop('seatPoint', 'disabled'), text('seatTarget')
    note('brighter')
    click('seatPoint')
    play()
    assert prop('seatPoint', 'disabled'), '閉じているときは止めて指す'
    ev("document.getElementById('nvideo').pause(); true")
    md = sheet_markdown()
    sheet = HERE / 'rt' / 'sheet.md'
    sheet.write_text(md, encoding='utf-8')
    print('6. 修正票:\n' + '\n'.join('     ' + l for l in md.strip().splitlines()))
    assert '## [Slide 4] ending seat 3 remove\nAt 0:12.9\n' in md   # 席の真ん中（席の端はフェードで割る）
    assert '## [Slide 4] ending seat 4\n' in md and 'Comment: 2 の後ろへ' in md
    assert '## [Slide 4] ending seat 1\n' in md and 'Comment: brighter' in md
    click('sheetBtn')
    assert 'ending seat 3 remove' in ev("document.getElementById('sheetList').innerText")
    click('sheetBtn')

    # ---------- 7. 書き戻し（Skill の手順どおり）: 番号を写真の名前に直してから当てる ----------
    r = run(CHECK, WORK, sheet)
    assert r.returncode == 0 and 'ending seat 3  - remove' in r.stdout and 'changed' not in r.stdout
    names = [f['src'] for f in json.loads(DEFINITION.read_text(encoding='utf-8'))['frames']]
    gone, after = names[2], names[3]                  # 3 を外す（名前で引き直す）
    assert run(LADDER, WORK, '--move', '1=5').returncode == 1, '固定の席をまたぐ移し方は止まる'
    assert run(LADDER, WORK, '--move', '3=4').returncode == 0   # 外す: 次の動かない席（5）の手前まで詰める
    assert run(LADDER, WORK, '--placeholder', '4').returncode == 0
    frames = json.loads(DEFINITION.read_text(encoding='utf-8'))['frames']
    assert frames[3]['src'] == gone and frames[3]['status'] == 'placeholder' and frames[2]['src'] == after
    assert run(LADDER, WORK, '--storyboard', '--mark', '1,4').returncode == 0
    page = (WORK / 'ending' / 'storyboard.html').read_text(encoding='utf-8')
    assert 'const MARK = [1, 4];' in page

    # ---------- 8. 作り手が選ぶ（印つきの絵コンテを開いて確かめる） ----------
    b2 = burn.Browser(burn.find_browser())
    try:
        b2.call('Page.navigate', {'url': (WORK / 'ending' / 'storyboard.html').as_uri()}, session=True)
        time.sleep(1.5)
        print('8. 絵コンテの印:', b2.evaluate("[...document.querySelectorAll('.card')].map(c => c.dataset.id + ':' + c.getAttribute('aria-pressed')).join(' ')"))
    finally:
        b2.close()
    time.sleep(1.1)  # 動画の更新日時が確実に変わるように
    assert run(LADDER, WORK, '--replace', '4=pictures/03.png').returncode == 0
    assert run(LADDER, WORK).returncode == 0
    assert run(BUILD, WORK, '--draft', '--skip-text').returncode == 0
    r = run(CHECK, WORK, sheet)
    assert 'changed' in r.stdout and r.returncode == 0

    # ---------- 9. プレイヤーで作品を読み直す ----------
    ev(f"{PICK}('reloadWork', {json.dumps(listing())})")
    wait("document.getElementById('reloadNote').textContent.length > 0", 'reloaded')
    print('9. 読み直し:', ev("document.getElementById('reloadNote').textContent"))
    ev("document.getElementById('sheetBtn').click(); true")
    time.sleep(0.3)
    listed = ev("document.getElementById('sheetList').innerText")
    print('   修正票の一覧:', listed.replace('\n', ' | '))
    shot('rt_after_reload.png')
    errs = ev("window.__errs")
    print('ページの例外:', errs)
    assert '変わった' in listed or 'changed' in listed
    assert not errs
    print('ALL OK')
finally:
    b.close()
    server.shutdown()
