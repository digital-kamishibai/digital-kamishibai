"""script.md の答え合わせ（docs/work-format.md §2.7）: ビルダー（build_work.py）と、プレイヤーの読み手（player/js/script.js）を
同じ組で縛る。答えは script/<名前>.json。作り直すのは書き方を足したとき・ビルダーを直したときだけ:

    python tests/golden/golden.py          # 答えを書き直す（差分を目で見てからコミットする）

答えの形: {work（エラーがあれば null）, texts（枚の番号 → [Text] の attrs と words）, errors, warnings（符号と場所）}。
プレイヤーの読み手だけ違う答えになる組（まだ読まない書き方）は、script/<名前>.js.json に手で書く。
見本の台本（examples/）も同じ組に入れる（SOURCES）。見本の答えには台本の文を写さない（作り手の家族の呼び名が入る。
examples/ の外に同じ文を増やさない）: 整えた答えの SHA-256（digest）と、枚数・符号だけを置く。"""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent / 'script'
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import build_work as bw  # noqa: E402

# 見本の台本（公開しているものだけ）。答えは script/sample-<名前>.json
SOURCES = {
    'sample-story': REPO / 'examples' / 'sample-story' / 'script.md',
    'sample-six-friends-smoothie-ja': REPO / 'examples' / 'six-friends-smoothie' / 'ja' / 'script.md',
    'sample-six-friends-smoothie-en': REPO / 'examples' / 'six-friends-smoothie' / 'en' / 'script.md',
}


def read(source: str) -> dict:
    """ビルダーの読む所だけ（素材のフォルダを見ない・字を描かない）"""
    r = bw.Result()
    work = bw.parse_script(source, r)
    texts = {}
    if work is not None:
        bw.resolve_media(work, None, r)
        for s in work['slides']:
            if s['_texts']:
                texts[str(s['number'])] = s['_texts']
            del s['_texts']
    return {'work': None if r.errors else work, 'texts': texts, 'errors': r.error_codes, 'warnings': r.warning_codes}


def canonical(answer: dict) -> str:
    """指紋を取る形: キーを並べ、空白を入れない（プレイヤーの側も同じ形にする）"""
    return json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(answer: dict) -> dict:
    """見本の答え: 台本の文を含まない形"""
    return {'digest': hashlib.sha256(canonical(answer).encode('utf-8')).hexdigest(),
            'slides': len(answer['work']['slides']) if answer['work'] else None,
            'errors': answer['errors'], 'warnings': answer['warnings']}


def answer(name: str, path: Path) -> dict:
    a = read(text_of(path))
    return digest(a) if name in SOURCES else a


def cases() -> dict[str, Path]:
    out = {p.stem: p for p in sorted(HERE.glob('*.md'))}
    out.update({f'{k}': v for k, v in SOURCES.items()})
    return out


def text_of(path: Path) -> str:
    return path.read_bytes().decode('utf-8')        # 改行も BOM もそのまま（読み手が直す）


if __name__ == '__main__':
    for name, path in cases().items():
        out = HERE / f'{name}.json'
        out.write_text(json.dumps(answer(name, path), ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(f'wrote {out.relative_to(REPO)}')
