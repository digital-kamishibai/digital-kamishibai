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
