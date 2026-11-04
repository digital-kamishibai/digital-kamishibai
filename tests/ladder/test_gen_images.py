"""Tests for ladder/images/gen_images.py. Gemini is never called: request_image is replaced by a fake."""
import base64
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip('PIL')
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / 'examples' / 'sample-story'
_spec = importlib.util.spec_from_file_location('gen_images', ROOT / 'ladder' / 'images' / 'gen_images.py')
gi = importlib.util.module_from_spec(_spec)
sys.modules['gen_images'] = gi
_spec.loader.exec_module(gi)

KEY = 'test-key-123456789'


def png(size=(2752, 1536), mode='RGBA', alpha=255, color=(40, 90, 160)) -> bytes:
    image = Image.new(mode, size, color + ((alpha,) if mode == 'RGBA' else ()))
    if mode == 'RGB':                                       # a little texture, so the sides are not "plain bands"
        for x in range(0, size[0], 7):
            for y in range(0, size[1], 50):
                image.putpixel((x, y), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


def textured(size=(2752, 1536)) -> bytes:
    image = Image.effect_noise(size, 60).convert('RGBA')
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


PLAN = '''# Plan: T

## Bilder

### [Prompt style]

```text
Watercolour. No letters.
```

### [Prompt 1] Cover
- Asserts: nothing
- Seen:

```text
A lighthouse.
```

### [Prompt 2] Storm
- Asserts: three waves
- Seen:

```
A storm.
### not a heading inside a code block
```

## Slides

1. Cover
'''


@pytest.fixture
def work(tmp_path):
    (tmp_path / 'plan.md').write_text(PLAN, encoding='utf-8')
    (tmp_path / 'pictures').mkdir()
    return tmp_path


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def request_image(key, model, body, retries=3):
        calls.append({'key': key, 'model': model, 'body': body})
        return textured()
    monkeypatch.setattr(gi, 'request_image', request_image)
    monkeypatch.setenv(gi.KEY_ENV, KEY)
    return calls


# ---------- the plan ----------

def test_reads_style_prompts_and_asserts():
    p = gi.parse_plan(PLAN)
    assert p.errors == []
    assert p.style == 'Watercolour. No letters.'
    assert p.slides == {1: 'A lighthouse.', 2: 'A storm.\n### not a heading inside a code block'}
    assert p.asserts == {1: 'nothing', 2: 'three waves'}
    assert gi.full_prompt(p, 1) == 'Watercolour. No letters.\n\nA lighthouse.'


def test_sample_plan_has_a_prompt_for_every_slide():
    p = gi.parse_plan((SAMPLE / 'plan.md').read_text(encoding='utf-8'))
    assert p.errors == []
    assert sorted(p.slides) == [1, 2, 3] and p.style


def test_crlf():
    assert gi.parse_plan(PLAN.replace('\n', '\r\n')).slides[1] == 'A lighthouse.'


@pytest.mark.parametrize('text, message', [
    ('### [プロンプト 1]\n```\nx\n```\n', 'no "### [Prompt N]"'),
    ('### [prompt 1]\n```\nx\n```\n', 'looks like a prompt heading'),
    ('### [Prompt 1]\n\nno code block\n', 'has no prompt'),
    ('### [Prompt 1]\n```\nx\n```\n### [Prompt 1]\n```\ny\n```\n', 'a second [Prompt 1]'),
    ('### [Prompt 0]\n```\nx\n```\n', 'start at 1'),
    ('### [Prompt 1]\n```\nx\n', 'not closed'),
])
def test_plan_errors(text, message):
    assert message in ' | '.join(gi.parse_plan(text).errors)


def test_a_heading_after_the_prompt_ends_it():
    p = gi.parse_plan('### [Prompt 1]\n```\nx\n```\n## Slides\n```\nnot a prompt\n```\n')
    assert p.slides == {1: 'x'}


def test_slide_numbers_and_ranges():
    assert gi.parse_numbers(['2', '5-7', '6']) == [2, 5, 6, 7]
    with pytest.raises(ValueError):
        gi.parse_numbers(['7-5'])
    with pytest.raises(ValueError):
        gi.parse_numbers(['two'])


# ---------- one picture ----------

def test_opaque_picture_becomes_rgb_and_at_most_1920():
    image = gi.tidy(png(alpha=255))
    assert image.mode == 'RGB'
    assert image.size == (1920, 1072)


def test_transparent_picture_keeps_its_alpha():
    assert gi.tidy(png(size=(800, 450), alpha=128)).mode == 'RGBA'


def test_small_picture_is_not_enlarged():
    assert gi.tidy(png(size=(1376, 768))).size == (1376, 768)


def test_tall_picture_in_the_middle_is_warned():
    image = Image.new('RGB', (1920, 1080), (250, 250, 250))
    image.paste(Image.effect_noise((600, 1080), 80).convert('RGB'), (660, 0))
    warnings = gi.picture_warnings(image)
    assert any('bands at the sides' in w for w in warnings)


def test_full_frame_picture_is_not_warned():
    assert gi.picture_warnings(gi.tidy(textured())) == []


def test_not_16_9_is_warned():
    assert any('not 16:9' in w for w in gi.picture_warnings(gi.tidy(textured((1024, 1024)))))


def test_request_body_attaches_the_style_picture(tmp_path):
    anchor = tmp_path / '01.png'
    anchor.write_bytes(png(size=(16, 9)))
    body = gi.request_body('A storm.', anchor)
    parts = body['contents'][0]['parts']
    assert parts[0]['inline_data']['mime_type'] == 'image/png'
    assert base64.b64decode(parts[0]['inline_data']['data']) == anchor.read_bytes()
    assert parts[-1] == {'text': 'A storm.'}
    assert body['generationConfig']['imageConfig'] == {'aspectRatio': '16:9', 'imageSize': '2K'}
    assert gi.request_body('A storm.', None)['contents'][0]['parts'] == [{'text': 'A storm.'}]


# ---------- runs ----------

def test_makes_missing_pictures_style_first(work, fake, capsys):
    assert gi.main([str(work)]) == 0
    assert (work / 'pictures' / '01.png').is_file() and (work / 'pictures' / '02.png').is_file()
    assert [c['body']['contents'][0]['parts'][-1]['text'] for c in fake] == [
        'Watercolour. No letters.\n\nA lighthouse.',
        'Watercolour. No letters.\n\nA storm.\n### not a heading inside a code block']
    assert len(fake[0]['body']['contents'][0]['parts']) == 1          # the first one sets the style
    assert 'inline_data' in fake[1]['body']['contents'][0]['parts'][0]  # the second follows it
    out = capsys.readouterr().out
    assert 'US$0.27' in out and 'slide 2: three waves' in out
    assert KEY not in out


def test_existing_pictures_are_skipped_or_get_candidates(work, fake, capsys):
    original = png(size=(64, 36), mode='RGB')
    (work / 'pictures' / '01.jpg').write_bytes(original)
    assert gi.main([str(work)]) == 0
    assert len(fake) == 1                                    # only slide 2
    assert 'slide 1: has a picture; skipped' in capsys.readouterr().out
    assert gi.main([str(work), '1']) == 0
    assert gi.main([str(work), '1']) == 0
    assert (work / 'pictures' / '01.jpg').read_bytes() == original   # never overwritten
    assert sorted(p.name for p in (work / 'pictures' / '_candidates').iterdir()) == ['01-1.png', '01-2.png']
    assert '--use N' in capsys.readouterr().out


def test_use_takes_a_candidate_and_keeps_the_old_picture(work, fake):
    original = png(size=(64, 36), mode='RGB')
    (work / 'pictures' / '01.jpg').write_bytes(original)
    gi.main([str(work), '1'])
    gi.main([str(work), '1'])
    second = (work / 'pictures' / '_candidates' / '01-2.png').read_bytes()
    assert gi.main([str(work), '--use', '1']) == 0                    # the newest
    assert (work / 'pictures' / '01.png').read_bytes() == second
    assert not (work / 'pictures' / '01.jpg').exists()
    replaced = list((work / 'pictures' / '_replaced').iterdir())
    assert len(replaced) == 1 and replaced[0].read_bytes() == original
    assert gi.main([str(work), '--use', '1-1']) == 0                  # a named one; the previous goes too
    assert len(list((work / 'pictures' / '_replaced').iterdir())) == 2
    assert gi.main([str(work), '--use', '1-9']) == 1
    assert gi.main([str(work), '--use', '2']) == 1


def test_use_names_the_ending_video_seats_that_still_show_the_old_picture(work, fake, capsys):
    # Issue #7: the ending video kept the old picture and nothing said so
    (work / 'pictures' / '01.jpg').write_bytes(png(size=(64, 36), mode='RGB'))
    frames = [{'i': 1, 'at': 0, 'dur': 5, 'src': 'pictures/02.jpg'}, {'i': 2, 'at': 5, 'dur': 5, 'src': 'pictures/01.jpg'},
              {'i': 3, 'at': 10, 'dur': 5, 'src': 'pictures/01.jpg', 'kind': 'final'}]
    first = json.dumps({'output': 'e.mp4', 'frames': frames})
    (work / 'ending_video.json').write_text(first, encoding='utf-8')
    second = json.dumps({'output': 'f.mp4', 'photo_root': 'D:/Photos', 'frames': [
        {'i': 1, 'at': 0, 'dur': 5, 'src': 'pictures/01.jpg'},                    # in the photo folder: another picture
        {'i': 2, 'at': 5, 'dur': 5, 'src': 'pictures/01.jpg', 'root': 'work'}]})
    (work / 'ending_video_second.json').write_text(second, encoding='utf-8')
    (work / 'ending_video_broken.json').write_text('{', encoding='utf-8')
    gi.main([str(work), '1'])
    capsys.readouterr()
    assert gi.main([str(work), '--use', '1']) == 0
    out = capsys.readouterr().out
    notes = [line for line in out.splitlines() if line.startswith('note: seat')]
    assert len(notes) == 3, out
    assert 'seat 2 of the ending video (ending_video.json)' in notes[0] and '--replace 2=pictures/01.png' in notes[0]
    assert 'seat 3 of the ending video (ending_video.json)' in notes[1]
    assert '(ending_video_second.json)' in notes[2] and '--config second --replace 2=pictures/01.png' in notes[2]
    assert (work / 'ending_video.json').read_text(encoding='utf-8') == first, "the ending video is the maker's: never changed"


def test_use_without_an_ending_video_says_nothing_more(work, fake, capsys):
    (work / 'pictures' / '01.jpg').write_bytes(png(size=(64, 36), mode='RGB'))
    gi.main([str(work), '1'])
    capsys.readouterr()
    assert gi.main([str(work), '--use', '1']) == 0
    assert 'note:' not in capsys.readouterr().out


def test_no_key(work, monkeypatch, capsys):
    monkeypatch.delenv(gi.KEY_ENV, raising=False)
    assert gi.main([str(work)]) == 1
    err = capsys.readouterr().err
    assert gi.KEY_ENV in err and 'paid' in err


def test_dry_run_needs_no_key_and_writes_nothing(work, monkeypatch, capsys):
    monkeypatch.delenv(gi.KEY_ENV, raising=False)
    assert gi.main([str(work), '--dry-run']) == 0
    out = capsys.readouterr().out
    assert 'nothing sent' in out and 'A lighthouse.' in out and 'US$' in out
    assert list((work / 'pictures').iterdir()) == []


def test_a_failure_does_not_print_the_key_or_stop_the_others(work, monkeypatch, capsys):
    monkeypatch.setenv(gi.KEY_ENV, KEY)

    def request_image(key, model, body, retries=3):
        if 'A lighthouse.' in body['contents'][0]['parts'][-1]['text']:
            raise RuntimeError(f'HTTP 400: bad request for {key}')
        return textured()
    monkeypatch.setattr(gi, 'request_image', request_image)
    assert gi.main([str(work)]) == 1
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    assert '***' in captured.err
    assert (work / 'pictures' / '02.png').is_file()


def test_unknown_slide_and_missing_plan(work, fake, tmp_path, capsys):
    assert gi.main([str(work), '9']) == 1
    assert 'no [Prompt N] for slide 9' in capsys.readouterr().err
    assert gi.main([str(tmp_path / 'nowhere')]) == 1


def test_request_image_reads_the_answer_and_sends_the_key_in_a_header(monkeypatch):
    seen = {}

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            data = base64.b64encode(b'PICTURE').decode('ascii')
            return json.dumps({'candidates': [{'content': {'parts': [{'inlineData': {'data': data}}]}}]}).encode()

    def urlopen(req, timeout):
        seen['url'] = req.full_url
        seen['key'] = req.get_header('X-goog-api-key')
        return Answer()
    monkeypatch.setattr(gi.urllib.request, 'urlopen', urlopen)
    assert gi.request_image(KEY, 'm', {'contents': []}) == b'PICTURE'
    assert seen['key'] == KEY and KEY not in seen['url'] and '/models/m:generateContent' in seen['url']
