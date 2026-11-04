import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bgmAt, soundsAt, createAudio, start, retune, cutForVideo, afterVideo, astate, bgmPosition, talkStep, TALK_ON_MS, TALK_OFF_MS } from '../../player/js/audio.js';

// 実際の作品の書き出しと同じ並び（BGM は S1・S3・S5、停止は S7）
const w = {
  slides: [
    { number: 1, cues: [{ type: 'bgm', file: 'b1', loop: false }, { type: 'sound', file: 's1' }] },
    { number: 2, cues: [] },
    { number: 3, cues: [{ type: 'bgm', file: 'b3', loop: false }] },
    { number: 4, cues: [] },
    { number: 5, cues: [{ type: 'bgm', file: 'b5' }] },
    { number: 6, cues: [{ type: 'sound', file: 's6' }, { type: 'sound', file: 's6b' }] },
    { number: 7, cues: [{ type: 'bgm-stop' }] },
  ],
};
const idOf = (f) => f.toUpperCase();

test('枚で鳴っているべき BGM は、それまでの最後の合図が勝つ（§3.4）', () => {
  assert.deepEqual(bgmAt(w, 1), { file: 'b1', loop: false, from: 1 });
  assert.deepEqual(bgmAt(w, 2), { file: 'b1', loop: false, from: 1 });
  assert.deepEqual(bgmAt(w, 4), { file: 'b3', loop: false, from: 3 });
  assert.deepEqual(bgmAt(w, 6), { file: 'b5', loop: true, from: 5 }); // loop が無ければループ
  assert.equal(bgmAt(w, 7), null);
});

test('効果音はその枚のものだけ（書いた順）', () => {
  assert.deepEqual(soundsAt(w, 6), ['s6', 's6b']);
  assert.deepEqual(soundsAt(w, 2), []);
});

test('開演前は何も決めない。開演した枚から鳴らす。同じ曲は続け、飛んだら頭から', () => {
  let st = retune(createAudio(), w, 3, idOf, 0);
  assert.equal(st.id, null);
  st = start(st, w, 3, idOf, 1000);
  assert.deepEqual([st.id, st.from, st.pos, st.at], ['B3', 3, 0, 1000]);
  const same = retune(st, w, 4, idOf, 9000);
  assert.equal(same, st); // 続けて鳴らす
  assert.equal(astate(same, 9000).pos, 8);
  st = retune(st, w, 7, idOf, 10000);
  assert.deepEqual([st.id, st.playing], [null, false]);
  st = retune(st, w, 1, idOf, 11000); // 戻る
  assert.deepEqual([st.id, st.pos], ['B1', 0]);
});

test('鳴らす位置: ループは長さで割った余り、1回きりは長さを越えたら終わり', () => {
  assert.equal(bgmPosition({ id: 'A', loop: true, pos: 130 }, 60), 10);
  assert.equal(bgmPosition({ id: 'A', loop: false, pos: 30 }, 60), 30);
  assert.equal(bgmPosition({ id: 'A', loop: false, pos: 61 }, 60), null);
  assert.equal(bgmPosition({ id: null, pos: 1 }, 60), null);
  assert.equal(bgmPosition({ id: 'A', loop: true, pos: 5 }, NaN), 5); // 長さが分からないうちはそのまま
});

test('動画を流し始めたら BGM を止め、動画のあとも枚を移っても同じ曲は鳴らし直さない（2026-10-26 練習の修正票）', () => {
  let st = start(createAudio(), w, 1, idOf, 0);
  st = cutForVideo(st, w, 1, 5000);                     // 1枚目で動画を流した
  assert.deepEqual([st.id, st.playing], [null, false]);
  assert.deepEqual(st.cut, { file: 'b1', from: 1 });
  assert.equal(astate(st, 6000).id, null);              // 聞き手の端末はフェードアウト
  const again = cutForVideo(st, w, 1, 7000);
  assert.equal(again, st, '止めるものが無ければそのまま（合図を送らない）');
  st = retune(st, w, 2, idOf, 8000);                    // 同じ曲の続く枚へ
  assert.equal(st.id, null, '動画のあとに再開しない');
  st = retune(st, w, 1, idOf, 9000);                    // 戻っても同じ曲
  assert.equal(st.id, null);
  st = retune(st, w, 3, idOf, 10000);                   // 次の [BGM] の合図
  assert.deepEqual([st.id, st.pos, st.cut], ['B3', 0, null]);
  st = retune(st, w, 1, idOf, 11000);                   // 別の曲を挟んで戻れば、最初の曲は頭から
  assert.equal(st.id, 'B1');
});

test('動画で止めた曲のあとが [BGM stop] でも、別の曲でも、止めた印は残らない・開演前は何もしない', () => {
  let st = start(createAudio(), w, 5, idOf, 0);
  st = cutForVideo(st, w, 5, 1000);
  st = retune(st, w, 7, idOf, 2000);
  assert.deepEqual([st.id, st.cut], [null, null]);
  const before = createAudio();
  assert.equal(cutForVideo(before, w, 1, 0), before);
});

test('話しているかの判定: しばらく越えつづけたら話し始め・しばらく下回りつづけたら話し終わり（息継ぎ・咳で上下しない）', () => {
  // 先頭の [-60, -1000] は静かな部屋（雑音の高さ＝floor を -60 にする）
  const run = (steps) => [[-60, -1000], ...steps].reduce((st, [db, t]) => talkStep(st, db, t), null);
  assert.equal(run([[-30, 0]]).talking, false, '越えた瞬間はまだ');
  assert.equal(run([[-30, 0], [-30, TALK_ON_MS - 1]]).talking, false);
  assert.equal(run([[-30, 0], [-30, TALK_ON_MS]]).talking, true);
  assert.equal(run([[-30, 0], [-60, 50], [-30, 100], [-30, TALK_ON_MS]]).talking, false, '途切れたら数え直す（咳）');
  const on = run([[-30, 0], [-30, TALK_ON_MS]]);
  assert.equal(talkStep(talkStep(on, -60, 200), -60, 200 + TALK_OFF_MS - 1).talking, true, '息継ぎのあいだは話しているまま');
  assert.equal(talkStep(talkStep(on, -60, 200), -60, 200 + TALK_OFF_MS).talking, false);
  assert.equal(talkStep(talkStep(talkStep(on, -60, 200), -30, 400), -60, 900).talking, true, '話し直したら数え直す');
  assert.equal(talkStep(on, -47, 300).talking, true, 'しきいの間（-50〜-45）は今のまま');
});

test('話しているかの判定: 雑音が持ち上がっても声と取り違えない（自動の音量合わせ。2026-10-26 練習した人の指摘）', () => {
  // 黙っているあいだ、雑音が -60 から -42 へゆっくり持ち上がる（固定のしきい -45 は越える）
  let st = null;
  for (let t = 0, db = -60; t <= 10000; t += 50, db = Math.min(-42, db + 0.1)) {
    st = talkStep(st, db + (t % 200 === 0 ? 2 : 0), t);     // 少しゆらぐ
    assert.equal(st.talking, false, `t=${t} 雑音を声と取り違えた（floor=${st.floor.toFixed(1)}）`);
  }
  // 声は雑音より十分大きい
  let t = 10050;
  for (; t <= 10050 + TALK_ON_MS; t += 50) st = talkStep(st, -25, t);
  assert.equal(st.talking, true, '雑音の上でも声には反応する');
  // 話しているあいだ、雑音の高さは上へ追わない（長く話しても切れない）
  for (; t <= 30000; t += 50) st = talkStep(st, -25, t);
  assert.equal(st.talking, true);
});

// 実際の作品の並び: S12 で曲 → S13 は動画のあとに歓喜の主題（[BGM after video]）→ S14 は続行 → S15 で次の曲
const wa = {
  slides: [
    { number: 1, cues: [{ type: 'bgm', file: 'b1', loop: false }] },
    { number: 2, cues: [{ type: 'bgm', file: 'b2', loop: false, start: 'after-video' }, { type: 'video', file: 'v2' }] },
    { number: 3, cues: [] },
    { number: 4, cues: [{ type: 'bgm', file: 'b4', loop: false }] },
  ],
};

test('[BGM after video] の枚は、前の曲を止めて無音で入り、動画が終わったら鳴らす（2026-10-29 実際の作品の修正票）', () => {
  assert.deepEqual(bgmAt(wa, 3), { file: 'b2', loop: false, from: 2, after: true });
  let st = start(createAudio(), wa, 1, idOf, 0);
  assert.equal(st.id, 'B1');
  st = retune(st, wa, 2, idOf, 1000);
  assert.deepEqual([st.id, st.playing], [null, false], '動画の前は無音');
  assert.equal(cutForVideo(st, wa, 2, 2000), st, '動画を流しても、止めるものは無い');
  st = afterVideo(st, wa, 2, idOf, 60000);
  assert.deepEqual([st.id, st.loop, st.from, st.playing, st.pos, st.at], ['B2', false, 2, true, 0, 60000]);
  assert.equal(afterVideo(st, wa, 2, idOf, 61000), st, '2回目は何もしない');
  const s3 = retune(st, wa, 3, idOf, 90000);
  assert.equal(s3, st, '次の枚では続行');
  assert.equal(retune(s3, wa, 2, idOf, 95000), s3, '戻っても鳴らしたまま');
  st = retune(s3, wa, 4, idOf, 120000);
  assert.equal(st.id, 'B4');
});

test('[BGM after video] の動画を流さずに次の枚へ行けば、そこで頭から鳴る。ほかの枚の動画では鳴らさない', () => {
  let st = start(createAudio(), wa, 2, idOf, 0);
  assert.equal(st.id, null, '開演した枚が after video の枚なら、まだ鳴らさない');
  assert.equal(afterVideo(st, wa, 1, idOf, 500), st, 'ほかの枚の動画の終わりでは鳴らさない');
  st = retune(st, wa, 3, idOf, 1000);
  assert.deepEqual([st.id, st.pos, st.at], ['B2', 0, 1000]);
  assert.equal(afterVideo(createAudio(), wa, 2, idOf, 0).id, null, '開演前は鳴らさない');
});

test('[BGM after video] の枚を離れて戻ったら、また動画を待つ', () => {
  let st = start(createAudio(), wa, 2, idOf, 0);
  st = afterVideo(st, wa, 2, idOf, 1000);
  st = retune(st, wa, 1, idOf, 2000);
  assert.equal(st.id, 'B1');
  st = retune(st, wa, 2, idOf, 3000);
  assert.equal(st.id, null);
});
