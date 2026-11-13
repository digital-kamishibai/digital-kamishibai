"""script.md の答え合わせ（tests/golden/）: ビルダーが答えのとおりに読む。プレイヤーの読み手も同じ組で縛る
（tests/player/script.test.js）。答えを書き直すのは python tests/golden/golden.py"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'golden'))
import golden  # noqa: E402

CASES = golden.cases()


def test_there_are_cases():
    assert len(CASES) >= 10 and 'sample-six-friends-smoothie-ja' in CASES


@pytest.mark.parametrize('name', sorted(CASES))
def test_builder_reads_as_the_answer(name):
    want = json.loads((golden.HERE / f'{name}.json').read_text(encoding='utf-8'))
    assert golden.answer(name, CASES[name]) == want


def test_every_answer_has_a_script():
    names = {p.name[:-len('.json')] for p in golden.HERE.glob('*.json') if not p.name.endswith('.js.json')}
    assert names == set(CASES)
