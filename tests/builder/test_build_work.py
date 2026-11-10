"""Tests for skills/digital-kamishibai/scripts/build_work.py against docs/work-format.md."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / 'examples' / 'sample-story'
_spec = importlib.util.spec_from_file_location(
    'build_work', ROOT / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py')
bw = importlib.util.module_from_spec(_spec)
sys.modules['build_work'] = bw
_spec.loader.exec_module(bw)


def script(*slides, header='# T\n\n> Language: en\n'):
    return header + '\n' + '\n---\n\n'.join(slides)


def ok(source, media=None, **kw):
    r = bw.build(source, media, **kw)
    assert r.errors == [], r.errors
    return r


def errors(source, media=None, **kw):
    r = bw.build(source, media, **kw)
    assert r.work is None
    return ' | '.join(r.errors)


# ---------- the shared example ----------

def test_sample_story_without_words_builds_to_its_work_json_exactly():
    # examples/sample-story/work.json is the build with --skip-text (the built pictures are not in the repository)
    r = ok((SAMPLE / 'script.md').read_text(encoding='utf-8'), SAMPLE, skip_text=True)
    assert bw.dump(r.work) == (SAMPLE / 'work.json').read_text(encoding='utf-8')
    assert any('[Text]' in w and 'slide 2' in w and 'left out' in w for w in r.warnings)


def test_words_on_screen_without_a_browser_is_an_error():
    assert 'need Microsoft Edge or Google Chrome' in errors((SAMPLE / 'script.md').read_text(encoding='utf-8'), SAMPLE)


# ---------- headings (§2.2) ----------

def test_no_slide_headings_is_an_error():
    assert 'no slide headings' in errors('# T\n\nJust text.\n')


def test_translated_heading_is_named():
    e = errors('# T\n\n## [スライド 1] 表紙\n\nこんにちは\n')
    assert 'never translated' in e and 'no slide headings' in e


def test_numbers_must_run_1_to_n():
    assert 'found 1, 3' in errors(script('## [Slide 1] A\n\na\n', '## [Slide 3] B\n\nb\n'))


def test_missing_title_is_an_error():
    assert 'no title' in errors('> Language: en\n\n## [Slide 1] A\n\na\n')


def test_title_and_empty_slide_title():
    w = ok('# My story\n\n> Language: en\n\n## [Slide 1]\n\nhello\n').work
    assert w['title'] == 'My story' and w['slides'][0]['title'] == ''


def test_heading_inside_a_production_note_does_not_count():
    w = ok(script('## [Slide 1] A\n\na\n\n<!--\n## [Slide 2] draft\n-->\n')).work
    assert len(w['slides']) == 1


# ---------- notes (§3.2) ----------

def test_note_only_lines_go_with_their_line_break_and_blank_runs_fold():
    w = ok(script('## [Slide 1] A\n\none\n\n<!-- pause -->\n\ntwo\n')).work
    assert w['slides'][0]['notes'] == 'one\n\ntwo'


def test_note_inside_a_line_keeps_the_rest():
    w = ok(script('## [Slide 1] A\n\nkeep <!-- not this --> this\n')).work
    assert w['slides'][0]['notes'] == 'keep  this'


def test_multi_line_note_is_removed():
    w = ok(script('## [Slide 1] A\n\nbefore\n<!-- one\ntwo\nthree -->\nafter\n')).work
    assert w['slides'][0]['notes'] == 'before\nafter'


def test_blank_lines_stay_when_nothing_was_removed():
    w = ok(script('## [Slide 1] A\n\none\n\n\n\ntwo\n')).work
    assert w['slides'][0]['notes'] == 'one\n\n\n\ntwo'


def test_bold_marks_go_and_free_cues_keep_their_mark():
    w = ok(script('## [Slide 1] A\n\n> **Wait** here.\n\nSay **this**.\n')).work
    assert w['slides'][0]['notes'] == '> Wait here.\n\nSay this.'


def test_a_hole_keeps_its_mark_in_the_notes_as_narration():
    r = ok(script('## [Slide 1] A\n\n> Wait here.\n\n~ Our **own** story\n~ goes here.\n\nThe end.\n'))
    assert r.work['slides'][0]['notes'] == '> Wait here.\n\n~ Our own story\n~ goes here.\n\nThe end.'
    assert r.warnings == []


@pytest.mark.parametrize('line', ['～ 全角のチルダ', '〜 波ダッシュ', '~no space', '~ '])
def test_a_line_that_looks_like_a_hole_mark_is_warned(line):
    r = ok(script(f'## [Slide 1] A\n\n{line}\n\nb\n'))
    assert any('line 7' in w and 'hole' in w for w in r.warnings), r.warnings
    assert r.work['slides'][0]['notes'].startswith(line.rstrip())


def test_tildes_that_are_not_a_mark_are_left_alone():
    r = ok(script('## [Slide 1] A\n\n~~struck~~ and ~ in a line\n'))
    assert r.warnings == []


def test_line_breaks_and_trailing_spaces_are_kept():
    w = ok(script('## [Slide 1] A\n\na short line  \nand the next\n')).work
    assert w['slides'][0]['notes'] == 'a short line  \nand the next'


def test_crlf_builds_the_same_as_lf():
    lf = script('## [Slide 1] A\n\none\n\n<!-- x -->\n\ntwo\n')
    assert bw.dump(ok(lf.replace('\n', '\r\n')).work) == bw.dump(ok(lf).work)


def test_unclosed_note_is_an_error():
    assert 'never closed' in errors(script('## [Slide 1] A\n\na <!-- oops\n\nb\n'))


def test_text_after_end_marker_is_ignored_with_a_warning():
    r = ok('# T\n\n> Language: en\n\n## [Slide 1] A\n\na\n\n---\n\nstray\n')
    assert r.work['slides'][0]['notes'] == 'a'
    assert any('after "---"' in w for w in r.warnings)


# ---------- machine cues (§2.4, §3.3) ----------

def test_cues_in_order_with_their_types():
    w = ok(script('## [Slide 1] A\n\n> [BGM] sounds/a.mp3\n\n> [Sound] sounds/b.mp3\n\n> [Video] videos/c.mp4\n\n'
                  '> [Video] videos/d.mp4\n\nnarration\n',
                  '## [Slide 2] B\n\n> [BGM once] sounds/e.mp3\n\nb\n',
                  '## [Slide 3] C\n\n> [BGM stop]\n\nc\n')).work
    assert w['slides'][0]['cues'] == [{'type': 'bgm', 'file': 'sounds/a.mp3'}, {'type': 'sound', 'file': 'sounds/b.mp3'},
                                      {'type': 'video', 'file': 'videos/c.mp4'}, {'type': 'video', 'file': 'videos/d.mp4'}]
    assert w['slides'][1]['cues'] == [{'type': 'bgm', 'file': 'sounds/e.mp3', 'loop': False}]
    assert w['slides'][2]['cues'] == [{'type': 'bgm-stop'}]
    assert [s['notes'] for s in w['slides']] == ['narration', 'b', 'c']


def test_bgm_after_video_waits_for_the_video_on_its_slide():
    w = ok(script('## [Slide 1] A\n\n> [BGM after video] sounds/e.mp3\n> [Video] videos/c.mp4\n\na\n')).work
    assert w['slides'][0]['cues'] == [{'type': 'bgm', 'file': 'sounds/e.mp3', 'loop': False, 'start': 'after-video'},
                                      {'type': 'video', 'file': 'videos/c.mp4'}]
    assert '[BGM after video] needs a [Video]' in errors(script('## [Slide 1] A\n\n> [BGM after video] sounds/e.mp3\n\na\n'))
    assert 'more than one of' in errors(script('## [Slide 1] A\n\n> [BGM] sounds/a.mp3\n> [BGM after video] sounds/e.mp3\n'
                                               '> [Video] videos/c.mp4\n\na\n'))


def test_machine_cues_may_follow_one_another():
    w = ok(script('## [Slide 1] A\n\n> [Picture] pictures/x.png\n> [Sound] sounds/b.mp3\n\na\n')).work
    assert w['slides'][0]['picture'] == 'pictures/x.png'
    assert w['slides'][0]['cues'] == [{'type': 'sound', 'file': 'sounds/b.mp3'}]


def test_unknown_or_translated_cue_is_an_error():
    assert 'unknown cue "[Bild]"' in errors(script('## [Slide 1] A\n\n> [Bild] pictures/1.jpg\n'))


def test_cue_block_with_another_line_is_an_error():
    assert 'not a machine cue' in errors(script('## [Slide 1] A\n\n> [Sound] sounds/b.mp3\n> wait for it\n'))


def test_cue_hidden_in_a_free_cue_is_an_error():
    assert 'would do nothing' in errors(script('## [Slide 1] A\n\n> Wait.\n> [BGM] sounds/a.mp3\n'))


def test_two_pictures_or_two_music_cues_are_errors():
    assert 'more than one [Picture]' in errors(
        script('## [Slide 1] A\n\n> [Picture] pictures/a.jpg\n\n> [Picture] pictures/b.jpg\n'))
    assert 'more than one of [BGM]' in errors(script('## [Slide 1] A\n\n> [BGM] s/a.mp3\n\n> [BGM stop]\n'))


def test_paths_use_forward_slashes():
    assert 'use "/"' in errors(script('## [Slide 1] A\n\n> [Sound] sounds\\b.mp3\n'))


def test_cue_without_a_file_is_an_error():
    assert 'needs a file path' in errors(script('## [Slide 1] A\n\n> [Video]\n'))


# ---------- words on the screen (§2.6) ----------

def test_text_block_is_read_and_left_out_of_notes():
    w = ok(script('## [Slide 1] A\n\n> [Text] place top size 54pt bold\n> The storm\n>\n> that night\n\nnarration\n'),
           skip_text=True).work
    assert w['slides'][0]['notes'] == 'narration'
    assert 'overlays' not in w['slides'][0]


def test_text_with_four_lengths_and_every_option():
    ok(script('## [Slide 1] A\n\n> [Text] left 0.50in top 6.3in width 4in height 0.80in size 28pt align left '
              'anchor bottom color #FFFFFF fill #102030\n> Winter\n'), skip_text=True)


@pytest.mark.parametrize('line, message', [
    ('> [Text] size 40pt', 'needs "place'),
    ('> [Text] place top left 1in top 1in width 1in height 1in', 'not both'),
    ('> [Text] left 1in top 1in width 1in', 'missing: height'),
    ('> [Text] place top couleur #FFFFFF', 'unknown word "couleur"'),
    ('> [Text] place top size 40', '"size 40" is not a value'),
    ('> [Text] place top left 0.505in', 'not both'),
    ('> [Text] place up', '"place up" is not a value'),
    ('> [Text] place top place bottom', 'written twice'),
])
def test_text_line_mistakes(line, message):
    assert message in errors(script(f'## [Slide 1] A\n\n{line}\n> words\n'))


def test_text_without_words_is_an_error():
    assert 'has no words' in errors(script('## [Slide 1] A\n\n> [Text] place top\n\nnarration\n'))


def test_forgotten_blank_line_after_text_is_an_error():
    assert 'read as words' in errors(script('## [Slide 1] A\n\n> [Text] place top\n> Title\n> [Sound] s/b.mp3\n'))


# ---------- pictures and media (§2.5, §4) ----------

@pytest.fixture
def media(tmp_path):
    (tmp_path / 'pictures').mkdir()
    (tmp_path / 'pictures' / '01.png').write_bytes(b'x')
    (tmp_path / 'videos').mkdir()
    (tmp_path / 'videos' / 'v.mp4').write_bytes(b'x' * 10)
    return tmp_path


def test_picture_without_cue_finds_the_real_extension(media):
    w = ok(script('## [Slide 1] A\n\na\n'), media).work
    assert w['slides'][0]['picture'] == 'pictures/01.png'


def test_missing_picture_keeps_the_default_name_and_warns(media):
    r = ok(script('## [Slide 1] A\n\na\n', '## [Slide 2] B\n\nb\n'), media)
    assert r.work['slides'][1]['picture'] == 'pictures/02.jpg'
    assert any('slide 2: picture not found' in w for w in r.warnings)


def test_a_new_picture_beside_the_named_one_is_pointed_out(media):
    # 見本から作り替えるとき: 台本が pictures/02.jpg を名指ししていて、チャット AI の絵を 02.png で隣に置いた
    (media / 'pictures' / '02.jpg').write_bytes(b'x')
    (media / 'pictures' / '02.png').write_bytes(b'x')
    r = ok(script('## [Slide 1] A\n\na\n', '## [Slide 2] B\n\n> [Picture] pictures/02.jpg\n\nb\n'), media)
    assert r.work['slides'][1]['picture'] == 'pictures/02.jpg'
    assert any('slide 2' in w and 'pictures/02.png is there too' in w and '> [Picture] pictures/02.png' in w
               for w in r.warnings)


def test_a_new_picture_beside_the_default_one_is_pointed_out(media):
    (media / 'pictures' / '01.jpg').write_bytes(b'x')
    r = ok(script('## [Slide 1] A\n\na\n'), media)
    assert r.work['slides'][0]['picture'] == 'pictures/01.jpg'
    assert any('slide 1' in w and 'pictures/01.png is there too' in w for w in r.warnings)


def test_a_named_picture_that_moved_to_another_extension_names_it(media):
    # 絵のはしごの --use は、02.jpg を _replaced/ へ動かし 02.png を置く
    r = ok(script('## [Slide 1] A\n\n> [Picture] pictures/01.jpg\n\na\n'), media)
    assert any('slide 1: picture not found: pictures/01.jpg' in w and 'pictures/01.png is there' in w
               for w in r.warnings)


def test_video_slide_without_picture_has_null(media):
    r = ok(script('## [Slide 1] A\n\na\n', '## [Slide 2] B\n\n> [Video] videos/v.mp4\n'), media)
    assert r.work['slides'][1]['picture'] is None
    assert not any('slide 2' in w for w in r.warnings)


def test_without_media_folder_default_names_are_written(media):
    w = ok(script('## [Slide 1] A\n\na\n')).work
    assert w['slides'][0]['picture'] == 'pictures/01.jpg'


def test_heic_picture_is_an_error(media):
    (media / 'pictures' / '02.heic').write_bytes(b'x')
    assert 'Export it as JPEG' in errors(script('## [Slide 1] A\n\na\n', '## [Slide 2] B\n\nb\n'), media)


def test_missing_media_and_large_video_warn(media, monkeypatch):
    monkeypatch.setattr(bw, 'VIDEO_MAX_BYTES', 5)
    r = ok(script('## [Slide 1] A\n\n> [Video] videos/v.mp4\n\n> [Sound] sounds/none.mp3\n\n> [Video] videos/c.mov\n'),
           media)
    text = ' | '.join(r.warnings)
    assert 'over 300 MB' in text and 'file not found: sounds/none.mp3' in text and 'c.mov is not MP4' in text


# ---------- linked videos (§2.4, §3.3) ----------

TED = 'https://www.youtube.com/watch?v=8KkKuTCFvzI'


def test_a_youtube_link_is_a_linked_video_with_its_stretch(media):
    r = ok(script(f'## [Slide 1] A\n\n> [Video] {TED} start 5:51 end 6:09\n\na\n',
                  '## [Slide 2] B\n\n> [Video] https://youtu.be/dCVlRFWOjgE start 45.5\n\nb\n',
                  '## [Slide 3] C\n\n> [Video] https://www.youtube.com/embed/dCVlRFWOjgE?start=45&end=158\n\nc\n',
                  '## [Slide 4] D\n\n> [Video] https://youtu.be/dCVlRFWOjgE?t=1m5s end 1:30\n'
                  '> [Video] videos/v.mp4\n\nd\n'), media)
    cues = [s['cues'] for s in r.work['slides']]
    assert cues[0] == [{'type': 'video', 'url': TED, 'start': 351, 'end': 369}]
    assert cues[1] == [{'type': 'video', 'url': 'https://www.youtube.com/watch?v=dCVlRFWOjgE', 'start': 45.5}]
    assert cues[2] == [{'type': 'video', 'url': 'https://www.youtube.com/watch?v=dCVlRFWOjgE', 'start': 45, 'end': 158}]
    assert cues[3] == [{'type': 'video', 'url': 'https://www.youtube.com/watch?v=dCVlRFWOjgE', 'start': 65, 'end': 90},
                       {'type': 'video', 'file': 'videos/v.mp4'}]
    # ファイルが無いことを警告しない（各端末が YouTube から流す）
    assert not any('not found' in w or 'not MP4' in w for w in r.warnings), r.warnings


def test_a_linked_video_slide_without_picture_has_null_and_after_video_music_waits_for_it(media):
    r = ok(script('## [Slide 1] A\n\na\n',
                  f'## [Slide 2] B\n\n> [BGM after video] sounds/x.mp3\n> [Video] {TED} start 351 end 369\n\nb\n'), media)
    assert r.work['slides'][1]['picture'] is None
    assert r.work['slides'][1]['cues'][0]['start'] == 'after-video'


def test_a_linked_video_passes_check_and_the_player_reads_it(tmp_path):
    (tmp_path / 'script.md').write_text(script(f'## [Slide 1] A\n\n> [Video] {TED} start 5:51 end 6:09\n\na\n'),
                                        encoding='utf-8')
    (tmp_path / 'pictures').mkdir()
    (tmp_path / 'pictures' / '01.jpg').write_bytes(b'x')
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / 'skills' / 'digital-kamishibai' / 'scripts' / 'build_work.py'),
                        str(tmp_path), '--check'], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0 and 'warning' not in (r.stdout + r.stderr).lower(), r.stdout + r.stderr


def test_linked_video_mistakes_are_errors():
    def err(line):
        return errors(script(f'## [Slide 1] A\n\n> [Video] {line}\n\na\n'))
    assert 'YouTube link only' in err('https://vimeo.com/12345678')
    assert 'YouTube link only' in err('https://www.youtube.com/watch?v=short')
    assert 'is not a time' in err(f'{TED} start five')
    assert 'is not a time' in err(f'{TED} start 5:75')
    assert 'once each' in err(f'{TED} begin 5:51')
    assert 'once each' in err(f'{TED} start 1 start 2')
    assert '"start <time>"' in err(f'{TED} start')
    assert 'end must come after start' in err(f'{TED} start 6:09 end 5:51')
    assert 'both in the link and after it' in err('https://youtu.be/8KkKuTCFvzI?t=351 start 351')
    assert 'is not a language' in err(f'{TED} captions Japanese!')
    assert 'once each' in err(f'{TED} captions ja captions en')


def test_a_linked_video_may_show_captions_from_the_start():
    w = ok(script(f'## [Slide 1] A\n\n> [Video] {TED} start 5:51 end 6:09 captions ja\n\na\n',
                  '## [Slide 2] B\n\n> [Video] https://youtu.be/dCVlRFWOjgE captions pt-BR start 45\n\nb\n')).work
    assert w['slides'][0]['cues'] == [{'type': 'video', 'url': TED, 'start': 351, 'end': 369, 'captions': 'ja'}]
    assert w['slides'][1]['cues'] == [{'type': 'video', 'url': 'https://www.youtube.com/watch?v=dCVlRFWOjgE', 'start': 45, 'captions': 'pt-BR'}]


def test_a_linked_video_may_be_played_quieter():
    w = ok(script(f'## [Slide 1] A\n\n> [Video] {TED} start 5:51 end 6:09 captions ja volume -6dB\n\na\n',
                  '## [Slide 2] B\n\n> [Video] https://youtu.be/dCVlRFWOjgE volume -7.5db start 45\n\nb\n',
                  '## [Slide 3] C\n\n> [Video] https://youtu.be/dCVlRFWOjgE volume 0dB\n\nc\n')).work
    assert w['slides'][0]['cues'] == [{'type': 'video', 'url': TED, 'start': 351, 'end': 369, 'captions': 'ja', 'volume': -6}]
    assert w['slides'][1]['cues'] == [{'type': 'video', 'url': 'https://www.youtube.com/watch?v=dCVlRFWOjgE', 'start': 45, 'volume': -7.5}]
    assert w['slides'][2]['cues'] == [{'type': 'video', 'url': 'https://www.youtube.com/watch?v=dCVlRFWOjgE'}]


def test_a_linked_video_volume_is_db_and_never_louder():
    def err(line):
        return errors(script(f'## [Slide 1] A\n\n> [Video] {line}\n\na\n'))
    assert 'is not a volume' in err(f'{TED} volume 50')
    assert 'is not a volume' in err(f'{TED} volume +3dB')
    assert 'is not a volume' in err(f'{TED} volume -41dB')
    assert 'is not a volume' in err(f'{TED} volume quiet')
    assert 'once each' in err(f'{TED} volume -6dB volume -3dB')
    assert '"volume <dB>"' in err(f'{TED} volume')


def test_youtube_ids_and_times_read_like_the_player():
    for url in ('https://www.youtube.com/watch?v=8KkKuTCFvzI', 'https://youtu.be/8KkKuTCFvzI?t=3',
                'https://m.youtube.com/watch?v=8KkKuTCFvzI', 'https://www.youtube-nocookie.com/embed/8KkKuTCFvzI',
                'https://www.youtube.com/shorts/8KkKuTCFvzI', 'https://www.youtube.com/live/8KkKuTCFvzI'):
        assert bw.youtube_id(url) == '8KkKuTCFvzI', url
    for url in ('https://www.youtube.com.evil.example/watch?v=8KkKuTCFvzI', 'https://vimeo.com/1',
                'https://www.youtube.com/channel/UCAuUUnT6oDeKwE6v1NGQxug', 'videos/v.mp4'):
        assert bw.youtube_id(url) is None, url
    assert [bw.seconds(t) for t in ('351', '351.5', '5:51', '1:05:51', '5:60', '1:60:00', 'x')] == \
        [351, 351.5, 351, 3951, None, None, None]
    assert [bw.link_seconds(t) for t in ('351', '351s', '5m51s', '1h', 'x')] == [351, 351, 351, 3600, None]


# ---------- language ----------

def test_language_from_header_or_guessed():
    assert ok('# T\n\n> Language: ja\n\n## [Slide 1] A\n\nhello\n').work['language'] == 'ja'
    r = ok('# T\n\n## [Slide 1] 表紙\n\nこんばんは。\n')
    assert r.work['language'] == 'ja' and any('guessed "ja"' in w for w in r.warnings)


# ---------- command line ----------

def test_cli_writes_work_json(tmp_path):
    (tmp_path / 'script.md').write_text(script('## [Slide 1] A\n\na\n'), encoding='utf-8')
    assert bw.main([str(tmp_path)]) == 0
    assert (tmp_path / 'work.json').read_text(encoding='utf-8').startswith('{\n  "format": "digital-kamishibai/work"')


def test_cli_check_writes_nothing(tmp_path):
    (tmp_path / 'script.md').write_text(script('## [Slide 1] A\n\na\n'), encoding='utf-8')
    assert bw.main([str(tmp_path), '--check']) == 0
    assert not (tmp_path / 'work.json').exists()


def test_cli_error_writes_nothing_and_keeps_the_old_work_json(tmp_path, capsys):
    (tmp_path / 'script.md').write_text('# T\n\nno slides\n', encoding='utf-8')
    (tmp_path / 'work.json').write_text('old', encoding='utf-8')
    assert bw.main([str(tmp_path)]) == 1
    assert (tmp_path / 'work.json').read_text(encoding='utf-8') == 'old'
    assert 'not written' in capsys.readouterr().err


# ---------- drawing the words into the picture (§2.6) ----------

class FakeRenderer:
    def __init__(self, fits=None, fail=None):
        self.jobs, self.fits, self.fail = None, fits, fail

    def __call__(self, jobs, media):
        if self.fail:
            raise RuntimeError(self.fail)
        self.jobs = jobs
        return self.fits


TEXT_SLIDES = script(
    '## [Slide 1] A\n\n> [Text] place top size 54pt bold color #ffffff\n> The storm\n>\n>\n>\n> that night\n\nnarration\n',
    '## [Slide 2] B\n\n> [Text] left 0.50in top 6.30in width 4.00in height 0.80in fill #102030 align left anchor bottom\n'
    '> Winter\n\n> [Text] place bottom\n> second box\n\nb\n',
    '## [Slide 3] C\n\nno words\n')


def test_built_pictures_replace_the_slide_pictures_only_where_there_are_words(media):
    fake = FakeRenderer()
    w = ok(TEXT_SLIDES, media, renderer=fake).work
    assert [s['picture'] for s in w['slides']] == ['pictures/_built/01.jpg', 'pictures/_built/02.jpg', 'pictures/03.jpg']
    assert [j['out'] for j in fake.jobs] == [media / 'pictures/_built/01.jpg', media / 'pictures/_built/02.jpg']
    assert [j['base'] for j in fake.jobs] == [None, None]
    assert fake.jobs[0]['picture'] == 'pictures/01.png' and fake.jobs[1]['picture'] is None   # 02 is missing: black
    assert 'draft' not in w and 'overlays' not in w['slides'][0]


def test_draft_writes_overlays_layout_base_and_slide_size(media):
    fake = FakeRenderer()
    w = ok(TEXT_SLIDES, media, renderer=fake, draft=True).work
    assert list(w)[:6] == ['format', 'version', 'title', 'language', 'draft', 'slide_size']
    assert w['draft'] is True and w['slide_size'] == {'width': 12192000, 'height': 6858000}
    s1, s2, s3 = w['slides']
    assert s1['overlays'] == [[['The storm'], [''], ['that night']]]
    assert s1['overlay_base'] == 'pictures/_built/01.base.jpg'
    assert fake.jobs[0]['base'] == media / 'pictures/_built/01.base.jpg'
    assert s1['overlay_layout'] == [{
        'x': 457200, 'y': 274320, 'width': 11274552, 'height': 1097280, 'inset': [91440, 45720, 91440, 45720],
        'anchor': 'middle', 'wrap': True,
        'paragraphs': [{'align': 'center', 'space_before': 0, 'size': 54, 'bold': True, 'color': '#FFFFFF',
                        'font': 'Arial'}] * 3}]
    box = s2['overlay_layout'][0]
    assert (box['x'], box['y'], box['width'], box['height']) == (457200, 5760720, 3657600, 731520)
    assert box['fill'] == '#102030' and box['anchor'] == 'bottom'
    assert box['paragraphs'][0] == {'align': 'left', 'space_before': 0, 'size': 40, 'bold': False,
                                    'color': '#000000', 'font': 'Arial'}
    assert s2['overlays'] == [[['Winter']], [['second box']]]
    assert 'overlays' not in s3 and s3['picture'] == 'pictures/03.jpg'


def test_draft_names_the_picture_each_built_picture_was_made_from(media):
    # the player tells a new picture by this file: the built one is written again at every build (Issue #5)
    w = ok(TEXT_SLIDES, media, renderer=FakeRenderer(), draft=True).work
    s1, s2, s3 = w['slides']
    assert s1['picture_source'] == 'pictures/01.png'
    assert 'picture_source' not in s2      # its picture is missing: drawn on black
    assert 'picture_source' not in s3      # no words: the slide shows the picture itself
    w = ok(TEXT_SLIDES, media, renderer=FakeRenderer()).work
    assert 'picture_source' not in w['slides'][0], 'only for practising'


@pytest.mark.parametrize('language, font', [('ja', 'Meiryo'), ('ko', 'Malgun Gothic'), ('zh-TW', 'Microsoft YaHei'),
                                            ('en', 'Arial'), ('fr', 'Arial')])
def test_font_follows_the_language(media, language, font):
    w = ok(script('## [Slide 1] A\n\n> [Text] place top\n> x\n', header=f'# T\n\n> Language: {language}\n'),
           media, renderer=FakeRenderer(), draft=True).work
    assert w['slides'][0]['overlay_layout'][0]['paragraphs'][0]['font'] == font


def test_words_that_do_not_fit_warn(media):
    r = ok(TEXT_SLIDES, media, renderer=FakeRenderer(fits=[[{'off': True, 'outside': False}],
                                                            [{'off': False, 'outside': True},
                                                             {'off': False, 'outside': False}]]))
    text = ' | '.join(r.warnings)
    assert 'slide 1: the words of [Text] 1 run off the slide' in text
    assert 'slide 2: the words of [Text] 1 run out of its colour band' in text
    assert '[Text] 2' not in text


def test_a_failed_drawing_is_an_error(media):
    assert 'could not draw the words on the screen: no browser' in errors(
        TEXT_SLIDES, media, renderer=FakeRenderer(fail='no browser'))


def test_a_cut_connection_points_at_the_sandbox(media):
    class Cut(FakeRenderer):
        def __call__(self, *args, **kwargs):
            raise ConnectionResetError(10054, 'the connection was reset')
    said = errors(TEXT_SLIDES, media, renderer=Cut())
    assert 'run this command outside it' in said
    assert 'run this command outside it' not in errors(TEXT_SLIDES, media, renderer=FakeRenderer(fail='no browser'))


def test_words_on_a_video_only_slide_are_an_error(media):
    assert 'needs a picture to draw on' in errors(
        script('## [Slide 1] A\n\na\n', '## [Slide 2] B\n\n> [Video] videos/v.mp4\n\n> [Text] place top\n> x\n'),
        media, renderer=FakeRenderer())


def test_skip_text_leaves_pictures_alone(media):
    w = ok(TEXT_SLIDES, media, skip_text=True, renderer=FakeRenderer()).work
    assert w['slides'][0]['picture'] == 'pictures/01.png'


# ---------- the real browser (only where Edge or Chrome is installed) ----------

def jpeg_size(data):
    i = 2
    while i < len(data):
        marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], 'big')
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], 'big'), int.from_bytes(data[i + 5:i + 7], 'big')
        i += 2 + length
    return None


@pytest.mark.skipif(bw.burn.find_browser() is None, reason='no Microsoft Edge or Google Chrome')
def test_burning_the_sample_story(tmp_path):
    import shutil
    work = tmp_path / 'sample'
    shutil.copytree(SAMPLE, work)
    before = {p.name: p.read_bytes() for p in (work / 'pictures').iterdir()}
    assert bw.main([str(work), '--draft']) == 0
    built = work / 'pictures' / '_built'
    for name in ('02.jpg', '02.base.jpg'):
        data = (built / name).read_bytes()
        assert data[:2] == b'\xff\xd8' and jpeg_size(data) == (1920, 1080)
    assert (built / '02.jpg').read_bytes() != (built / '02.base.jpg').read_bytes()
    assert {p.name: p.read_bytes() for p in (work / 'pictures').iterdir() if p.is_file()} == before  # originals untouched
    w = json.loads((work / 'work.json').read_text(encoding='utf-8'))
    assert w['slides'][1]['picture'] == 'pictures/_built/02.jpg' and w['draft'] is True


# ---------- ending video seats (§3.3, only with --draft) ----------

def test_the_ending_video_gets_its_seats_only_in_a_draft():
    source = (SAMPLE / 'script.md').read_text(encoding='utf-8')
    plain = ok(source, SAMPLE, skip_text=True, definitions=SAMPLE).work
    assert plain['slides'][3]['cues'] == [{'type': 'video', 'file': 'videos/ending.mp4'}]
    draft = ok(source, SAMPLE, skip_text=True, draft=True, definitions=SAMPLE).work
    cue = draft['slides'][3]['cues'][0]
    assert cue['role'] == 'ending'
    assert cue['seats'] == [
        {'n': 1, 'from': 0.0, 'to': 6.4, 'label': 'pictures/02.png'},          # the 0.8 s cross-fades split at the middle
        {'n': 2, 'from': 6.4, 'to': 12.4, 'label': 'pictures/03.png'},
        {'n': 3, 'from': 12.4, 'to': 18.0, 'label': 'pictures/01.jpg', 'pin': 'the title at the end of the song'},
    ]


def ending_work(tmp_path, definition):
    (tmp_path / 'ending_video_second.json').write_text(json.dumps(definition), encoding='utf-8')
    return '# T\n\n## [Slide 1] End\n\n> [Video] videos/second.mp4\n'


def test_a_seat_whose_picture_is_gone_is_warned_with_the_command(tmp_path):
    # Issue #7: --use moved the slide's picture to _replaced/, and the ending video still showed the old one
    (tmp_path / 'pictures').mkdir()
    (tmp_path / 'pictures' / '07.png').write_bytes(b'x')
    (tmp_path / 'pictures' / '08.jpg').write_bytes(b'x')
    source = ending_work(tmp_path, {'output': 'second.mp4', 'frames': [
        {'i': 1, 'at': 0, 'dur': 5, 'src': 'pictures/07.jpg'}, {'i': 2, 'at': 5, 'dur': 5, 'src': 'pictures/08.jpg'},
        {'i': 3, 'at': 10, 'dur': 5, 'src': 'pictures/09.jpg'}, {'i': 4, 'at': 15, 'dur': 5}]})
    for draft in (False, True):
        warnings = [w for w in ok(source, tmp_path, draft=draft, definitions=tmp_path).warnings if 'seat' in w]
        assert len(warnings) == 2, warnings
        assert 'seat 1 shows pictures/07.jpg' in warnings[0]
        assert '--config second --replace 1=pictures/07.png' in warnings[0]
        assert 'seat 3 shows pictures/09.jpg' in warnings[1] and '--replace 3=FILE' in warnings[1]


def test_seats_in_a_photo_folder_elsewhere_are_not_looked_at(tmp_path):
    source = ending_work(tmp_path, {'output': 'second.mp4', 'photo_root': 'D:/Photos', 'frames': [
        {'i': 1, 'at': 0, 'dur': 5, 'src': '2016/bike.jpg'}, {'i': 2, 'at': 5, 'dur': 5, 'src': 'pictures/01.jpg', 'root': 'work'}]})
    warnings = [w for w in ok(source, tmp_path, definitions=tmp_path).warnings if 'seat' in w]
    assert len(warnings) == 1 and 'seat 2 shows pictures/01.jpg' in warnings[0], warnings


def test_seats_start_after_the_prologue(tmp_path):
    source = ending_work(tmp_path, {'output': 'second.mp4', 'prologue': {'src': 'a.mp4', 'dur': 8},
                                    'frames': [{'i': 1, 'at': 0, 'dur': 5, 'src': 'x.jpg'}, {'i': 2, 'at': 5, 'dur': 4.5}]})
    cue = ok(source, tmp_path, draft=True, definitions=tmp_path).work['slides'][0]['cues'][0]
    assert cue['seats'] == [{'n': 1, 'from': 8.0, 'to': 13.0, 'label': 'x.jpg'}, {'n': 2, 'from': 13.0, 'to': 17.5}]


@pytest.mark.parametrize('frames, why', [
    ([{'i': 1, 'at': 0, 'dur': 5}, {'i': 3, 'at': 5, 'dur': 5}], 'numbered 3'),
    ([{'i': 1, 'at': 0, 'dur': 5}, {'i': 2, 'at': 4, 'dur': 5}], 'not in order'),
    ([{'i': 1, 'dur': 5}], 'cannot read'),
])
def test_a_broken_definition_leaves_the_seats_out_with_a_warning(tmp_path, frames, why):
    source = ending_work(tmp_path, {'output': 'second.mp4', 'frames': frames})
    r = ok(source, tmp_path, draft=True, definitions=tmp_path)
    assert r.work['slides'][0]['cues'][0] == {'type': 'video', 'file': 'videos/second.mp4'}
    assert any('ending_video_second.json' in w and why in w for w in r.warnings), r.warnings
