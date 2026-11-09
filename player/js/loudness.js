// BGM の曲の大きさを測り、大きすぎる曲を下げる量を決める。DOM にも通信にも触らない純粋な関数だけを置く（node --test で守る）。
// 設計: docs/work-format.md §4。測り方は ITU-R BS.1770-4 の統合ラウドネス（ffmpeg の ebur128 と同じ考え方）。
// ⚠️ 2026-11-09 見本の曲を自分の曲に差し替えると、CD や配信の曲（-10〜-14 LUFS）は見本の曲（-30〜-34 LUFS）より
//    約20dB 大きく鳴って語りを消す。作り手が何もしなくても語りの下に敷けるように、プレイヤーがそろえる。

export const LEVEL_TARGET = -30;   // BGM をこの大きさ（LUFS）まで下げる
export const LEVEL_SLACK = 1;      // 目標よりこれだけ大きいまでは、そのまま（見本の曲・測り方の少しのずれで動かさない）
export const LEVEL_MAX_CUT = -40;  // 下げるのはここまで（dB）

/** K 特性の2段のフィルタの係数（標本化の周波数 fs ごと。libebur128 と同じ求め方） */
export function kWeighting(fs) {
  // 1段目: 高い音を持ち上げる棚
  let f0 = 1681.974450955533, G = 3.999843853973347, Q = 0.7071752369554196;
  let K = Math.tan(Math.PI * f0 / fs);
  const Vh = 10 ** (G / 20), Vb = Vh ** 0.4996667741545416;
  let a0 = 1 + K / Q + K * K;
  const shelf = { b: [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0], a: [2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0] };
  // 2段目: 低い音を切る
  f0 = 38.13547087602444; Q = 0.5003270373238773;
  K = Math.tan(Math.PI * f0 / fs);
  a0 = 1 + K / Q + K * K;
  const high = { b: [1, -2, 1], a: [2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0] };
  return [shelf, high];
}

/** 統合ラウドネス（LUFS）。channels＝各チャンネルの標本（Float32Array など）、fs＝標本化の周波数。
 *  0.4秒より短い・無音なら -Infinity */
export function integratedLoudness(channels, fs) {
  const n = channels.length ? channels[0].length : 0;
  const seg = Math.round(fs / 10);            // 0.1秒（0.4秒の区切りを 0.1秒ずつずらす＝75% 重ねる）
  const segs = Math.floor(n / seg);
  if (!channels.length || segs < 4) return -Infinity;
  const sums = new Float64Array(segs);
  const [s1, s2] = kWeighting(fs);
  for (const x of channels) {
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0, z1 = 0, z2 = 0;
    for (let i = 0, k = 0; k < segs; k++) {
      let acc = 0;
      for (const end = i + seg; i < end; i++) {
        const xi = x[i];
        const y = s1.b[0] * xi + s1.b[1] * x1 + s1.b[2] * x2 - s1.a[0] * y1 - s1.a[1] * y2;
        x2 = x1; x1 = xi;
        const z = s2.b[0] * y + s2.b[1] * y1 + s2.b[2] * y2 - s2.a[0] * z1 - s2.a[1] * z2;
        y2 = y1; y1 = y;
        z2 = z1; z1 = z;
        acc += z * z;
      }
      sums[k] += acc;                         // 左右（前の3つまで）は重み 1 で足す
    }
  }
  const power = [];
  for (let k = 0; k + 4 <= segs; k++) power.push((sums[k] + sums[k + 1] + sums[k + 2] + sums[k + 3]) / (4 * seg));
  const lufs = (p) => -0.691 + 10 * Math.log10(p);
  const mean = (ps) => ps.reduce((a, b) => a + b, 0) / ps.length;
  const loud = power.filter((p) => lufs(p) > -70);
  if (!loud.length) return -Infinity;
  const rel = lufs(mean(loud)) - 10;
  const kept = loud.filter((p) => lufs(p) > rel);
  return lufs(mean(kept));
}

/** 曲を下げる量（dB、0 以下）。大きすぎる曲だけ目標まで下げる。小さい曲は上げない（割れる・雑音が上がる） */
export function levelGain(lufs) {
  if (!Number.isFinite(lufs) || lufs <= LEVEL_TARGET + LEVEL_SLACK) return 0;
  return Math.max(LEVEL_MAX_CUT, Math.round((LEVEL_TARGET - lufs) * 10) / 10);
}

/** 受け取った dB を、掛けてよい範囲に収める（聞き手は語り手から来た値をそのまま信じない） */
export function safeGain(db) {
  const v = Number(db);
  return Number.isFinite(v) ? Math.min(0, Math.max(LEVEL_MAX_CUT, v)) : 0;
}

/** dB → 掛ける倍率 */
export const dbToAmp = (db) => 10 ** (safeGain(db) / 20);
