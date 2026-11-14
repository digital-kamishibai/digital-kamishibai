"""サイトの見本の語りを変えてみる（段2。docs/work-format.md §6 の最後）を確かめる（Edge が要る。素材は Release site-media から取り込む）:
    python tests/e2e/vary_sample.py [作業フォルダ]
 見本を ?sample= で開く → 1枚目で「語りを変えてみる」→ 欄を書き換えて閉じる → 画面の語りが替わり、黄色のまま・印は出ない →
 知らせが出る → ファイルに保存（保存の窓は差し替え）した中身が Based on・Changed 付きの script.md → 開き直しても残っている →
 2枚目には欄が無い（黄色い所の無い枚）→ 玄関のカードに「変えた版で開く」→ variant=1 が無ければ見本のまま →
 このブラウザから消しても、保存した台本を貼る・ファイルで開くと変えた版で開く → 合図を変えた台本は開かない →
 見本から作っていない台本は、案内の中の「作品フォルダを選ぶ」で作品を開ける（iPad では zip の案内）→
 全部を見本に戻すと元の語り → zip を開く（作品の zip は作品として・台本だけの zip は変えた版として）→
 AI に相談（段3）: 穴1のプロンプト（かかる枚・問いを先に）→ 答えを貼ると、開いていない枚の語りまで替わる。ページに例外が無いこと。
 DK_E2E_BASE を置くと、その箱で確かめる。"""
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
import zipfile
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

failures = []
MINE = 'A WORD OF MY OWN'


def ok(name, cond, detail=''):
    print(f'  {"OK " if cond else "NG "} {name}' + (f'  ({detail})' if detail else ''))
    if not cond:
        failures.append(name)


r = subprocess.run(['node', str(REPO / 'scripts' / 'fetch-samples.mjs')], capture_output=True, text=True, encoding='utf-8', errors='replace')
assert r.returncode == 0, r.stdout + r.stderr
shutil.rmtree(ROOT, ignore_errors=True)
shutil.copytree(REPO / 'player', ROOT / 'player')


class Site(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript'}

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Site, directory=str(ROOT / 'player')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = os.environ.get('DK_E2E_BASE', '').rstrip('/') or f'http://localhost:{server.server_address[1]}'
print(f'base: {base}')
TRAP = ("window.__errs = []; addEventListener('error', (e) => __errs.push(e.message)); "
        "addEventListener('unhandledrejection', (e) => __errs.push(String(e.reason))); true")
# 保存の窓の代わり: 書いた中身を覚える
SAVE = ("window.__saved = null; window.showSaveFilePicker = async (o) => ({ createWritable: async () => ({ "
        "write: async (b) => { window.__saved = { name: o.suggestedName, text: await b.text() }; }, close: async () => {} }) }); true")


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


def open_sample(b, extra=''):
    b.call('Page.navigate', {'url': base + '/narrator.html?test&sample=six-friends-smoothie&lang=ja' + extra}, session=True)
    time.sleep(0.3)
    b.evaluate(TRAP)
    return wait(b, "window.__dk && __dk.site() && __dk.screen() === 'show'", 'sample opened')


def has_mine(b):
    return b.evaluate(f"[...document.querySelectorAll('#notes .hole')].some((d) => d.textContent === '{MINE}')")


def open_prep(b):
    b.call('Page.navigate', {'url': base + '/narrator.html?test'}, session=True)
    # 前のページ（見本が開いたまま）に向かって操作しないよう、新しいページの準備の画面まで待つ
    wait(b, "location.search === '?test' && window.__dk && __dk.site() === null && __dk.screen() === 'prep'", 'prep')
    b.evaluate(TRAP)


nar = burn.Browser(burn.find_browser())
try:
    nar.call('Emulation.setDeviceMetricsOverride', {'width': 1400, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    nar.call('Emulation.setLocaleOverride', {'locale': 'ja-JP'}, session=True)
    print('1. 見本を開き、1枚目の語りを変える')
    ok('見本を開いた', open_sample(nar))
    nar.evaluate("localStorage.clear(); true")
    ok('開き直した（置いた版の無い状態）', open_sample(nar))
    ok('1枚目に「語りを変えてみる」', nar.evaluate("!document.getElementById('varyBtn').hidden"))
    nar.evaluate("document.getElementById('varyBtn').click(); true")
    fields = nar.evaluate("[...document.querySelectorAll('#varyFields textarea')].map((a) => a.value)")
    ok('黄色い所が欄になり、印は欄に出ない', len(fields) >= 3 and not any(f.startswith('~') for f in fields), f'{len(fields)} fields')
    nar.evaluate(f"const a = document.querySelector('#varyFields textarea'); a.value = '{MINE}\\nsecond line'; "
                 "document.getElementById('varyDone').click(); true")
    look = nar.evaluate("({holes: [...document.querySelectorAll('#notes .hole')].map((d) => d.textContent), marks: [...document.querySelectorAll('#notes div')].filter((d) => /^~/.test(d.textContent)).length, pane: document.getElementById('varyPane').hidden, note: document.getElementById('varyNote').hidden})")
    ok('画面の語りが替わり、黄色のまま', look['holes'][:2] == [MINE, 'second line'], json.dumps(look['holes'][:3], ensure_ascii=False))
    ok('印は画面に出ない・欄は閉じた', look['marks'] == 0 and look['pane'])
    ok('置き場の知らせが出る', not look['note'])
    v = nar.evaluate("__dk.vary()")
    ok('変えた版の見出しに Based on・Changed', v['variant'] and '> Based on: ' in v['variant'] and '(six-friends-smoothie/ja, version ' in v['variant']
       and '> Changed: 穴1（1枚目）' in v['variant'], (v['variant'] or '')[:400])

    print('2. ファイルに保存（保存の窓は差し替え）')
    nar.evaluate(SAVE)
    nar.evaluate("document.getElementById('varySave').click(); true")
    ok('script.md として保存した', wait(nar, "!!window.__saved", 'saved'))
    saved = nar.evaluate("window.__saved")
    ok('名前と中身', saved['name'] == 'six-friends-smoothie-ja-script.md' and f'~1 {MINE}' in saved['text'] and saved['text'] == v['variant'],
       saved['name'])

    ok('URL に variant=1 が付いた（読み込み直しても変えた版）', nar.evaluate("new URLSearchParams(location.search).get('variant') === '1'"))

    print('3. 開き直しても残っている・黄色い所の無い枚には欄が無い')
    ok('variant=1 で開き直した', open_sample(nar, '&variant=1'))
    ok('変えた語りのまま', has_mine(nar))
    nar.evaluate("document.getElementById('nextBtn').click(); true")
    time.sleep(0.3)
    ok('2枚目（黄色い所が無い）には「語りを変えてみる」が出ない', nar.evaluate("document.getElementById('varyBtn').hidden"))

    print('4. 玄関・見本のまま・ファイルや貼った台本から開き直す')
    nar.call('Page.navigate', {'url': base + '/index.html'}, session=True)
    ok('玄関のカードに「変えた版で開く」', wait(nar, "[...document.querySelectorAll('#samples a')].some((a) => a.textContent === '変えた版で開く' && a.getAttribute('href').endsWith('&variant=1'))", 'variant link'))
    # 玄関を開いたあとで変えた版が置かれても（前から開いていたタブ・戻るで出た前の画面）、作り直して出す（実機で見つからなかった）
    keep = nar.evaluate("localStorage.getItem('dk-variant:six-friends-smoothie:ja')")
    nar.evaluate("localStorage.removeItem('dk-variant:six-friends-smoothie:ja'); document.dispatchEvent(new Event('visibilitychange')); true")
    ok('置き場が無ければ「変えた版で開く」は出ない', wait(nar, "![...document.querySelectorAll('#samples a')].some((a) => a.textContent === '変えた版で開く')", 'gone'))
    nar.evaluate(f"localStorage.setItem('dk-variant:six-friends-smoothie:ja', {json.dumps(keep)}); document.dispatchEvent(new Event('visibilitychange')); true")
    ok('タブが前に出たら、作り直して出す', wait(nar, "[...document.querySelectorAll('#samples a')].some((a) => a.textContent === '変えた版で開く')", 'visible'))
    nar.evaluate("localStorage.removeItem('dk-variant:six-friends-smoothie:ja'); dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })); true")
    nar.evaluate(f"localStorage.setItem('dk-variant:six-friends-smoothie:ja', {json.dumps(keep)}); dispatchEvent(new PageTransitionEvent('pageshow', {{ persisted: true }})); true")
    ok('戻るで前の画面が出ても、作り直して出す', wait(nar, "[...document.querySelectorAll('#samples a')].some((a) => a.textContent === '変えた版で開く')", 'pageshow'))
    ok('variant=1 が無ければ見本のまま', open_sample(nar) and not has_mine(nar))
    nar.evaluate("document.getElementById('varyBtn').click(); document.getElementById('varyDone').click(); true")
    ok('見本のまま欄を開いて何も変えずに閉じても、置いた変えた版は消えない',
       nar.evaluate("Object.keys(localStorage).includes('dk-variant:six-friends-smoothie:ja')"))
    nar.evaluate("localStorage.clear(); true")
    open_prep(nar)
    nar.evaluate(f"document.getElementById('pasteScriptBtn').click(); document.getElementById('pasteText').value = {json.dumps(saved['text'])}; "
                 "document.getElementById('pasteOpen').click(); true")
    ok('貼った台本で、変えた版が開く', wait(nar, "window.__dk && __dk.site() && __dk.screen() === 'show'", 'pasted') and has_mine(nar))
    ok('貼った台本もこのブラウザに置いた', nar.evaluate("Object.keys(localStorage).some((k) => k === 'dk-variant:six-friends-smoothie:ja')"))
    nar.evaluate("localStorage.clear(); true")
    open_prep(nar)
    nar.evaluate(f"const dt = new DataTransfer(); dt.items.add(new File([{json.dumps(saved['text'])}], 'six-friends-smoothie-ja-script.md', {{ type: 'text/markdown' }})); "
                 "const i = document.getElementById('openScript'); i.files = dt.files; i.dispatchEvent(new Event('change')); true")
    ok('ファイルの台本で、変えた版が開く', wait(nar, "window.__dk && __dk.site() && __dk.screen() === 'show'", 'file') and has_mine(nar))
    open_prep(nar)
    # 黄色い所のほかを変えた台本は段4a の道（tests/e2e/made_sample.py）。骨組み（合図）まで変えたものは開かない
    # 枚の終わりの "---" より後は読まれないので、見出しのすぐ後に入れる
    other = saved['text']
    at = other.index('\n', other.index('## [Slide 2]'))
    other = other[:at + 1] + '\n> [Sound] sounds/other.mp3\n' + other[at + 1:]
    nar.evaluate(f"document.getElementById('pasteScriptBtn').click(); document.getElementById('pasteText').value = {json.dumps(other)}; "
                 "document.getElementById('pasteOpen').click(); true")
    ok('合図を変えた台本は、理由を出して開かない', wait(nar, "!document.getElementById('loadError').hidden && document.getElementById('loadError').textContent.includes('見本の絵と音では開けません')", 'other')
       and nar.evaluate("__dk.site() === null"))
    open_prep(nar)
    nar.evaluate("document.getElementById('pasteScriptBtn').click(); document.getElementById('pasteText').value = "
                 + json.dumps('# Mine\n\n## [Slide 1] A\n\nhello\n') + "; document.getElementById('pasteOpen').click(); true")
    ok('見本から作っていない台本は、理由を出す', wait(nar, "!document.getElementById('loadError').hidden && document.getElementById('loadError').textContent.includes('Based on')", 'not variant'))
    # 自分の作品の台本を選んで止まり、案内を読んでも「作品フォルダを選ぶ」へたどり着けなかった（実機で）: 案内の中に同じボタンを置く
    ok('案内の中に「作品フォルダを選ぶ」ボタン（上のボタンと同じと名指し）',
       nar.evaluate("(() => { const l = document.getElementById('pickWorkHereLabel'), box = document.getElementById('loadError'); "
                    "return !l.hidden && box.contains(l) && l.textContent.includes('作品フォルダを選ぶ') "
                    "&& box.textContent.includes('上の「作品フォルダを選ぶ」と同じ'); })()"))
    if base.startswith('http://localhost'):
        # フォルダを選ぶ窓は押せないので、選んだあとの input の change を差し替えて渡す（作品は見本の版のフォルダ）
        src = ROOT / 'player' / 'samples' / 'six-friends-smoothie' / 'ja'
        src = sorted(src.iterdir(), key=lambda p: int(p.name))[-1]
        files = [{'url': '/' + f.relative_to(ROOT / 'player').as_posix(), 'rel': 'my-work/' + f.relative_to(src).as_posix()}
                 for f in sorted(src.rglob('*')) if f.is_file() and f.name not in ('script.md', 'version.json')]
        nar.evaluate(f"""(async (files) => {{
          const list = [];
          for (const f of files) {{
            const file = new File([await (await fetch(f.url)).blob()], f.rel.split('/').pop());
            Object.defineProperty(file, 'webkitRelativePath', {{ value: f.rel }});
            list.push(file);
          }}
          const input = document.getElementById('pickWorkHere');
          Object.defineProperty(input, 'files', {{ value: list, configurable: true }});
          input.dispatchEvent(new Event('change'));
        }})({json.dumps(files)}); true""")
        ok('案内の中のボタンで選んだ作品フォルダが開く（理由の箱は消える）',
           wait(nar, "document.getElementById('workTitle').textContent.length > 0 && __dk.screen() !== 'prep'", 'pick here', 1200)
           and nar.evaluate("document.getElementById('loadError').hidden && __dk.site() === null"),
           nar.evaluate("document.getElementById('loadError').textContent"))
    open_prep(nar)
    # フォルダを選べない端末（iPad）: ボタンは出さず、作品フォルダを zip にして開くよう言う
    nar.evaluate("Object.defineProperty(navigator, 'userAgent', { get: () => 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15' }); "
                 "window.showDirectoryPicker = undefined; document.getElementById('pasteScriptBtn').click(); document.getElementById('pasteText').value = "
                 + json.dumps('# Mine\n\n## [Slide 1] A\n\nhello\n') + "; document.getElementById('pasteOpen').click(); true")
    ok('iPad では、ボタンの代わりに zip で開く案内', wait(nar, "!document.getElementById('loadError').hidden && document.getElementById('loadError').textContent.includes('丸ごと zip にして')", 'ipad')
       and nar.evaluate("!document.getElementById('loadError').contains(document.getElementById('pickWorkHereLabel'))"))

    print('5. 全部を見本に戻す')
    ok('variant=1 で開き直した', open_sample(nar, '&variant=1') and has_mine(nar))
    nar.evaluate("document.getElementById('prev').click(); true")
    time.sleep(0.3)
    nar.evaluate("document.getElementById('varyBtn').click(); document.getElementById('varyResetAll').click(); true")
    ok('元の語り・知らせは消える', nar.evaluate(f"![...document.querySelectorAll('#notes .hole')].some((d) => d.textContent === '{MINE}') "
                                     "&& document.getElementById('varyNote').hidden && __dk.vary().variant === null"))
    ok('このブラウザからも消えた', nar.evaluate("!Object.keys(localStorage).some((k) => k.startsWith('dk-variant:'))"))

    print('6. zip を開く（docs/work-format.md §1 Zip）')
    # 作品の zip: 見本の版のフォルダ（work.json と素材）を、ほかの道具が作るように縮めて詰める（work.json は deflate、素材は無圧縮）
    src = ROOT / 'player' / 'samples' / 'six-friends-smoothie' / 'ja'
    src = sorted(src.iterdir(), key=lambda p: int(p.name))[-1]
    work_zip = ROOT / 'player' / 'work.zip'
    with zipfile.ZipFile(work_zip, 'w') as z:
        for f in sorted(src.rglob('*')):
            if f.is_file() and f.name not in ('script.md', 'version.json'):
                z.write(f, 'my-work/' + f.relative_to(src).as_posix(),
                        compress_type=zipfile.ZIP_DEFLATED if f.suffix == '.json' else zipfile.ZIP_STORED)
    script_zip = ROOT / 'player' / 'script.zip'
    with zipfile.ZipFile(script_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('script.md', saved['text'])

    def open_file(url, name):
        nar.evaluate(f"fetch('{url}').then((r) => r.blob()).then((b) => {{ const dt = new DataTransfer(); "
                     f"dt.items.add(new File([b], '{name}', {{ type: 'application/zip' }})); const i = document.getElementById('openScript'); "
                     "i.files = dt.files; i.dispatchEvent(new Event('change')); }); true")

    if base.startswith('http://localhost'):
        open_prep(nar)
        open_file('/work.zip', 'my-work.zip')
        ok('作品の zip が作品として開く（足りない素材が無い・サイトの見本ではない）',
           wait(nar, "document.getElementById('workTitle').textContent.length > 0 && __dk.screen() !== 'prep'", 'work zip', 1200)
           and nar.evaluate("document.getElementById('missing').hidden && __dk.site() === null"),
           nar.evaluate("document.getElementById('missing').textContent + document.getElementById('loadError').textContent"))
        open_prep(nar)
        open_file('/script.zip', 'my-script.zip')
        ok('台本だけの zip は変えた版として開く', wait(nar, "window.__dk && __dk.site() && __dk.screen() === 'show'", 'script zip') and has_mine(nar))
    else:
        print('  （箱では zip を置けないので、6 は手元だけ）')

    print('7. AI に相談（段3）')
    nar.evaluate("localStorage.clear(); true")
    ok('見本を開いた', open_sample(nar))
    nar.evaluate("document.getElementById('varyBtn').click(); true")
    ok('穴1の欄に「AI に相談」', nar.evaluate("!!document.querySelector('#varyFields [data-advise=\"1\"]')"))
    nar.evaluate("document.querySelector('#varyFields [data-advise=\"1\"]').click(); true")
    prompt = nar.evaluate("__dk.advise().prompt")
    ok('プロンプト: 穴1がかかる枚（1・4・5枚目）だけ・印は入らない',
       all(f'## [Slide {n}]' in prompt for n in (1, 4, 5)) and '## [Slide 2]' not in prompt and '~1' not in prompt)
    ok('プロンプト: 語る人自身の話なので、話を作らせず問いを先に', '話を作らないで' in prompt and '自分の話を見つける問い' in prompt)
    ok('プロンプト: 家族の名前や写真は要らないと書く', '家族の名前や写真は' in prompt)
    # プロンプトの形どおりの答え: 枚ごとに、替える所の数だけ段落
    import re
    answer = ['```']
    for m in re.finditer(r'^## \[Slide ([0-9]+)\][^\n]*\n([\s\S]*?)(?=^## \[Slide|\Z)', prompt, re.M):
        k = m.group(2).count('### 替える所')
        answer.append(f'[Slide {m.group(1)}]')
        answer.append('\n\n'.join(f'AI LINE {m.group(1)}-{j}' for j in range(k)))
        answer.append('')
    answer.append('```')
    nar.evaluate(f"document.getElementById('adviseAnswer').value = {json.dumps(chr(10).join(answer))}; document.getElementById('adviseApply').click(); true")
    ok('欄に入れた（1・4・5枚目）', '1・4・5枚目' in nar.evaluate("document.getElementById('adviseNote').textContent"),
       nar.evaluate("document.getElementById('adviseNote').textContent"))
    ok('開いている枚の欄に入った', nar.evaluate("document.querySelector('#varyFields textarea').value === 'AI LINE 1-0'"))
    nar.evaluate("document.getElementById('varyDone').click(); true")
    notes = nar.evaluate("__dk.vary().notes")
    ok('閉じると、開いていない4・5枚目の語りまで替わる', 'AI LINE 4-0' in notes[3] and 'AI LINE 5-0' in notes[4] and 'AI LINE 1-0' in notes[0])
    nar.evaluate("document.getElementById('varyBtn').click(); document.querySelector('#varyFields [data-advise=\"1\"]').click(); "
                 "document.getElementById('adviseAnswer').value = '[Slide 1]\\nonly one paragraph'; document.getElementById('adviseApply').click(); true")
    ok('数が合わない答えは、理由を出して入れない', '5つですが' in nar.evaluate("document.getElementById('adviseNote').textContent"),
       nar.evaluate("document.getElementById('adviseNote').textContent"))
    nar.evaluate("document.getElementById('varyResetAll').click(); true")
    ok('ページに例外が無い（AI に相談）', not nar.evaluate("window.__errs"), json.dumps(nar.evaluate("window.__errs"), ensure_ascii=False))
    ok('ページに例外が無い', not nar.evaluate("window.__errs"), json.dumps(nar.evaluate("window.__errs"), ensure_ascii=False))
finally:
    nar.close()
    server.shutdown()

print('\n' + ('すべて OK' if not failures else f'NG {len(failures)} 件: ' + ', '.join(failures)))
sys.exit(1 if failures else 0)
