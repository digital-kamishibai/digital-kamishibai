// ICE の様子の読み取り（純粋な関数。ブラウザと node --test の両方から使う）。
//
// ⚠️ 候補の数は数えない。失敗するとブラウザが統計から候補を消し、「相手の候補ゼロ」と誤って見える
// （2026-10-24: 実際には候補は全部届いていて、止まっていたのは確認の通信だった）。
// 見るのは**確認の往復**——送った数・返事の数・相手から届いた数。

/** getStats() の結果（配列か forEach を持つ物）から、確認の往復を数える。 */
export function summarizeIce(stats, state = '') {
  const local = {};
  let sent = 0; let answered = 0; let heard = 0; let pairs = 0;
  const each = (fn) => (typeof stats.forEach === 'function' ? stats.forEach(fn) : Object.values(stats).forEach(fn));
  each((r) => {
    if (r.type === 'local-candidate') {
      const kind = r.candidateType === 'host' && /\.local$/.test(r.address || r.ip || '') ? 'mdns' : r.candidateType;
      local[kind] = (local[kind] || 0) + 1;
    }
    if (r.type === 'candidate-pair') {
      pairs += 1;
      sent += r.requestsSent || 0;
      answered += r.responsesReceived || 0;
      heard += r.requestsReceived || 0;
    }
  });
  return { state, pairs, sent, answered, heard, local };
}

/** 新しい数え方が空（失敗後に統計が消えた）なら、前回の数を残して状態だけ新しくする。 */
export function keepLast(prev, next) {
  if (next.pairs === 0 && prev && prev.pairs > 0) return { ...prev, state: next.state };
  return next;
}

/** 確認を十分に（合計30回＝数秒ぶん。1組あたり毎秒1回ほど送る）送ったのに、返事も相手からの確認も1つも無い＝家の中の UDP が届いていない。
 *  Android 17 以降では、Chrome にローカル ネットワーク権限が無いとこうなる（ping は通るので気づきにくい）。 */
export function looksBlocked(s) {
  return !!s && s.sent >= 30 && s.answered === 0 && s.heard === 0;
}

export const isAndroid = (device) => /^Android/.test(String(device || ''));

/** 返事が無いとき、どこで止まっているか。案内の文はこの答えで選ぶ（語り手と聞き手で言い方が違うので、文は持たない）。
 *  - 'no-relay-here': 中継を配っているのに、この端末に relay の候補が無い＝この端末のネットワークが中継サーバーへの通信を通さない（学校・会社のネットワーク）
 *  - 'no-relay-there': この端末は中継に出られるのに返事が無い＝相手の端末のネットワークが中継を通さない
 *  - 'local-net': 中継が無く、相手が Android（Chrome のローカル ネットワーク権限）
 *  - 'same-wifi': 中継が無い。直接つながるには同じネットワークが要る
 *  中継があれば Android の権限は効かない（中継はインターネット越しで、家の中の通信を使わない）ので、権限の案内は中継が無いときだけ。 */
export function whyBlocked(s, { relay = false, android = false } = {}) {
  if (!looksBlocked(s)) return null;
  if (relay) return s.local && s.local.relay ? 'no-relay-there' : 'no-relay-here';
  return android ? 'local-net' : 'same-wifi';
}

/** つながった接続が、直接か中継か（'direct' | 'relay' | null）。選ばれた候補の組の、どちらかの端が relay なら中継。
 *  選ばれた組の見つけ方はブラウザで違う: Chrome・Safari は transport の selectedCandidatePairId、Firefox は組の selected。 */
export function routeOf(stats) {
  const byId = new Map();
  let pairId = null;
  const each = (fn) => (typeof stats.forEach === 'function' ? stats.forEach(fn) : Object.values(stats).forEach(fn));
  each((r) => {
    if (r && r.id) byId.set(r.id, r);
    if (r && r.type === 'transport' && r.selectedCandidatePairId) pairId = r.selectedCandidatePairId;
  });
  let pair = pairId ? byId.get(pairId) : null;
  if (!pair) pair = [...byId.values()].find((r) => r.type === 'candidate-pair' && r.selected);
  if (!pair) pair = [...byId.values()].find((r) => r.type === 'candidate-pair' && r.nominated && r.state === 'succeeded');
  if (!pair) return null;
  const local = byId.get(pair.localCandidateId);
  const remote = byId.get(pair.remoteCandidateId);
  if (!local && !remote) return null;
  return (local && local.candidateType === 'relay') || (remote && remote.candidateType === 'relay') ? 'relay' : 'direct';
}

/** 中継を止めている理由（/api/ice の reason。損失の天井）→ 案内の文の鍵。語り手と聞き手で言い方が違う。
 *  理由が無い（中継を配っている・鍵が無い箱・見張りが止まっている）なら null——いつもの「同じ Wi-Fi」の案内に任せる。 */
export function relayNote(reason, who = 'narrator') {
  const base = { month: 'relayMonth', day: 'relayDay' }[reason];
  if (!base) return null;
  return who === 'listener' ? `${base}Listener` : base;
}

/** 確かめる人のための切り替え: ページの URL に ?relay を付けると、中継だけを使う（直接の道を試さない）。
 *  同じ回線どうしでは直接つながってしまい、中継・取り消し・枠の案内を実機で見られないため。中継を配っていないときは効かせない（つながらなくなる）。 */
export function forcedRelay(search, relay) {
  return relay && new URLSearchParams(search || '').has('relay') ? { iceTransportPolicy: 'relay' } : {};
}
