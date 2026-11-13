"""見本の穴の印（docs/work-format.md §2.3 の ~N）と、穴の手引き（holes.md）の表の「場所」が食い違わない。
表の「場所」は人が読むために書いたもの。そこに出てくる枚の番号と、台本で ~N が乗っている枚が同じであることを見る。
見本の黄色い語りには、どれも穴の番号を付ける（段3の「AI に相談」は穴ごと）。"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'skills' / 'digital-kamishibai' / 'scripts'))
import build_work as bw  # noqa: E402

SAMPLES = sorted(p.parent for p in (REPO / 'examples').glob('*/*/holes.md') if (p.parent / 'script.md').is_file())
MARK = re.compile(r'^~([0-9]*) ', re.MULTILINE)


def table(holes_md: str) -> dict[int, str]:
    """穴の表: 穴の番号 → 「場所」の文字"""
    out = {}
    for line in holes_md.splitlines():
        m = re.match(r'^\|\s*([0-9]+)\D*?\|\s*([^|]+?)\s*\|', line)
        if m and int(m.group(1)) not in out:
            out[int(m.group(1))] = m.group(2)
        elif out and not line.startswith('|'):
            break                                  # 最初の表だけ
    return out


def slides_in(place: str) -> set[int]:
    """「1枚目（4・5枚目の結びにも）」「2〜5枚目」「Slides 17 and 18」「Slides 2 to 5」→ 枚の番号"""
    out: set[int] = set()
    for a, b in re.findall(r'([0-9]+)\s*(?:〜|～|to|–)\s*([0-9]+)', place):
        out.update(range(int(a), int(b) + 1))
    place = re.sub(r'([0-9]+)\s*(?:〜|～|to|–)\s*([0-9]+)', '', place)
    out.update(int(n) for n in re.findall(r'[0-9]+', place))
    return out


def marks(script: str) -> dict[str, set[int]]:
    """台本の印 → それが乗っている枚（'' は番号の無い印）"""
    r = bw.Result()
    work = bw.parse_script(script, r)
    assert not r.errors, r.errors
    out: dict[str, set[int]] = {}
    for s in work['slides']:
        for digits in MARK.findall(s['notes']):
            out.setdefault(digits, set()).add(s['number'])
    return out


def test_there_are_samples_with_holes():
    assert any(p.parts[-2:] == ('six-friends-smoothie', 'ja') for p in SAMPLES)


@pytest.mark.parametrize('folder', SAMPLES, ids=lambda p: '/'.join(p.parts[-2:]))
def test_marks_sit_where_the_guide_says(folder):
    places = table((folder / 'holes.md').read_text(encoding='utf-8'))
    found = marks((folder / 'script.md').read_text(encoding='utf-8'))
    assert found, 'no hole is marked'
    assert '' not in found, f'a hole with no number on slide(s) {sorted(found.get("", []))}'
    for digits, slides in found.items():
        n = int(digits)
        assert n in places, f'~{n} is not in the table of holes.md'
        assert slides == slides_in(places[n]), f'~{n}: script on {sorted(slides)}, holes.md says "{places[n]}"'


def test_slides_in():
    assert slides_in('1枚目（4・5枚目の結びにも）') == {1, 4, 5}
    assert slides_in('2〜5枚目') == {2, 3, 4, 5}
    assert slides_in('Slides 17 and 18') == {17, 18}
    assert slides_in('Slide 1 (and the ends of slides 4 and 5)') == {1, 4, 5}
    assert slides_in('The last paragraph of slide 14') == {14}
