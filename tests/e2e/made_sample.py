"""見本を元に書いた台本（段4a。docs/work-format.md §6「A script written from a sample」）を確かめる
（Edge が要る。素材は Release site-media から取り込む）:
    python tests/e2e/made_sample.py [作業フォルダ]
 見本の台本の黄色でない語りと題を替えた台本（Based on 無し）を貼る → サイトの見本と突き合わせて、見本の絵と音で開く・知らせが出る →
 画面の語りと題が替わる・絵は見本のまま → このブラウザに置いた（Based on・Changed 付き）→ variant=1 で開き直しても同じ →
 貼った台本の黄色い所は欄で変えられ、AI に相談は出ない → 骨組み（絵・画面の文字）を変えた台本は、違う枚を全部出して開かない →
 行頭の印が全角の台本は、直すかを聞き、直して開ける。ページに例外が無いこと。DK_E2E_BASE を置くと、その箱で確かめる。"""
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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
TITLE = 'A MADE TITLE'
KEY = 'dk-variant:six-friends-smoothie:ja'


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

# 見本の一番新しい版の台本（git の examples/ と同じことは tests/scripts/sites.test.js が見ている）から、
# 黄色でない語りの行をすべて別の文に、作品の題も替える。合図・制作メモ・印の付いた行・見出しはそのまま（台本の文はテストに写さない）
sample = (REPO / 'examples' / 'six-friends-smoothie' / 'ja' / 'script.md').read_text(encoding='utf-8').replace('\r\n', '\n')
n = 0
lines = []
for line in sample.split('\n'):
    if line.startswith('# '):
        line = '# ' + TITLE
    elif re.match(r'^[^\s#>~\-\[<*|]', line) and not line.startswith('**'):
        n += 1
        line = f'MADE LINE {n}'
    lines.append(line)
MADE = '\n'.join(lines)
assert n > 10 and '> Based on:' not in MADE


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


def paste(b, text):
    b.evaluate(f"document.getElementById('pasteScriptBtn').click(); document.getElementById('pasteText').value = {json.dumps(text)}; "
               "document.getElementById('pasteOpen').click(); true")


def opened(b):
    return wait(b, "window.__dk && __dk.site() && __dk.screen() === 'show'", 'opened')


def notes(b):
    return b.evaluate("__dk.vary().notes") or []


nar = burn.Browser(burn.find_browser())
try:
    nar.call('Emulation.setDeviceMetricsOverride', {'width': 1400, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False}, session=True)
    nar.call('Emulation.setLocaleOverride', {'locale': 'ja-JP'}, session=True)

    print('1. Based on の無い、語りを替えた台本を貼る')
    open_prep(nar)
    nar.evaluate("localStorage.clear(); true")
    paste(nar, '```markdown\n' + MADE + '\n```\n')   # チャット AI の答えを、コードブロックの記号ごと貼る
    ok('見本の絵と音で開いた', opened(nar))
    ok('コードブロックの記号は語りに残らない', not any('```' in x for x in nar.evaluate("__dk.vary().notes") or []))
    site = nar.evaluate("(() => { const s = __dk.site(); return s && { made: s.made, slug: s.slug, holes: s.holes }; })()")
    ok('段4a の道（見本と突き合わせた）', site and site['made'] and site['slug'] == 'six-friends-smoothie', json.dumps(site, ensure_ascii=False))
    note = nar.evaluate("document.getElementById('reloadNote').textContent")
    ok('知らせ: どの見本で開いたか・確かめた語りではない', '絵と音で開きました' in note and '出典で確かめたものではありません' in note and '絵の上の文字は見本のまま' in note, note[:200])
    ns = notes(nar)
    # 1枚目は黄色い所だけの枚なので、替わるのは2枚目から
    ok('画面の語りが替わった（黄色でない語りのある枚すべて）', len(ns) == 5 and all('MADE LINE' in x for x in ns[1:]), f'{len(ns)} slides')
    ok('作品の題は台本のもの', TITLE in nar.evaluate("document.getElementById('tabWork').textContent + document.getElementById('workTitle').textContent"))
    ok('絵は見本のまま（足りない素材が無い）', nar.evaluate("document.getElementById('missing').hidden"))
    kept = json.loads(nar.evaluate(f"localStorage.getItem('{KEY}') || 'null'") or 'null')
    ok('このブラウザに置いた（段4a の印・元の台本）', kept and kept.get('kind') == 'made' and kept.get('origin') == MADE)
    v = nar.evaluate("__dk.vary().variant") or ''
    ok('残す台本に Based on（足した）と Changed（語りの枚）', '(six-friends-smoothie/ja, version ' in v and '> Changed: 語り（' in v, v[:300])

    print('2. variant=1 で開き直す')
    nar.call('Page.navigate', {'url': base + '/narrator.html?test&sample=six-friends-smoothie&lang=ja&variant=1'}, session=True)
    time.sleep(0.3)
    nar.evaluate(TRAP)
    ok('開いた', opened(nar))
    ok('替えた語りのまま', any('MADE LINE' in x for x in notes(nar)) and nar.evaluate("__dk.site().made"))

    print('3. 貼った台本の黄色い所を欄で変える（AI に相談は出ない）')
    nar.evaluate("document.getElementById('varyBtn').click(); true")
    ok('欄が出る・AI に相談は出ない', nar.evaluate("document.querySelectorAll('#varyFields textarea').length > 0 && !document.querySelector('#varyFields [data-advise]')"))
    nar.evaluate("const a = document.querySelector('#varyFields textarea'); a.value = 'MY OWN WORDS'; document.getElementById('varyDone').click(); true")
    ns = notes(nar)
    ok('欄の文と、替えた語りの両方が出る', 'MY OWN WORDS' in ns[0] and 'MADE LINE' in '\n'.join(ns))
    nar.call('Page.navigate', {'url': base + '/narrator.html?test&sample=six-friends-smoothie&lang=ja&variant=1'}, session=True)
    time.sleep(0.3)
    ok('開き直しても欄の文が残る', opened(nar) and 'MY OWN WORDS' in notes(nar)[0])
    nar.evaluate("document.getElementById('varyBtn').click(); document.getElementById('varyResetAll').click(); true")
    ns = notes(nar)
    ok('全部を戻すと、貼った台本の語りに戻る（見本の語りではない）', 'MY OWN WORDS' not in ns[0] and 'MADE LINE' in '\n'.join(ns)
       and nar.evaluate(f"Object.keys(localStorage).includes('{KEY}')"))

    print('4. 骨組みを変えた台本は開かない')
    open_prep(nar)
    bad = re.sub(r'^(> \[Picture\] )(\S+)', r'\1pictures/other.jpg', MADE.split('## [Slide 2]')[0], count=1, flags=re.M) \
        + '## [Slide 2]' + MADE.split('## [Slide 2]', 1)[1]
    # 枚の終わりの "---" より後は読まれないので、見出しのすぐ後に入れる
    bad = re.sub(r'^(## \[Slide 2\][^\n]*\n)', r'\1\n> [Sound] sounds/other.mp3\n', bad, count=1, flags=re.M)
    paste(nar, bad)
    ok('理由を出して開かない', wait(nar, "!document.getElementById('loadError').hidden", 'error') and nar.evaluate("__dk.site() === null"))
    err = nar.evaluate("document.getElementById('loadError').textContent")
    ok('いちばん近い見本と比べて、違う枚を全部出す（1枚目の絵・2枚目の音）',
       'いちばん近い見本' in err and '1枚目: 絵の行' in err and '2枚目: 音楽・効果音・動画の行' in err, err[:300])
    text_slide = next((m for m in re.finditer(r'^> \[Text\][^\n]*\n> ([^\n]+)', MADE, re.M)), None)
    if text_slide:
        open_prep(nar)
        paste(nar, MADE[:text_slide.start(1)] + 'OTHER WORDS' + MADE[text_slide.end(1):])
        ok('画面の文字を変えた台本は「作り手向けの道で」', wait(nar, "!document.getElementById('loadError').hidden", 'text error')
           and '作り手向けの道' in nar.evaluate("document.getElementById('loadError').textContent"))
    open_prep(nar)
    paste(nar, '# Mine\n\n> Language: ja\n\n## [Slide 1] A\n\nhello\n')
    ok('見本と骨組みが合わない台本は、見本を元にしていないと言う',
       wait(nar, "!document.getElementById('loadError').hidden && document.getElementById('loadError').textContent.includes('見本を元にしたものではありません')", 'none'))

    print('5. 行頭の印が全角の台本')
    open_prep(nar)
    nar.evaluate("localStorage.clear(); true")
    wide = re.sub(r'^~([0-9]*) ', lambda m: '～' + m.group(1) + ' ', MADE, flags=re.M)
    paste(nar, wide)
    ok('直すかを聞く（何行か）', wait(nar, "!document.getElementById('wideBox').hidden", 'wide')
       and '行あります' in nar.evaluate("document.getElementById('wideText').textContent") and nar.evaluate("__dk.site() === null"))
    nar.evaluate("document.getElementById('wideFix').click(); true")
    ok('直して開く', opened(nar) and nar.evaluate("__dk.site().made"))
    nar.evaluate("document.getElementById('varyBtn').click(); true")
    ok('直した印が欄になる', nar.evaluate("document.querySelectorAll('#varyFields textarea').length > 0"))
    nar.evaluate("document.getElementById('varyDone').click(); true")

    print('6. この見本を元に、AI と台本を書く（段4a の後半）')
    nar.evaluate("localStorage.clear(); true")
    nar.call('Page.navigate', {'url': base + '/narrator.html?test&sample=six-friends-smoothie&lang=ja'}, session=True)
    time.sleep(0.3)
    nar.evaluate(TRAP)
    ok('見本を開いた', opened(nar) and not nar.evaluate("__dk.site().made"))
    ok('練習中の帯に「AI と台本を書く」', nar.evaluate("!document.getElementById('composeBtn').hidden && document.getElementById('composePane').hidden"))
    nar.evaluate("document.getElementById('composeBtn').click(); true")
    prompt = nar.evaluate("document.getElementById('composePrompt').value") or ''
    ok('プロンプト: 問いを先に・話を作らせない・家族の呼び方', 'まだ台本を書かないでください' in prompt and 'あなたが話を作らないでください' in prompt
       and '語る人が使ったものだけ' in prompt and '家族の名前や写真は' in prompt)
    ok('プロンプト: 絵の説明が5枚分（画風・文字の注意は入らない）', all(f'## {k}枚目\n' in prompt for k in range(1, 6))
       and '[Prompt' not in prompt and '【文字について】' not in prompt)
    ok('プロンプト: 見本の台本を丸ごと', nar.evaluate("document.getElementById('composePrompt').value.includes(__dk.site().sampleScript.replace(/\\n+$/, ''))"))
    nar.evaluate(f"document.getElementById('composeAnswer').value = {json.dumps(bad)}; document.getElementById('composeOpen').click(); true")
    ok('骨組みの違う答えは、箱の中に理由を出して開かない', wait(nar, "!document.getElementById('composeErr').hidden", 'compose error')
       and '1枚目: 絵の行' in nar.evaluate("document.getElementById('composeErr').textContent")
       and nar.evaluate("__dk.screen() === 'show' && !__dk.site().made"))
    nar.evaluate(f"document.getElementById('composeAnswer').value = {json.dumps('```markdown\n' + MADE + '\n```\n')}; document.getElementById('composeOpen').click(); true")
    ok('AI が書いた台本で、見本の絵と音で開く', wait(nar, "__dk.site() && __dk.site().made && __dk.screen() === 'show'", 'compose open')
       and any('MADE LINE' in x for x in notes(nar)))
    ok('開いたら箱は閉じる・答えの欄は空', nar.evaluate("document.getElementById('composePane').hidden && document.getElementById('composeAnswer').value === ''"))

    ok('ページに例外が無い', not nar.evaluate("window.__errs"), json.dumps(nar.evaluate("window.__errs"), ensure_ascii=False))
finally:
    nar.close()
    server.shutdown()

print('\n' + ('すべて OK' if not failures else f'NG {len(failures)} 件: ' + ', '.join(failures)))
sys.exit(1 if failures else 0)
