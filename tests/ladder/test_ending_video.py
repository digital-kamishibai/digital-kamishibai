"""Tests for ladder/ending-video/ (build_ending_video.py, storyboard_page.py, check_smoothness.py).

Most tests are pure (no ffmpeg). The last ones build a real video from made-up pictures and a made-up song when
ffmpeg is on the PATH, and are skipped otherwise.
"""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip('PIL')
from PIL import Image, ImageDraw  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LADDER = ROOT / 'ladder' / 'ending-video'
SAMPLE = ROOT / 'examples' / 'sample-story'
sys.path.insert(0, str(LADDER))


def load(name):
    spec = importlib.util.spec_from_file_location(name, LADDER / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bev = load('build_ending_video')
page = load('storyboard_page')
smooth = load('check_smoothness')

HAS_FFMPEG = shutil.which('ffmpeg') is not None and shutil.which('ffprobe') is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason='ffmpeg/ffprobe not on the PATH')


def definition(**extra):
    data = {
        'audio': 'sounds/song.mp3', 'output': 'ending.mp4', 'duration_sec': 12.0, 'photo_root': 'photos',
        'frames': [
            {'i': 1, 'at': 0.0, 'dur': 4.0, 'xfade': 0.6, 'beat': 'Intro', 'src': '2019/a.jpg', 'status': 'placeholder'},
            {'i': 2, 'at': 4.0, 'dur': 4.0, 'xfade': 0.6, 'beat': 'Verse', 'src': '2019/b.jpg', 'status': 'picked',
             'pin': 'the first line of the verse'},
            {'i': 3, 'at': 8.0, 'dur': 4.0, 'xfade': 0.0, 'beat': 'Verse', 'kind': 'clip',
             'src': '2019/c.mp4', 'clip_start_sec': 1.0, 'status': 'placeholder'},
        ],
    }
    data.update(extra)
    return data


def errors_of(data):
    return ' | '.join(bev.validate_config(data))


# ---------- the definition ----------

def test_a_good_definition_passes():
    assert bev.validate_config(definition()) == []


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('audio'), 'missing key audio'),
    (lambda d: d.update(output='ending.mov'), 'output='),
    (lambda d: d.update(output='videos/ending.mp4'), 'output='),
    (lambda d: d.pop('photo_root'), 'missing key photo_root'),
    (lambda d: d.update(frames=[]), 'no seats'),
    (lambda d: d['frames'][0].pop('src'), 'missing key src'),
    (lambda d: d['frames'][0].update(kind='pan'), 'kind='),
    (lambda d: d['frames'][0].update(status='done'), 'status='),
    (lambda d: d['frames'][2].pop('clip_start_sec'), 'clip_start_sec'),
    (lambda d: d['frames'][1].update(i=1), 'used again'),
    (lambda d: d['frames'][0].update(xfade=4.0), 'eats the seat'),
    (lambda d: d['frames'][1].update(at=4.5), 'gap'),
    (lambda d: d['frames'][1].update(at=3.5), 'overlap'),
    (lambda d: d.update(duration_sec=13.0), 'add up to'),
    (lambda d: d['frames'][1].update(pin=''), 'pin='),
    (lambda d: d['frames'][0].update(rotate='left'), 'rotate='),
    (lambda d: d['frames'][0].update(zoom_from=1.03, zoom=1.06), 'not a zoom out'),
    (lambda d: d['frames'][0].update(zoom_center=[0.5, 0.5]), 'zoom_center works only'),
    (lambda d: d['frames'][0].update(ease='out'), 'ease works only'),
    (lambda d: d['frames'][2].update(zoom_from=1.2), 'still seat'),
    (lambda d: d['frames'][0].update(clip_hold_sec=1.0), 'only in a clip seat'),
    (lambda d: d['frames'][2].update(clip_hold_sec=4.0), 'would not play'),
    (lambda d: d.update(pre_still={'src': 'x.jpg', 'dur': 2}), 'not supported'),
    (lambda d: d['frames'][0].update(layer={'src': 'band.png'}), 'not supported'),
    (lambda d: d.update(final_still={'color': '#FFFFFF'}), 'needs a title'),
    (lambda d: d.update(video_fade_out=5.0), 'longer than the last seat'),
    (lambda d: d.update(prologue={'src': 'p.mp4'}), 'prologue: missing key dur'),
    (lambda d: d.update(prologue={'src': 'p.mp4', 'dur': 2, 'fade_in': 1, 'fade_out': 1}), 'not shorter'),
    (lambda d: d.update(epilogue={'src': 'e.mp4', 'dur': 2, 'body_fade_in': 1}), 'belongs to the prologue'),
    (lambda d: d.update(epilogue={'src': 'e.mp4', 'dur': 2}, video_fade_out=1.0), 'do the same thing'),
])
def test_definition_errors(change, message):
    data = definition()
    change(data)
    assert message in errors_of(data) and errors_of(data)


def test_photo_root_is_not_needed_when_everything_is_in_the_work_folder():
    data = definition()
    data.pop('photo_root')
    for f in data['frames']:
        f['root'] = 'work'
    assert bev.validate_config(data) == []


def test_clip_parts_must_fill_the_seat():
    data = definition()
    data['frames'][2].update(clip_parts=[{'start': 1.0, 'dur': 2.0}, {'start': 9.0, 'dur': 2.0}])
    assert bev.validate_config(data) == []
    data['frames'][2]['clip_parts'][1]['dur'] = 1.0
    assert 'add up to 3.000' in errors_of(data)
    data['frames'][2]['clip_parts'][1]['dur'] = 2.0
    data['frames'][2]['clip_start_sec'] = 2.0
    assert 'clip_start_sec must equal' in errors_of(data)


def test_total_length_is_prologue_song_epilogue_and_the_seats_do_not_move():
    data = definition(prologue={'src': 'p.mp4', 'dur': 3.0}, epilogue={'src': 'e.mp4', 'dur': 2.5})
    assert bev.validate_config(data) == []
    assert bev.total_length(data) == 17.5
    assert [f['at'] for f in data['frames']] == [0.0, 4.0, 8.0]


# ---------- seats and content ----------

def test_replace_keeps_the_seat():
    data = definition()
    before = copy.deepcopy(data['frames'][0])
    f = bev.apply_replace(data, 1, '2020\\d.jpg')
    assert f['src'] == '2020/d.jpg' and f['status'] == 'picked'
    assert {k: f[k] for k in ('i', 'at', 'dur', 'xfade', 'beat')} == {k: before[k] for k in ('i', 'at', 'dur', 'xfade', 'beat')}
    assert data['frames'][1]['src'] == '2019/b.jpg'


def test_replace_with_a_video_makes_a_clip_and_back():
    data = definition()
    bev.apply_replace(data, 1, '2019/v.mp4', clip_start_sec=2.5)
    assert data['frames'][0]['kind'] == 'clip' and data['frames'][0]['clip_start_sec'] == 2.5
    bev.apply_replace(data, 3, '2019/e.jpg')
    assert 'kind' not in data['frames'][2] and 'clip_start_sec' not in data['frames'][2]
    assert bev.validate_config(data) == []


def test_replace_drops_what_was_fitted_to_the_old_video():
    data = definition()
    data['frames'][2]['clip_hold_sec'] = 1.0
    bev.apply_replace(data, 3, '2019/other.mp4')
    assert 'clip_hold_sec' not in data['frames'][2] and data['frames'][2]['clip_start_sec'] == 0.0


def test_replace_leaves_a_closing_picture_closing():
    data = definition()
    data['frames'][2] = {'i': 3, 'at': 8.0, 'dur': 4.0, 'kind': 'final', 'root': 'work', 'src': 'pictures/03.png'}
    bev.apply_replace(data, 3, 'pictures/01.jpg')
    assert data['frames'][2]['kind'] == 'final'


def test_replace_an_unknown_seat():
    with pytest.raises(bev.ConfigError):
        bev.apply_replace(definition(), 9, 'x.jpg')


def test_move_moves_only_the_content():
    data = definition()
    seats = [(f['i'], f['at'], f['dur'], f.get('beat'), f.get('pin')) for f in data['frames']]
    bev.apply_move(data, 3, 0)
    assert [f['src'] for f in data['frames']] == ['2019/c.mp4', '2019/a.jpg', '2019/b.jpg']
    assert data['frames'][0]['kind'] == 'clip' and data['frames'][0]['clip_start_sec'] == 1.0
    assert [(f['i'], f['at'], f['dur'], f.get('beat'), f.get('pin')) for f in data['frames']] == seats
    assert bev.validate_config(data) == []
    bev.apply_move(data, 1, 3)
    assert [f['src'] for f in data['frames']] == ['2019/a.jpg', '2019/b.jpg', '2019/c.mp4']


@pytest.mark.parametrize('i, after', [(9, 1), (1, 9), (2, 2)])
def test_move_errors(i, after):
    with pytest.raises(bev.ConfigError):
        bev.apply_move(definition(), i, after)


def test_sort_by_date_leaves_pinned_seats_even_if_not_passed():
    data = definition()
    dates = {1: '2021-01-01', 2: '2000-01-01', 3: '2010-01-01'}
    moved = bev.apply_sort(data, {1, 2, 3}, lambda i: dates[i])
    assert moved == [1, 3]                                        # seat 2 is pinned in the definition
    assert [f['src'] for f in data['frames']] == ['2019/c.mp4', '2019/b.jpg', '2019/a.jpg']


def test_sort_is_stable():
    data = definition()
    data['frames'][1].pop('pin')
    bev.apply_sort(data, {1, 2, 3}, lambda i: 'same')
    assert [f['src'] for f in data['frames']] == ['2019/a.jpg', '2019/b.jpg', '2019/c.mp4']


def test_pins_need_reasons():
    data = definition()
    assert bev.pinned_seats(data) == {2: 'the first line of the verse'}
    with pytest.raises(bev.ConfigError):
        bev.apply_pin(data, 1, '  ')
    assert bev.apply_pin(data, 1, 'the cover') is None
    assert bev.apply_unpin(data, 2) == 'the first line of the verse'
    assert bev.pinned_seats(data) == {1: 'the cover'}


def test_status_and_numbers():
    data = definition()
    assert bev.apply_status(data, bev.parse_numbers('1-2'), 'confirmed') == 2
    assert bev.parse_numbers('1-3,7') == {1, 2, 3, 7}
    for bad in ('3-1', 'a', ''):
        with pytest.raises(bev.ConfigError):
            bev.parse_numbers(bad)
    with pytest.raises(bev.ConfigError):
        bev.apply_status(data, {9}, 'picked')


def test_kind_from_the_extension():
    assert bev.kind_for('a.MOV') == 'clip' and bev.kind_for('a.jpeg') == 'photo' and bev.kind_for('a.txt') is None


# ---------- paths and lengths ----------

def test_paths(tmp_path):
    data = definition()
    root = bev.photo_root_of(data, str(tmp_path))
    assert root == os.path.normpath(str(tmp_path / 'photos'))
    assert bev.resolve_src(data['frames'][0], root, str(tmp_path)) == os.path.normpath(str(tmp_path / 'photos/2019/a.jpg'))
    assert bev.resolve_src(dict(data['frames'][0], root='work'), root, str(tmp_path)) == \
        os.path.normpath(str(tmp_path / '2019/a.jpg'))
    assert bev.photo_root_of(data, str(tmp_path), override=str(tmp_path / 'elsewhere')) == str(tmp_path / 'elsewhere')
    assert bev.config_path('w', 'second').endswith('ending_video_second.json')
    assert bev.storyboard_paths('w', 'second')[1] == os.path.join('w', 'ending_second', 'storyboard.html')


def test_cross_fades_keep_the_total_length():
    data = definition()
    assert [bev.segment_length(f) for f in data['frames']] == [4.6, 4.6, 4.0]
    assert bev.xfade_offsets(data['frames']) == [4.0, 8.0]
    # every cross-fade shortens the chain by its length: the whole is the sum of dur again
    total = sum(bev.segment_length(f) for f in data['frames']) - sum(f['xfade'] for f in data['frames'][:-1])
    assert total == pytest.approx(12.0)


def test_frames_are_rounded_up():
    assert bev.segment_frames(6.219) == 187 and bev.segment_frames(1.0) == 30


# ---------- commands ----------

def test_clip_seeks_before_input_and_is_silent():
    f = definition()['frames'][2]
    cmd = bev.build_clip_command('in.mp4', f, 'out.mp4')
    assert cmd.index('-ss') < cmd.index('-i') and '-an' in cmd
    assert cmd[cmd.index('-ss') + 1] == '1.000'
    assert '-noautorotate' not in cmd                     # phones' own rotation stays on
    assert 'transpose' not in ' '.join(cmd)


def test_rotate_turns_both_background_and_picture():
    f = dict(definition()['frames'][2], rotate='ccw')
    chain = bev.build_clip_command('in.mp4', f, 'out.mp4')
    graph = chain[chain.index('-filter_complex') + 1]
    assert graph.startswith('[0:v]transpose=2,split=2[rotbg][rotfg];') and '[rotbg]' in graph and '[rotfg]' in graph


def test_held_clip_reads_only_what_plays():
    f = dict(definition()['frames'][2], clip_hold_sec=1.5)
    cmd = bev.build_clip_command('in.mp4', f, 'out.mp4')
    assert cmd[cmd.index('-t') + 1] == '2.500' and cmd.index('-t') < cmd.index('-i')
    assert 'tpad=stop_mode=clone:stop_duration=1.500' in ' '.join(cmd)
    assert bev.clip_thumb_sec(f) == pytest.approx(1.0 + 2.0)


def test_clip_parts_join_with_hard_cuts():
    f = dict(definition()['frames'][2], clip_parts=[{'start': 1.0, 'dur': 2.0}, {'start': 9.0, 'dur': 2.0}])
    cmd = bev.build_clip_command('in.mp4', f, 'out.mp4')
    assert cmd.count('-i') == 2 and 'concat=n=2:v=1:a=0' in ' '.join(cmd)
    assert bev.clip_thumb_sec(f) == pytest.approx(9.0)    # the middle (2.0 s in) is the start of the second stretch


def test_still_seat_is_left_to_ffmpeg_and_moving_seats_are_drawn():
    f = {'i': 1, 'at': 0, 'dur': 2.0, 'src': 'a.jpg', 'zoom': 1.0}
    cmd, feed = bev.build_photo_command('img.jpg', f, 'o.mp4')
    assert feed is None and '-loop' in cmd
    cmd, feed = bev.build_photo_command('img.jpg', dict(f, zoom=1.06), 'o.mp4')
    assert feed is not None and cmd[cmd.index('-f') + 1] == 'rawvideo' and cmd.count('-r') == 2


def picture(path, size=(960, 540)):
    im = Image.new('RGB', size, (40, 90, 160))
    d = ImageDraw.Draw(im)
    for x in range(0, size[0], 23):
        d.line([(x, 0), (x + 100, size[1])], fill=(255, 255, 255), width=2)
    im.save(path)
    return str(path)


def test_zoom_frames_are_all_different_even_slowly(tmp_path, monkeypatch):
    # sub-pixel drawing: no two neighbouring frames alike, even at 0.2 px per frame
    monkeypatch.setattr(bev, 'OUT_W', 192)
    monkeypatch.setattr(bev, 'OUT_H', 108)
    img = picture(tmp_path / 'p.png')
    frames = list(bev.ken_burns_frames(img, 60, 1.0, 1.02))
    assert len(frames) == 60
    assert all(a != b for a, b in zip(frames, frames[1:]))


def test_zoom_out_starts_at_zoom_from_and_keeps_the_centre():
    assert bev.zoom_z_at(1.3, 1.0, 10, 0) == 1.3 and bev.zoom_z_at(1.3, 1.0, 10, 9) == 1.0
    assert bev.zoom_z_at(1.3, 1.0, 11, 5, 'out') < bev.zoom_z_at(1.3, 1.0, 11, 5)       # slows down at the end
    left, top, right, bottom = bev.crop_box_at(1000, 500, 2.0, 0.2, 0.6)
    assert (0.2 * 1000 - left) / (right - left) == pytest.approx(0.2)                    # the point stays put
    assert (0.6 * 500 - top) / (bottom - top) == pytest.approx(0.6)
    assert bev.crop_box_at(1000, 500, 1.06)[0] % 1 != 0                                 # fractions, not pixels


def test_feeding_failures_kill_ffmpeg_and_exit_codes_decide():
    with pytest.raises(subprocess.CalledProcessError):
        bev.run_render([sys.executable, '-c', 'import sys; sys.stdin.read(); sys.exit(3)'],
                       lambda: iter([b'x' * 10]))

    def broken():
        yield b'x'
        raise RuntimeError('picture failed')
    with pytest.raises(RuntimeError):
        bev.run_render([sys.executable, '-c', 'import sys; sys.stdin.read()'], broken)


def test_signature_changes_only_for_what_matters(tmp_path):
    src = tmp_path / 'a.jpg'
    src.write_bytes(b'x')
    f = {'i': 1, 'at': 0, 'dur': 4.0, 'src': 'a.jpg'}
    base = bev.signature(f, str(src))
    assert bev.SUBPIXEL_TAG in base                                  # a moving seat carries the generation
    assert bev.SUBPIXEL_TAG not in bev.signature(dict(f, zoom=1.0), str(src))
    assert bev.signature(dict(f, zoom_from=1.2), str(src)) != base
    assert bev.signature(dict(f, rotate='cw'), str(src)) != base
    clip = {'i': 3, 'at': 0, 'dur': 4.0, 'src': 'a.jpg', 'kind': 'clip', 'clip_start_sec': 1.0}
    assert bev.signature(dict(clip, clip_hold_sec=1.0), str(src)) != bev.signature(clip, str(src))
    assert bev.signature(f, str(src), {'title': 'T'}) != base


def test_part_files_and_unusable_segments(tmp_path):
    tmp, cmd = bev.to_part_command(['ffmpeg', '-i', 'a', 'out.mp4'], 'out.mp4')
    assert tmp == 'out.mp4.part' and cmd[-3:] == ['-f', 'mp4', 'out.mp4.part']
    small = tmp_path / 's.mp4'
    small.write_bytes(b'x' * 48)
    assert not bev.usable_segment(str(small)) and not bev.usable_segment(str(tmp_path / 'none.mp4'))
    small.write_bytes(b'x' * 5000)
    assert bev.usable_segment(str(small))


def test_xfade_join_and_song():
    data = definition()
    cmd = bev.build_xfade_command(['s1', 's2', 's3'], data['frames'], 'song.mp3', 'o.mp4', 12.0, fade_in=0.5,
                                  fade_out=2.0)
    graph = cmd[cmd.index('-filter_complex') + 1]
    assert 'xfade=transition=fade:duration=0.600:offset=4.000' in graph
    assert 'offset=8.000' in graph and 'fade=t=out:st=10.000:d=2.000' in graph and 'fade=t=in:st=0:d=0.500' in graph
    assert cmd[cmd.index('-map', cmd.index('-map') + 1) + 1] == '3:a'


def test_sides_keep_their_sound_and_join_without_re_encoding():
    cmd = bev.build_side_command('p.mp4', {'src': 'p.mp4', 'dur': 4, 'gain_db': 6, 'fade_out': 1}, 'o.mp4')
    joined = ' '.join(cmd)
    assert '-an' not in cmd and 'volume=6.00dB,alimiter' in joined and 'afade=t=out:st=3.000' in joined
    assert cmd.index('-ss') < cmd.index('-i') and 'sample_rates=48000' in joined
    concat = bev.build_concat_command('list.txt', 'o.mp4')
    assert concat[concat.index('-c') + 1] == 'copy' and 'setts=pts=PTS-STARTPTS:dts=DTS-STARTDTS' in concat
    assert bev.concat_list_text(['C:\\a\\it\'s.mp4']) == "file 'C:/a/it'\\''s.mp4'\n"


def test_loudness():
    assert bev.loudness_gain_db(-30.0) == 8.0
    text = 'junk\n  Summary:\n  Integrated loudness:\n    I:         -20.3 LUFS\n  True peak:\n    Peak:       -2.1 dBFS\n'
    assert bev.parse_ebur128_summary(text) == (-20.3, -2.1)
    cmd = bev.build_loudness_command('a.mp4', 'b.mp4', 3.0)
    assert 'level=0' in ' '.join(cmd) and cmd[cmd.index('-c:v') + 1] == 'copy'


def test_replace_waits_out_a_short_lock(tmp_path, monkeypatch):
    # issue #1: in a Dropbox folder the first build stopped with a traceback; the same command just after worked
    src, dst = tmp_path / 'a.part', tmp_path / 'a.mp4'
    src.write_bytes(b'new')
    real, calls, sleeps = os.replace, [], []

    def held_twice(a, b):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError(5, 'Access is denied')
        real(a, b)
    monkeypatch.setattr(bev.os, 'replace', held_twice)
    monkeypatch.setattr(bev.time, 'sleep', sleeps.append)
    bev.replace_file(str(src), str(dst))
    assert dst.read_bytes() == b'new' and not src.exists() and len(sleeps) == 2


def test_replace_that_stays_locked_says_what_to_do(tmp_path, monkeypatch):
    def held(a, b):
        raise PermissionError(5, 'Access is denied')
    monkeypatch.setattr(bev.os, 'replace', held)
    monkeypatch.setattr(bev.time, 'sleep', lambda s: None)
    with pytest.raises(bev.ConfigError) as ex:
        bev.replace_file('a.part', 'a.mp4')
    text = '\n'.join(ex.value.messages)
    assert 'another program is using a.mp4' in text and 'run the same command again' in text


def test_replace_does_not_hide_other_errors(tmp_path):
    with pytest.raises(FileNotFoundError):                                     # only a lock is waited out
        bev.replace_file(str(tmp_path / 'missing.part'), str(tmp_path / 'a.mp4'))


def test_shrink_commands_aim_under_the_player_limit():
    first, second = bev.shrink_commands('a.mp4', 'b.mp4', 270.0, 'log')
    kbps = int(second[second.index('-b:v') + 1][:-1])
    assert kbps * 1000 * 270 / 8 + bev.AUDIO_BPS * 270 / 8 <= bev.TARGET_VIDEO_BYTES * 1.001
    assert first[first.index('-f') + 1] == 'mp4' and '-pass' in second
    with pytest.raises(bev.ConfigError):
        bev.shrink_commands('a.mp4', 'b.mp4', 10 * 3600.0, 'log')               # ten hours cannot fit


# ---------- dates ----------

def test_dates_from_names_and_folders():
    assert bev.fname_date('IMG_20160610_101010.jpg') == '2016-06-10'
    assert bev.fname_date('x_20161340.jpg') is None
    assert bev.fname_datetime('IMG_20160610_101010.jpg') == ('2016-06-10', '10:10')
    assert bev.folder_date(os.path.join('a', '2020', '2025-4', 'x.jpg')) == '2025-04'


def test_pixel_names_are_utc_and_shown_in_local_time():
    import datetime
    local = datetime.datetime(2024, 6, 1, 12, 0, tzinfo=datetime.timezone.utc).astimezone()
    assert bev.fname_datetime('PXL_20240601_120000000.jpg') == (local.strftime('%Y-%m-%d'), local.strftime('%H:%M'))


def test_capture_date_prefers_exif(tmp_path):
    p = tmp_path / '2015' / 'IMG_20160101_000000.jpg'
    p.parent.mkdir()
    im = Image.new('RGB', (10, 10))
    exif = Image.Exif()
    exif[306] = '2014:05:06 07:08:09'
    im.save(p, exif=exif)
    assert bev.capture_datetime(str(p)) == ('2014-05-06', '07:08', 'EXIF')
    q = tmp_path / '2015' / 'plain.jpg'
    Image.new('RGB', (10, 10)).save(q)
    assert bev.capture_datetime(str(q))[2] == 'folder'


# ---------- init ----------

def test_init_frames_cover_the_song():
    frames = bev.init_frames(61.3, 5.0, ['a', 'b', 'c'])
    assert len(frames) == 12 and frames[0]['at'] == 0.0
    assert bev.timeline_errors(frames, 61.3) == []
    assert frames[-1]['xfade'] == 0.0 and all(f['status'] == 'placeholder' for f in frames)
    assert bev.sample_evenly(['a', 'b', 'c', 'd'], 2) == ['a', 'c'] and bev.sample_evenly([], 3) == []


# ---------- storyboard ----------

def test_storyboard_freshness(tmp_path):
    data = definition()
    for f in data['frames']:
        f['root'] = 'work'
    (tmp_path / 'ending_video.json').write_text('{}')
    jpg, html = bev.storyboard_paths(str(tmp_path))
    assert bev.check_storyboard_fresh(str(tmp_path), data) == []                   # not made: not an error
    os.makedirs(os.path.dirname(jpg))
    for p in (jpg, html):
        Path(p).write_text('x')
    os.utime(tmp_path / 'ending_video.json', (1, 1))
    assert bev.check_storyboard_fresh(str(tmp_path), data) == []
    os.utime(html, (0, 0))
    assert len(bev.check_storyboard_fresh(str(tmp_path), data)) == 1
    (tmp_path / '2019').mkdir()
    Path(tmp_path / '2019' / 'a.jpg').write_text('redrawn')                       # a picture redrawn, same name
    os.utime(html, None)
    os.utime(jpg, (2, 2))
    assert len(bev.check_storyboard_fresh(str(tmp_path), data)) == 1


def test_page_parts():
    assert page.esc('<a href="x">&') == '&lt;a href=&quot;x&quot;&gt;&amp;'
    assert page.mmss(119.9) == '1:59'
    frames = [{'i': 1, 'src': 'a.jpg'}, {'i': 2, 'src': 'a.jpg'}, {'i': 3, 'src': 'v.mp4', 'kind': 'clip',
              'clip_start_sec': 1}, {'i': 4, 'src': 'v.mp4', 'kind': 'clip', 'clip_start_sec': 9}]
    assert page.dup_map(frames) == {1: [2], 2: [1]}
    assert page.ui_for({'page': {'lang': 'ja'}})['copy'] == page.UI['ja']['copy']
    assert page.ui_for({})['copy'] == page.UI['en']['copy']
    assert set(page.UI['en']) == set(page.UI['ja'])
    assert '--config second' in page.command_prefix('W', 'second') and '"W"' in page.command_prefix('W')


def test_page_html_for_photos_only(tmp_path):
    data = definition()
    for k, f in enumerate(data['frames']):
        f.update(root='work', src=f'p{k}.png')
        f.pop('kind', None)
        f.pop('clip_start_sec', None)
        picture(tmp_path / f'p{k}.png', (64, 36))
    data['page'] = {'lang': 'ja', 'title': 'T <b>', 'beat_notes': {'Verse': 'note'}}
    html = page.build_html(str(tmp_path), data, progress=False)
    assert '<title>T &lt;b&gt; 絵コンテ</title>' in html and 'note' in html
    assert html.count('class="card') == 3 and 'data:image/jpeg;base64,' in html
    assert 'the first line of the verse' in html                                  # the pin's reason is shown
    assert '</script>' in html and html.count('</script>') == 1
    # parts of the song are runs of seats: a beat that comes back is a new part; no beat shows as "seats"
    data['frames'][0]['beat'] = 'Verse'
    data['frames'][1]['beat'] = ''
    html = page.build_html(str(tmp_path), data, progress=False)
    assert html.count('<section class="beat"') == 3 and '<h2>コマ</h2>' in html


def test_page_opens_with_the_seats_of_a_correction_sheet_marked(tmp_path):
    data = definition()
    for k, f in enumerate(data['frames']):
        f.update(root='work', src=f'p{k}.png')
        f.pop('kind', None)
        f.pop('clip_start_sec', None)
        picture(tmp_path / f'p{k}.png', (64, 36))
    assert 'const MARK = [];' in page.build_html(str(tmp_path), data, progress=False)
    assert 'const MARK = [1, 3];' in page.build_html(str(tmp_path), data, progress=False, mark=[3, 1])
    with pytest.raises(bev.ConfigError, match='no seat 9'):
        bev.make_storyboard(str(tmp_path), data, mark=[9])
    bev.make_storyboard(str(tmp_path), data, mark=[3, 1])       # through the command's own path (it names a letter `mark`)
    html = Path(bev.storyboard_paths(str(tmp_path))[1]).read_text(encoding='utf-8')
    assert 'const MARK = [1, 3];' in html


# ---------- smoothness ----------

def test_judge_finds_a_staircase_and_passes_even_motion():
    stairs = ([0.1] * 5 + [0.9]) * 20
    even = [0.3 + 0.01 * (k % 3) for k in range(120)]
    assert smooth.judge(stairs)['verdict'] == 'judder' and smooth.judge(stairs)['period'] == 6
    assert smooth.judge(even)['verdict'] == 'ok'
    assert smooth.judge([0.0] * 100)['verdict'] == 'static'
    assert smooth.judge([0.3] * 5)['verdict'] == 'short'


def test_seats_measured_are_the_moving_ones_after_the_prologue():
    data = definition(prologue={'src': 'p.mp4', 'dur': 3.0})
    data['frames'][1]['zoom'] = 1.0
    seats = smooth.seats_of(data)
    assert [s[0] for s in seats] == ['i=1 photo']
    assert seats[0][1] == pytest.approx(3.0 + smooth.MARGIN)


# ---------- the sample ----------

def test_the_sample_definition_is_valid():
    data = json.loads((SAMPLE / 'ending_video.json').read_text(encoding='utf-8'))
    assert bev.validate_config(data) == []
    assert all(f.get('root') == 'work' for f in data['frames'])


# ---------- a real build (ffmpeg) ----------

def make_work(tmp_path):
    work = tmp_path / 'work'
    (work / 'sounds').mkdir(parents=True)
    photos = tmp_path / 'photos' / '2019'
    photos.mkdir(parents=True)
    for k, size in enumerate([(1200, 800), (600, 800), (1280, 720)]):
        picture(photos / f'IMG_2019060{k + 1}_120000.jpg', size)
    subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=9',
                           '-c:a', 'libmp3lame', str(work / 'sounds' / 'song.mp3')])
    subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=6',
                           '-f', 'lavfi', '-i', 'sine=frequency=550:duration=6', '-c:v', 'libx264',
                           '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(photos / 'VID_20190610_090000.mp4')])
    return work, tmp_path / 'photos'


@needs_ffmpeg
def test_build_storyboard_replace_rebuild_and_measure(tmp_path, capsys):
    work, photos = make_work(tmp_path)
    w = str(work)
    assert bev.main([w, '--init', '--audio', 'sounds/song.mp3', '--photos', str(photos), '--seat', '3']) == 0
    assert bev.main([w, '--init', '--audio', 'sounds/song.mp3', '--photos', str(photos)]) == 1   # never overwrites
    data = json.loads((work / 'ending_video.json').read_text(encoding='utf-8'))
    assert len(data['frames']) == 3 and data['photo_root'] == str(photos).replace('\\', '/')
    assert bev.main([w, '--storyboard']) == 0
    assert bev.main([w]) == 0
    out = work / 'videos' / 'ending.mp4'
    info = bev.probe_media(str(out))
    assert info[:2] == (1920, 1080) and info[2] == pytest.approx(9.0, abs=0.1)
    assert bev.measure_loudness(str(out))[0] == pytest.approx(bev.LOUDNESS_TARGET_LUFS, abs=1.0)
    assert bev.main([w, '--check']) == 0
    # point at a seat on the storyboard, replace it with a video, rebuild: only that seat is made again
    capsys.readouterr()
    assert bev.main([w, '--replace', '2=2019/VID_20190610_090000.mp4@1.5']) == 0
    assert bev.main([w, '--check']) == 1                                   # the storyboard is old now
    assert bev.main([w, '--storyboard']) == 0
    capsys.readouterr()
    assert bev.main([w]) == 0
    assert 'segments: 1 made, 2 reused' in capsys.readouterr().out
    assert bev.main([w, '--check']) == 0
    ng, measured, _skipped = smooth.check_work(w)
    assert ng == 0 and measured >= 1
    html = (work / 'ending' / 'storyboard.html').read_text(encoding='utf-8')
    assert html.count('class="card') == 3 and '--replace' in html


@needs_ffmpeg
def test_prologue_and_the_player_size_limit(tmp_path, monkeypatch):
    work, photos = make_work(tmp_path)
    w = str(work)
    assert bev.main([w, '--init', '--audio', 'sounds/song.mp3', '--photos', str(photos), '--seat', '4.5']) == 0
    path = work / 'ending_video.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['prologue'] = {'src': '2019/VID_20190610_090000.mp4', 'dur': 2.0, 'fade_out': 0.5, 'body_fade_in': 0.3}
    path.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setattr(bev, 'MAX_VIDEO_BYTES', 3_000_000)
    monkeypatch.setattr(bev, 'TARGET_VIDEO_BYTES', 2_500_000)
    assert bev.main([w]) == 0
    out = str(work / 'videos' / 'ending.mp4')
    assert os.path.getsize(out) <= 3_000_000
    # Ubuntu's ffmpeg made this 11.13 s (4 frames longer; not investigated), Windows' 11.00 s. The tool warns at 0.5 s
    assert bev.probe_media(out)[2] == pytest.approx(11.0, abs=0.3)
    assert bev.has_audio(out)
