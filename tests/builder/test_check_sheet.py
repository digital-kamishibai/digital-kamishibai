"""Tests for skills/digital-kamishibai/scripts/check_sheet.py against docs/work-format.md §6."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / 'examples' / 'sample-story'
SCRIPTS = ROOT / 'skills' / 'digital-kamishibai' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location('check_sheet', SCRIPTS / 'check_sheet.py')
cs = importlib.util.module_from_spec(_spec)
sys.modules['check_sheet'] = cs
_spec.loader.exec_module(cs)


def format_example():
    text = (ROOT / 'docs' / 'work-format.md').read_text(encoding='utf-8')
    start = text.index('```````markdown\n') + len('```````markdown\n')
    return text[start:text.index('\n```````', start)]


def test_reads_the_example_of_the_format():
    title, items, errors = cs.read_sheet(format_example())
    assert errors == [] and title == "The Lighthouse Keeper's Lamp"
    notes, overlay, layout, colours = items
    assert notes == {'slide': 1, 'kind': 'notes', 'at': (2, 2), 'before': ['Who do you think lit it?'],
                     'after': ['Who lit it, do you think?'], 'comment': 'sounds more like me'}
    assert overlay['kind'] == 'overlay' and overlay['before'] == [['The storm']]
    assert overlay['after'] == [['The storm'], ['that night']]
    assert cs.box_of('a\n\n\n\nb') == [['a'], [''], ['b']]          # an empty paragraph: an empty line between two blank lines
    assert layout['before'] == {'top': 0.18, 'size': 30} and layout['after'] == {'top': 0.30, 'size': 32}
    assert colours['before'] == {'color': '#3A3A3A', 'fill': 'none'} and colours['after'] == {'color': '#FFFFFF', 'fill': '#2B4A74'}


def test_fences_longer_than_three_and_empty_after():
    sheet = ('# Correction sheet: T (2026-10-25 21:04)\n\n## [Slide 1] notes 1-2\n### Before\n````\nuse ``` here\n\nsecond\n````\n'
             '### After\n```\n\n```\n\n## [Slide 2] comment\nComment: add a box with the year\n')
    title, items, errors = cs.read_sheet(sheet)
    assert errors == []
    assert items[0]['at'] == (1, 2) and items[0]['before'] == ['use ``` here', 'second'] and items[0]['after'] == []
    assert items[1] == {'slide': 2, 'kind': 'comment', 'at': None, 'comment': 'add a box with the year'}


def test_broken_sheets_are_reported():
    _, _, errors = cs.read_sheet('# Notes\n\n## [Slide 1] note 1\n')
    assert any('first line' in e for e in errors) and any('not a correction heading' in e for e in errors)
    _, _, errors = cs.read_sheet('# Correction sheet: T (2026-10-25 21:04)\n\n## [Slide 1] layout 1\n### Before\n```\ntop 1cm\n```\n'
                                 '### After\n```\ntop 0.30in\n```\n')
    assert any('not a layout line' in e for e in errors)
    for bad in ('color white', 'fill #FFF', 'color none'):
        _, _, errors = cs.read_sheet('# Correction sheet: T (2026-10-25 21:04)\n\n## [Slide 1] layout 1\n### Before\n```\n'
                                     f'{bad}\n```\n### After\n```\nfill none\n```\n')
        assert any('not a layout line' in e for e in errors), bad


# ---------- the round trip on the shared example ----------

SHEET = '''# Correction sheet: The Lighthouse Keeper's Lamp (2026-10-25 21:04)

## [Slide 1] notes 2
### Before
```
Who do you think lit it, every night, for forty years?
```
### After
```
Who lit it, do you think, every night, for forty years?
```
Comment: sounds more like me

## [Slide 2] overlay 1
### Before
```
The keeper's island

winter
```
### After
```
The keeper's island

late winter
```

## [Slide 2] layout 1
### Before
```
top 0.30in
size 44pt
```
### After
```
top 0.50in
size 40pt
```

## [Slide 3] notes 1
### Before
```
In the morning, the keeper found a small boat on the beach,
and a child asleep inside it.
```
### After
```
```

## [Slide 3] comment
Comment: a picture of the boat would help
'''


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / 'sample'
    shutil.copytree(SAMPLE, folder)
    return folder


def states(folder):
    judged, errors = cs.check(folder, SHEET)
    assert errors == []
    return [state for _, state in judged]


def test_before_writing_back_everything_is_pending(work):
    assert states(work) == ['pending', 'pending', 'pending', 'pending', 'comment']
    (work / 'sheet.md').write_text(SHEET, encoding='utf-8')
    assert cs.main([str(work), str(work / 'sheet.md')]) == 1


def test_after_writing_back_by_the_rules_everything_is_done(work, capsys):
    script = work / 'script.md'
    s = script.read_text(encoding='utf-8')
    s = s.replace('Who do you think lit it, every night, for forty years?',
                  'Who lit it, do you think, every night, for forty years?')
    s = s.replace('> [Text] place top size 44pt bold color #FFFFFF\n> The keeper\'s island\n>\n> winter',
                  '> [Text] left 0.50in top 0.50in width 12.33in height 1.20in size 40pt bold color #FFFFFF\n'
                  '> The keeper\'s island\n>\n> late winter')
    s = s.replace('In the morning, the keeper found a small boat on the beach,\nand a child asleep inside it.\n\n', '')
    script.write_text(s, encoding='utf-8')
    assert states(work) == ['done', 'done', 'done', 'done', 'comment']
    (work / 'sheet.md').write_text(SHEET, encoding='utf-8')
    assert cs.main([str(work), str(work / 'sheet.md')]) == 0
    out = capsys.readouterr().out
    assert 'comment   [Slide 3] comment  - a picture of the boat would help' in out and '0 pending' in out


def test_changed_again_is_reworded(work):
    script = work / 'script.md'
    s = script.read_text(encoding='utf-8').replace('Who do you think lit it, every night, for forty years?',
                                                   'Who lit the lamp, every night?')
    s = s.replace('> [Text] place top size 44pt', '> [Text] left 0.50in top 0.60in width 12.33in height 1.20in size 40pt')
    script.write_text(s, encoding='utf-8')
    assert states(work)[:3] == ['reworded', 'pending', 'reworded']


COLOUR_SHEET = '''# Correction sheet: The Lighthouse Keeper's Lamp (2026-10-30 10:00)

## [Slide 2] layout 1
### Before
```
color #FFFFFF
fill none
```
### After
```
color #2A2A3A
fill #FAF7F0
```
'''

BAND_OFF_SHEET = '''# Correction sheet: The Lighthouse Keeper's Lamp (2026-10-30 10:00)

## [Slide 2] layout 1
### Before
```
fill #FAF7F0
```
### After
```
fill none
```
'''

TEXT_LINE = '> [Text] place top size 44pt bold color #FFFFFF\n'


def test_colours_are_written_back_by_replacing_and_adding_words(work):
    """§2.6: color replaces the word's value; fill is added; fill none removes the fill word"""
    def state(sheet):
        judged, errors = cs.check(work, sheet)
        assert errors == []
        return [s for _, s in judged]
    script = work / 'script.md'
    s = script.read_text(encoding='utf-8')
    assert TEXT_LINE in s
    assert state(COLOUR_SHEET) == ['pending']
    script.write_text(s.replace(TEXT_LINE, '> [Text] place top size 44pt bold color #2a2a3a\n'), encoding='utf-8')
    assert state(COLOUR_SHEET) == ['reworded']                     # only the colour of the words: the band is not there yet
    script.write_text(s.replace(TEXT_LINE, '> [Text] place top size 44pt bold color #2A2A3A fill #FAF7F0\n'), encoding='utf-8')
    assert state(COLOUR_SHEET) == ['done']
    # taking the band away again: "fill none" is a box with no fill
    assert state(BAND_OFF_SHEET) == ['pending']
    script.write_text(s.replace(TEXT_LINE, '> [Text] place top size 44pt bold color #2A2A3A\n'), encoding='utf-8')
    assert state(BAND_OFF_SHEET) == ['done']


def test_the_colour_of_a_box_counts_only_paragraphs_with_words():
    box = {'x': 0, 'y': 0, 'width': 914400, 'height': 914400, 'fill': '#faf7f0',
           'paragraphs': [{'size': 30, 'color': '#7a4518'}, {'size': 30, 'color': '#000000'}, {'size': 30, 'color': '#7A4518'}]}
    assert cs.sheet_values(box, [['a'], [''], ['b']])['color'] == '#7A4518'
    assert cs.sheet_values(box, [['a'], [''], ['b']])['fill'] == '#FAF7F0'
    assert 'color' not in cs.sheet_values(box, [['a'], ['b'], ['c']])           # no single colour
    assert cs.sheet_values({**box, 'fill': None}, None)['fill'] == 'none'
    item = {'slide': 1, 'kind': 'layout', 'at': 1, 'before': {'color': '#7A4518'}, 'after': {'color': '#FFFFFF'}}
    slide = {'overlays': [[['a'], ['b'], ['c']]], 'overlay_layout': [box]}
    assert cs.judge(item, slide) == 'reworded'                                  # §6: a box with no single colour


def test_a_sheet_for_another_work_is_an_error(work):
    _, errors = cs.check(work, SHEET.replace("The Lighthouse Keeper's Lamp", 'Another story', 1))
    assert any('is for "Another story"' in e for e in errors)


def test_a_slide_that_no_longer_exists_is_reworded():
    item = {'slide': 9, 'kind': 'notes', 'at': (1, 1), 'before': ['a'], 'after': ['b']}
    assert cs.judge(item, None) == 'reworded'


def media_example():
    text = (ROOT / 'docs' / 'work-format.md').read_text(encoding='utf-8')
    start = text.index('\n````markdown\n') + len('\n````markdown\n')
    return text[start:text.index('\n````\n', start)]


def test_reads_the_picture_and_video_example_of_the_format():
    title, items, errors = cs.read_sheet('# Correction sheet: T (2026-10-26 10:00)\n\n' + media_example())
    assert errors == []
    picture, chosen, video, seat = items
    assert picture == {'slide': 3, 'kind': 'picture', 'at': None,
                       'comment': 'the lamp should be dark — the storm has put it out'}
    assert chosen == {'slide': 4, 'kind': 'picture', 'at': None, 'media': {'use': 'pictures/_candidates/04-2.png'}}
    assert video['kind'] == 'video' and video['at'] == 2
    assert video['media'] == {'from': '0:12.5 (source 1:34.5)', 'to': '1:10.0 (source 4:58.0)'}
    assert seat['kind'] == 'ending seat' and seat['at'] == 2
    assert seat['media'] == {'at': '0:08.3', 'label': 'pictures/03.png'} and seat['comment'].startswith('too dark')


def test_a_picture_correction_needs_a_comment():
    _, _, errors = cs.read_sheet('# Correction sheet: T (2026-10-26 10:00)\n\n## [Slide 1] picture\n')
    assert errors == ['[Slide 1] picture: a picture correction needs "Comment:" (what to change) or "Use" (the chosen candidate)']


def test_picture_and_video_corrections_are_listed_not_judged(work, capsys):
    sheet = ('# Correction sheet: The Lighthouse Keeper\'s Lamp (2026-10-26 10:00)\n\n'
             '## [Slide 3] picture\nComment: the lamp should be dark\n\n'
             '## [Slide 3] video 1\nFrom 0:03.0\nComment: start later\n\n'
             '## [Slide 4] ending seat 1\nAt 0:03.0\nLabel pictures/02.png\n')
    judged, errors = cs.check(work, sheet)
    # a new cut is in the video file, not in script.md: the sheet cannot see it (the player does, by the file)
    assert errors == [] and [state for _, state in judged] == ['look', 'look', 'look']
    (work / 'sheet.md').write_text(sheet, encoding='utf-8')
    assert cs.main([str(work), str(work / 'sheet.md')]) == 0          # nothing pending: the maker chooses the new ones
    assert 'look      [Slide 4] ending seat 1' in capsys.readouterr().out


def test_an_ending_seat_with_another_picture_is_changed(work):
    # the example's ending_video.json: seat 1 holds pictures/02.png. After --replace 1=pictures/03.png it does not
    sheet = ('# Correction sheet: The Lighthouse Keeper\'s Lamp (2026-10-26 10:00)\n\n'
             '## [Slide 4] ending seat 1\nAt 0:03.0\nLabel pictures/02.png\n\n'
             '## [Slide 3] ending seat 1\nAt 0:03.0\nLabel pictures/02.png\n')
    definition = work / 'ending_video.json'
    data = json.loads(definition.read_text(encoding='utf-8'))
    data['frames'][0]['src'] = 'pictures/03.png'
    definition.write_text(json.dumps(data), encoding='utf-8')
    judged, errors = cs.check(work, sheet)
    assert errors == [] and [state for _, state in judged] == ['changed', 'changed']   # slide 3 has no ending video


def test_a_chosen_candidate_is_pending_until_it_is_used(work, capsys):
    # the maker chose a candidate in the player (Use). gen_images.py --use moves it into the slide's place
    sheet = ('# Correction sheet: The Lighthouse Keeper\'s Lamp (2026-10-29 20:00)\n\n'
             '## [Slide 3] picture\nUse pictures/_candidates/03-2.png\n')
    title, items, errors = cs.read_sheet(sheet)
    assert errors == [] and items[0]['media'] == {'use': 'pictures/_candidates/03-2.png'}
    candidate = work / 'pictures' / '_candidates' / '03-2.png'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b'png')
    (work / 'sheet.md').write_text(sheet, encoding='utf-8')
    assert cs.main([str(work), str(work / 'sheet.md')]) == 1
    assert 'PENDING   [Slide 3] picture  - use pictures/_candidates/03-2.png' in capsys.readouterr().out
    candidate.unlink()
    judged, errors = cs.check(work, sheet)
    assert errors == [] and [state for _, state in judged] == ['done']
