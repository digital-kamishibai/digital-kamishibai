import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { validateWork, fileMap, findWorkJson, resolvePictures, resolveVideos, resolveAudio, resolveBases, resolveCandidates, resolveLinks, uniqueById, seatAt, toSource, dirEntries, workDirOf } from '../../player/js/work.js';

const sample = JSON.parse(readFileSync(new URL('../../examples/sample-story/work.json', import.meta.url), 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

test('見本作品は検査を通る', () => {
  const { work, errors } = validateWork(sample);
  assert.deepEqual(errors, []);
  assert.equal(work.slides.length, 4);
});

test('形式・版が違えば止める', () => {
  const w = clone(sample); w.version = 2;
  assert.match(validateWork(w).errors.join(), /unsupported version/);
  const x = clone(sample); x.format = 'other';
  assert.match(validateWork(x).errors.join(), /format/);
});

test('枚の番号は 1..N', () => {
  const w = clone(sample); w.slides[1].number = 5;
  assert.match(validateWork(w).errors.join(), /slide 2: number must be 2/);
});

test('枚が無い作品は止める', () => {
  const w = clone(sample); w.slides = [];
  assert.match(validateWork(w).errors.join(), /at least one slide/);
});

test('絵が null でよいのは動画のある枚だけ', () => {
  const w = clone(sample); w.slides[0].picture = null;
  assert.match(validateWork(w).errors.join(), /only on a slide with a video/);
  w.slides[0].cues = [{ type: 'video', file: 'videos/a.mp4' }];
  assert.deepEqual(validateWork(w).errors, []);
});

test('HEIC は受け付けない', () => {
  const w = clone(sample); w.slides[0].picture = 'pictures/01.HEIC';
  assert.match(validateWork(w).errors.join(), /HEIC/);
});

test('知らない合図は止める', () => {
  const w = clone(sample); w.slides[0].cues = [{ type: 'bmg', file: 'a.mp3' }];
  assert.match(validateWork(w).errors.join(), /unknown cue type/);
});

test('work.json の場所が基準フォルダになる（浅いものを優先）', () => {
  assert.deepEqual(findWorkJson(['story/pictures/01.jpg', 'story/old/work.json', 'story/work.json']), { path: 'story/work.json', base: 'story' });
  assert.deepEqual(findWorkJson(['work.json']), { path: 'work.json', base: '' });
  assert.equal(findWorkJson(['a.jpg']), null);
});

test('基準フォルダからの相対パスで引ける', () => {
  const m = fileMap([{ path: 'story/pictures/01.jpg', file: 'F1' }, { path: 'other/x.jpg', file: 'X' }], 'story');
  assert.deepEqual([...m.keys()], ['pictures/01.jpg']);
});

test('絵の拡張子が違っても同じ名前なら結びつく（§2.5）・無いものは名前で返す', () => {
  const w = clone(sample);
  w.slides.push({ number: 4, title: '', picture: 'pictures/04.jpg', notes: '', cues: [] });
  const media = new Map([['pictures/01.png', 'P1'], ['pictures/02.png', 'P2'], ['pictures/03.png', 'P3']]);
  const { pictures, missing } = resolvePictures(w, [media]);
  assert.equal(pictures.get(1).key, 'pictures/01.png'); // 01.jpg と書いてあっても 01.png を使う
  assert.equal(pictures.get(1).mime, 'image/png');
  assert.deepEqual(missing, ['pictures/04.jpg']);
});

test('先に渡した表（zip の中）を優先する', () => {
  const a = new Map([['pictures/01.jpg', 'ZIP']]);
  const b = new Map([['pictures/01.jpg', 'FOLDER']]);
  const one = { ...clone(sample), slides: [clone(sample).slides[0]] };
  assert.equal(resolvePictures(one, [a, b]).pictures.get(1).file, 'ZIP');
});

test('組み立ての元の絵（picture_source）: 絵の件の見分けに使うファイルを結びつける・形が違えば止める（Issue #5）', () => {
  const w = { ...clone(sample), slides: [{ ...clone(sample).slides[0], picture: 'pictures/_built/01.jpg', picture_source: 'pictures/01.png' }] };
  assert.deepEqual(validateWork(w).errors, []);
  const media = new Map([['pictures/_built/01.jpg', 'BUILT'], ['pictures/01.png', 'SRC']]);
  const p = resolvePictures(w, [media]).pictures.get(1);
  assert.equal(p.file, 'BUILT', '映すのは組み立てた絵');
  assert.deepEqual(p.source, { key: 'pictures/01.png', file: 'SRC' });
  assert.equal(resolvePictures(w, [new Map([['pictures/_built/01.jpg', 'BUILT']])]).pictures.get(1).source, undefined, '元の絵が手元に無い');
  for (const bad of ['', 3]) {
    const b = clone(w); b.slides[0].picture_source = bad;
    assert.match(validateWork(b).errors.join(), /picture_source/);
  }
});

// ---------- 動画（段階2） ----------

test('動画キーは、パスそのままで手元のファイルに結びつく。無ければ名前で出す', () => {
  const w = {
    slides: [
      { number: 1, cues: [] },
      { number: 2, cues: [{ type: 'video', file: 'videos/a.mp4' }, { type: 'sound', file: 's.mp3' }] },
      { number: 3, cues: [{ type: 'video', file: 'videos/missing.mp4' }] },
    ],
  };
  const file = { size: 123 };
  const r = resolveVideos(w, [new Map(), new Map([['videos/a.mp4', file]])]);
  assert.deepEqual(r.videos, [{ n: 2, k: 1, key: 'videos/a.mp4', file, size: 123, mime: 'video/mp4' }]);
  assert.deepEqual(r.missing, ['videos/missing.mp4']);
});

// ---------- 音（段階4） ----------

test('BGM・効果音の素材は、同じファイルを1つにまとめて結びつく', () => {
  const w = { slides: [
    { number: 1, cues: [{ type: 'bgm', file: 'sounds/a.mp3', loop: false }, { type: 'sound', file: 'sounds/s.m4a' }] },
    { number: 2, cues: [{ type: 'sound', file: 'sounds/s.m4a' }, { type: 'bgm', file: 'sounds/none.mp3' }, { type: 'video', file: 'v.mp4' }] },
  ] };
  const a = { size: 1 }, b = { size: 2 };
  const r = resolveAudio(w, [new Map([['sounds/a.mp3', a], ['sounds/s.m4a', b]])]);
  assert.deepEqual(r.audio.map((x) => [x.key, x.mime]), [['sounds/a.mp3', 'audio/mpeg'], ['sounds/s.m4a', 'audio/mp4']]);
  assert.deepEqual(r.missing, ['sounds/none.mp3']);
});

test('bgm の loop は true／false だけ', () => {
  const w = clone(sample);
  w.slides[0].cues = [{ type: 'bgm', file: 'x.mp3', loop: 'no' }];
  assert.ok(validateWork(w).errors.some((e) => e.includes('loop')));
  w.slides[0].cues = [{ type: 'bgm', file: 'x.mp3', loop: false }];
  assert.deepEqual(validateWork(w).errors, []);
});

test('bgm の start は "after-video" だけ・その枚に動画が要る', () => {
  const w = clone(sample);
  w.slides[0].cues = [{ type: 'bgm', file: 'x.mp3', loop: false, start: 'later' }, { type: 'video', file: 'v.mp4' }];
  assert.ok(validateWork(w).errors.some((e) => e.includes('start')));
  w.slides[0].cues = [{ type: 'bgm', file: 'x.mp3', loop: false, start: 'after-video' }];
  assert.ok(validateWork(w).errors.some((e) => e.includes('needs a video')));
  w.slides[0].cues = [{ type: 'bgm', file: 'x.mp3', loop: false, start: 'after-video' }, { type: 'video', file: 'v.mp4' }];
  assert.deepEqual(validateWork(w).errors, []);
});

test('同じ動画を2つの枚で使うと、枚ごとの一覧には2回出るが、配る一覧は1本にまとめる（2回送って上書きしない）', () => {
  const w = {
    format: 'digital-kamishibai/work', version: 1, title: 'T', language: 'en',
    slides: [
      { number: 1, title: 'a', picture: 'pictures/01.jpg', notes: '', cues: [{ type: 'video', file: 'videos/x.mp4' }] },
      { number: 2, title: 'b', picture: 'pictures/02.jpg', notes: '', cues: [{ type: 'video', file: 'videos/x.mp4' }, { type: 'video', file: 'videos/gone.mp4' }] },
      { number: 3, title: 'c', picture: 'pictures/03.jpg', notes: '', cues: [{ type: 'video', file: 'videos/gone.mp4' }] },
    ],
  };
  const r = resolveVideos(w, [new Map([['videos/x.mp4', { size: 5 }]])]);
  assert.deepEqual(r.videos.map((v) => v.n), [1, 2]);
  assert.deepEqual(r.missing, ['videos/gone.mp4']); // 見つからないものも1回だけ挙げる
  const items = [{ id: 'm', n: 1 }, { id: 'v', n: 1 }, { id: 'v', n: 2 }, { id: 'w', n: 2 }];
  assert.deepEqual(uniqueById(items).map((x) => `${x.id}${x.n}`), ['m1', 'v1', 'w2']);
});

// ---------- 画面の文字・練習用の版（修正票。work-format §3.1・§3.2） ----------

test('overlays と draft は無くても、正しい形なら有っても通る', () => {
  assert.equal(sample.draft, undefined);
  assert.ok(sample.slides.every((s) => s.overlays === undefined));
  const w = clone(sample);
  w.draft = true;
  w.slides[0].overlays = [[['行1', '行2'], ['段落2']], [['枠2の文']]];
  w.slides[1].overlays = [[['上'], [''], ['下']]]; // 空の段落は残す
  w.slides[2].overlays = []; // 文字のある枠が無い枚
  assert.deepEqual(validateWork(w).errors, []);
});

test('overlays の形が違えば止める', () => {
  for (const bad of ['文字', ['文字'], [['文字']], [[]], [[[]]], [[[1]]], [null], [[['a'], 'b']]]) {
    const w = clone(sample); w.slides[0].overlays = bad;
    assert.match(validateWork(w).errors.join(), /slide 1: overlays must be/, JSON.stringify(bad));
  }
});

test('draft は true だけ（false も書かない）', () => {
  for (const bad of [false, 'true', 1, null]) {
    const w = clone(sample); w.draft = bad;
    assert.match(validateWork(w).errors.join(), /draft must be true/, JSON.stringify(bad));
  }
});

// ---------- 画面の文字の置き場所（絵の上で直す。work-format §3.1・§3.2） ----------

const para = (o = {}) => ({ align: 'center', space_before: 0, size: 30, bold: true, color: '#2A2A3A', font: 'Meiryo', ...o });
const box = (o = {}) => ({ x: 457200, y: 164592, width: 11247120, height: 685800, inset: [91440, 45720, 91440, 45720], anchor: 'top', wrap: true, paragraphs: [para()], ...o });
function withLayout() {
  const w = clone(sample);
  w.draft = true;
  w.slide_size = { width: 12192000, height: 6858000 };
  w.slides[0].overlays = [[['見出し']], [['1. 一つ目', '続き'], ['2. 二つ目']]];
  w.slides[0].overlay_base = 'overlay_base/01.jpg';
  w.slides[0].overlay_layout = [box(), box({ shape: 'roundRect', corner: 0.1, fill: '#FAF7F0', outline: { color: '#B08A3E', width: 19050 }, rotation: -3.5, anchor: 'middle', paragraphs: [para({ align: 'left' }), para({ align: 'left', space_before: 14 })] })];
  return w;
}

test('overlay_layout は無くても、正しい形なら有っても通る', () => {
  assert.ok(sample.slides.every((s) => s.overlay_layout === undefined));
  assert.deepEqual(validateWork(withLayout()).errors, []);
});

test('overlay_layout には slide_size・overlays・overlay_base が要る', () => {
  const a = withLayout(); delete a.slide_size;
  assert.match(validateWork(a).errors.join(), /slide_size must be/);
  const b = withLayout(); delete b.slides[0].overlays;
  assert.match(validateWork(b).errors.join(), /slide 1: overlay_layout needs overlays/);
  const c = withLayout(); delete c.slides[0].overlay_base;
  assert.match(validateWork(c).errors.join(), /slide 1: overlay_layout needs overlay_base/);
});

test('overlay_layout の数・段落の数が overlays と違えば止める', () => {
  const a = withLayout(); a.slides[0].overlay_layout.pop();
  assert.match(validateWork(a).errors.join(), /one entry per box of overlays \(2\)/);
  const b = withLayout(); b.slides[0].overlay_layout[1].paragraphs.pop();
  assert.match(validateWork(b).errors.join(), /box 2: paragraphs must have one entry per paragraph of overlays \(2\)/);
});

test('overlay_layout の値の形が違えば止める（受け継ぐ値も書き出してあること）', () => {
  const cases = [
    [{ x: 1.5 }, /x, y, width, height/], [{ width: 0 }, /x, y, width, height/],
    [{ inset: [0, 0, 0] }, /inset/], [{ anchor: 'center' }, /anchor/], [{ wrap: 'yes' }, /wrap/],
    [{ shape: 'ellipse' }, /shape/], [{ shape: 'roundRect' }, /corner/], [{ fill: 'red' }, /fill/],
    [{ outline: { color: '#000000' } }, /outline/], [{ rotation: '90' }, /rotation/],
    [{ paragraphs: [para({ color: undefined })] }, /paragraph 1 needs/], [{ paragraphs: [para({ align: 'justify' })] }, /paragraph 1 needs/],
    [{ paragraphs: [para({ font: '' })] }, /paragraph 1 needs/],
  ];
  for (const [patch, re] of cases) {
    const w = withLayout(); Object.assign(w.slides[0].overlay_layout[0], patch);
    assert.match(validateWork(w).errors.join(), re, JSON.stringify(patch));
  }
});

test('下敷き（overlay_base）は置き場所のある枚だけ結びつける・拡張子を読み替える・見つからなくても足りない素材に数えない', () => {
  const w = withLayout();
  w.slides[1].overlay_base = 'overlay_base/02.jpg';           // overlay_layout の無い枚は結びつけない
  const media = new Map([['overlay_base/01.png', 'B1'], ['overlay_base/02.jpg', 'B2']]);
  const bases = resolveBases(w, [media]);
  assert.deepEqual([...bases.keys()], [1]);
  assert.equal(bases.get(1).key, 'overlay_base/01.png');
  assert.equal(bases.get(1).mime, 'image/png');
  assert.equal(resolveBases(w, [new Map()]).size, 0);
  // 下敷きが無くても、絵の足りない素材には出てこない
  assert.ok(!resolvePictures(w, [new Map()]).missing.includes('overlay_base/01.jpg'));
});

// ---------- 動画の情報（role・seats・source_segments。work-format §3.3） ----------

const ending = () => ({
  type: 'video', file: 'videos/ending.mp4', role: 'ending',
  seats: [
    { n: 1, from: 2, to: 8, label: 'pictures/02.png' },
    { n: 2, from: 8, to: 14, label: 'pictures/03.png' },
    { n: 3, from: 14, to: 20, label: 'pictures/01.jpg', pin: 'the title at the end of the song' },
  ],
});
const withCue = (cue) => { const w = clone(sample); w.slides[2].cues = [cue]; return w; };

test('動画の情報は無くても、正しい形なら有っても通る', () => {
  assert.deepEqual(validateWork(withCue({ type: 'video', file: 'videos/a.mp4' })).errors, []);
  assert.deepEqual(validateWork(withCue(ending())).errors, []);
  assert.deepEqual(validateWork(withCue({ type: 'video', file: 'videos/e.mp4', role: 'ending' })).errors, [], '編集アプリで作ったエンディング動画には席が無い');
  assert.deepEqual(validateWork(withCue({ type: 'video', file: 'videos/a.mp4', source_segments: [{ start: 82, dur: 74 }, { start: 278, dur: 105 }] })).errors, []);
});

test('リンクの動画: YouTube のリンクと、開始・止める秒（work-format §2.4・§3.3）', () => {
  const ok = { type: 'video', url: 'https://www.youtube.com/watch?v=8KkKuTCFvzI', start: 351, end: 369 };
  assert.deepEqual(validateWork(withCue(ok)).errors, []);
  assert.deepEqual(validateWork(withCue({ type: 'video', url: 'https://youtu.be/8KkKuTCFvzI' })).errors, [], '範囲は無くてもよい');
  assert.deepEqual(validateWork(withCue({ type: 'video', url: 'https://youtu.be/8KkKuTCFvzI', start: 45.5 })).errors, []);
  const bad = (cue, re) => assert.match(validateWork(withCue(cue)).errors.join(), re, JSON.stringify(cue));
  bad({ type: 'video', url: 'https://vimeo.com/1234' }, /must be a YouTube link/);
  bad({ type: 'video', url: 'videos/a.mp4' }, /must be a YouTube link/);
  bad({ ...ok, file: 'videos/a.mp4' }, /a file or a url, not both/);
  bad({ ...ok, start: -1 }, /start must be seconds/);
  bad({ ...ok, start: '5:51' }, /start must be seconds/);
  bad({ ...ok, end: 300 }, /end must be seconds after start/);
  bad({ type: 'video', url: ok.url, end: 0 }, /end must be seconds after start/);
  assert.deepEqual(validateWork(withCue({ ...ok, captions: 'ja' })).errors, []);
  assert.deepEqual(validateWork(withCue({ ...ok, captions: 'pt-BR' })).errors, []);
  bad({ ...ok, captions: 'Japanese!' }, /captions must be a language code/);
  bad({ ...ok, captions: true }, /captions must be a language code/);
  assert.deepEqual(validateWork(withCue({ ...ok, volume: -6 })).errors, []);
  assert.deepEqual(validateWork(withCue({ ...ok, volume: -40 })).errors, []);
  bad({ ...ok, volume: 3 }, /volume must be dB from -40 to 0/);
  bad({ ...ok, volume: -41 }, /volume must be dB from -40 to 0/);
  bad({ ...ok, volume: '-6dB' }, /volume must be dB from -40 to 0/);
  bad({ ...ok, role: 'ending' }, /no role, seats or source_segments/);
  bad({ ...ok, source_segments: [{ start: 0, dur: 1 }] }, /no role, seats or source_segments/);
});

test('リンクの動画は手元のファイルに結びつけない・足りない素材に数えない・何本目かはファイルの動画と通しで数える', () => {
  const w = clone(sample);
  w.slides[1].cues = [{ type: 'video', file: 'videos/a.mp4' }, { type: 'video', url: 'https://youtu.be/8KkKuTCFvzI', start: 351, end: 369 }];
  w.slides[2].picture = null;
  w.slides[2].cues = [{ type: 'video', url: 'https://www.youtube.com/watch?v=dCVlRFWOjgE', volume: -6 }];
  w.slides[3].cues = []; w.slides[3].picture = 'pictures/04.jpg'; // 見本のエンディング動画は外す
  assert.deepEqual(validateWork(w).errors, [], '絵の無い枚でも、リンクの動画があればよい');
  const rv = resolveVideos(w, [new Map([['videos/a.mp4', { size: 5 }]])]);
  assert.deepEqual(rv.missing, []);
  assert.deepEqual(rv.videos.map((v) => [v.n, v.k, v.key]), [[2, 1, 'videos/a.mp4']]);
  assert.deepEqual(resolveLinks(w), [
    { id: 'link-2-2', kind: 'link', n: 2, k: 2, key: 'https://youtu.be/8KkKuTCFvzI', yt: '8KkKuTCFvzI', start: 351, end: 369, captions: null, volume: 0 },
    { id: 'link-3-1', kind: 'link', n: 3, k: 1, key: 'https://www.youtube.com/watch?v=dCVlRFWOjgE', yt: 'dCVlRFWOjgE', start: 0, end: null, captions: null, volume: -6 },
  ]);
  assert.deepEqual(resolveLinks(sample), []);
});

test('role は ending だけ・seats は ending だけ・source_segments は role の無い動画だけ', () => {
  assert.match(validateWork(withCue({ type: 'video', file: 'v.mp4', role: 'opening' })).errors.join(), /role must be "ending"/);
  const noRole = ending(); delete noRole.role;
  assert.match(validateWork(withCue(noRole)).errors.join(), /seats need role "ending"/);
  assert.match(validateWork(withCue({ ...ending(), source_segments: [{ start: 0, dur: 1 }] })).errors.join(), /only for a video without role/);
});

test('席は 1, 2, 3 … の順・from < to・前の席が終わる前に始まらない', () => {
  const skip = ending(); skip.seats[2].n = 4;
  assert.match(validateWork(withCue(skip)).errors.join(), /seat 3: n must be 3/);
  const back = ending(); back.seats[1].to = 8;
  assert.match(validateWork(withCue(back)).errors.join(), /seat 2: needs seconds from < to/);
  const overlap = ending(); overlap.seats[1].from = 7.5;
  assert.match(validateWork(withCue(overlap)).errors.join(), /seat 2: starts before seat 1 ends/);
  const pin = ending(); pin.seats[0].pin = '';
  assert.match(validateWork(withCue(pin)).errors.join(), /pin must be the reason/);
  const gap = ending(); gap.seats[1].from = 9;
  assert.deepEqual(validateWork(withCue(gap)).errors, [], '席の間のすき間はよい');
});

test('source_segments は空でなく、start >= 0・dur > 0', () => {
  assert.match(validateWork(withCue({ type: 'video', file: 'v.mp4', source_segments: [] })).errors.join(), /non-empty list/);
  assert.match(validateWork(withCue({ type: 'video', file: 'v.mp4', source_segments: [{ start: 3, dur: 0 }] })).errors.join(), /source segment 1/);
});

test('一時停止の位置から席を引く: プロローグの手前・境目は後ろの席・最後の席・エピローグ', () => {
  const { seats } = ending();
  assert.equal(seatAt(seats, 1.9), null);
  assert.equal(seatAt(seats, 2).n, 1);
  assert.equal(seatAt(seats, 8).n, 2);
  assert.equal(seatAt(seats, 19.99).n, 3);
  assert.equal(seatAt(seats, 20), null);
  assert.equal(seatAt(undefined, 3), null);
});

test('切り出した動画の秒を元の動画の秒に直す: 区間1つ・2つ・境目・範囲の外', () => {
  assert.deepEqual(toSource([{ start: 40, dur: 343 }], 12.5), { segment: 1, at: 52.5 });
  const two = [{ start: 82, dur: 74 }, { start: 278, dur: 105 }];
  assert.deepEqual(toSource(two, 10), { segment: 1, at: 92 });
  assert.deepEqual(toSource(two, 74), { segment: 2, at: 278 });
  assert.deepEqual(toSource(two, 179), { segment: 2, at: 383 });
  assert.equal(toSource(two, 179.5), null);
  assert.equal(toSource(two, -1), null);
  assert.equal(toSource(undefined, 3), null);
  // 終わりの位置（修正票の To）: 境目ちょうどは前の区間の終わり。境目でなければ同じ
  assert.deepEqual(toSource(two, 74, true), { segment: 1, at: 156 });
  assert.deepEqual(toSource(two, 179, true), { segment: 2, at: 383 });
  assert.deepEqual(toSource(two, 100, true), toSource(two, 100));
  assert.deepEqual(toSource(two, 0, true), { segment: 1, at: 82 }, '頭は前の区間が無い');
});

test('絵の候補: pictures/_candidates/NN-K を新しい K から・ほかの枚や名前の違うものは入れない・前の maps が勝つ', () => {
  const f = (name) => ({ name });
  const work = new Map([
    ['pictures/_candidates/05-1.png', f('a')], ['pictures/_candidates/05-3.PNG', f('b')], ['pictures/_candidates/05-2.jpg', f('c')],
    ['pictures/_candidates/06-1.png', f('d')], ['pictures/_candidates/05-x.png', f('e')], ['pictures/05.png', f('g')],
    ['pictures/_replaced/05-20261029-134733.png', f('h')], ['pictures/_candidates/5-1.png', f('i')],
  ]);
  const media = new Map([['pictures/_candidates/05-1.png', f('m')], ['pictures/_candidates/05-4.webp', f('n')]]);
  const list = resolveCandidates(5, [work, media]);
  assert.deepEqual(list.map((c) => [c.k, c.key, c.file.name]), [
    [4, 'pictures/_candidates/05-4.webp', 'n'], [3, 'pictures/_candidates/05-3.PNG', 'b'],
    [2, 'pictures/_candidates/05-2.jpg', 'c'], [1, 'pictures/_candidates/05-1.png', 'a'],
  ]);
  assert.deepEqual(list.map((c) => c.mime), ['image/webp', 'image/png', 'image/jpeg', 'image/png']);
  assert.deepEqual(resolveCandidates(12, [work]), []);
  assert.deepEqual(resolveCandidates(6, [work]).map((c) => c.key), ['pictures/_candidates/06-1.png']);
});

// showDirectoryPicker の代わり（フォルダ＝{ 名前: 中身 }、ファイル＝文字列）
const fakeDir = (name, tree) => ({
  kind: 'directory', name,
  async *entries() {
    for (const [k, v] of Object.entries(tree)) {
      yield [k, typeof v === 'string' ? { kind: 'file', name: k, getFile: async () => ({ name: k, text: async () => v }) } : fakeDir(k, v)];
    }
  },
  async getDirectoryHandle(k) { if (typeof tree[k] !== 'object') throw new Error('NotFound'); return fakeDir(k, tree[k]); },
});

test('選んだフォルダの中身は webkitdirectory と同じ形のパスになる', async () => {
  const d = fakeDir('works', { a: { 'work.json': '{}', pictures: { '01.png': 'x' } } });
  const entries = await dirEntries(d);
  assert.deepEqual(entries.map((x) => x.path).sort(), ['works/a/pictures/01.png', 'works/a/work.json']);
  const found = findWorkJson(entries.map((x) => x.path));
  assert.equal(found.base, 'works/a');
  assert.equal((await workDirOf(d, found.base)).name, 'a', '親を選んでも、修正票の保存先は work.json のあるフォルダ');
  assert.equal((await workDirOf(d, 'works')).name, 'works');
});
