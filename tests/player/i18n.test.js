import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pair } from '../../player/js/i18n.js';

test('中継の枠の案内: 英日がそろい、直接つながる端末なら上演できることと、戻る時を言う', () => {
  for (const key of ['relayMonth', 'relayDay']) {
    const [en, ja] = pair(key);
    assert.match(en, /relay allowance is used up/);
    assert.match(en, /connect directly/);
    assert.match(en, /UTC/);
    assert.match(ja, /中継の枠を使い切りました/);
    assert.match(ja, /直接つながる端末/);
    assert.match(ja, /日本時間の朝9時/); // 区切りは UTC の0時
  }
  assert.match(pair('relayMonth')[1], /今月/);
  assert.match(pair('relayDay')[1], /今日/);
});

test('聞き手への案内: 同じ Wi-Fi なら入れることを言う（「同じ Wi-Fi ですか？」の前に添える）', () => {
  for (const key of ['relayMonthListener', 'relayDayListener']) {
    const [en, ja] = pair(key);
    assert.match(en, /same Wi-Fi as the narrator/);
    assert.match(ja, /語り手と同じ Wi-Fi/);
  }
  assert.equal(pair('noSuchKey'), null);
});

test('リンクの動画の言葉: 流せない理由はどれも英日がそろう・語り手には「流せないときの語り」へ進むよう言う', () => {
  for (const why of ['api', 'blocked', 'gone', 'bad-link', 'referrer', 'player', 'stall']) {
    const p = pair('linkWhy_' + why);
    assert.ok(p && p[0] && p[1], why);
  }
  assert.match(pair('linkHereNo', 'x')[1], /動画を流せないときの語り/);
  assert.match(pair('linkHereNo', 'x')[0], /cannot be played/);
  for (const key of ['chipLinkNo', 'linkPrepNo', 'linkStall']) assert.ok(pair(key)[0] && pair(key)[1], key);
  for (const key of ['linkPeersNo', 'linkPeerNo', 'linkCannot', 'linkName']) assert.ok(pair(key, 'x')[0] && pair(key, 'x')[1], key);
});

test('見本を元にしていない台本の案内: どのボタンで開けるか・自分の作品はどのボタンかを、英日とも名指しする', () => {
  const [en, ja] = pair('scriptNotVariant');
  assert.match(en, /Open a script or a zip/);
  assert.match(ja, /「台本・zip のファイルを開く」と「台本を貼る」/);
  assert.equal(pair('openScript')[1], '台本・zip のファイルを開く');   // 案内の名指しとボタンの名前がずれない
  const folder = pair('scriptOwnFolder');
  assert.ok(folder[0].includes(`“${pair('pickWork')[0]}”`) && folder[1].includes(`「${pair('pickWork')[1]}」`));
  const zip = pair('scriptOwnZip');
  assert.ok(zip[0].includes(`“${pair('openScript')[0]}”`) && zip[1].includes(`「${pair('openScript')[1]}」`));
  assert.match(zip[1], /zip/);
});
