// 録画（プラン「録画と練習」G1〜G3）。語り手の PC の中だけで録り、どこにも上げない。
// 映像＝「聞き手の画面」を 16:9 に描き直したもの（台本は描かない＝R1）。音＝語り手の声・届けている聞き手の声・BGM・効果音・動画の音を1本に混ぜたもの。
// 録ったそばから、語り手が選んだファイルへ少しずつ書く（File System Access API。メモリに抱えない——30分で 0.5〜1GB）。
//
// ⚠️ 語り手の PC の音は出どころが分かれている（BGM・効果音＝engine.js の AudioContext／動画＝枠の <video>／声＝mixer.js の AudioContext）。
//    それぞれの流れ（MediaStream）をこの録画用の AudioContext に集めて混ぜる。
// ⚠️ <video> の captureStream() の音は、音量つまみ（volume）の**前**で取られる（2026-10-24 Chrome 155 で確認: volume 0 でも同じ大きさ）。
//    聞き手の端末は音量つまみの後の音を聞いているので、ここで同じ量を掛ける。

import { fitRect } from './record.js';
import { createScanner, finalize } from './mp4fix.js';

export function createRecorder({ width = 1280, height = 720, fps = 30, draw }) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const g = canvas.getContext('2d');
  let actx = null;
  let dest = null;
  let rec = null;
  let writable = null;
  let chain = Promise.resolve();
  let drawTimer = 0;
  let startedAt = 0;
  let bytes = 0;
  let error = null;
  const sources = [];            // { node, close }
  let video = null;              // { track, src, gain }
  let videoVolume = 1;
  let stopped = null;
  let scanner = null;            // MP4 のとき、書きながら moov・moof を拾う（止めたときにふつうの MP4 へ直す。mp4fix.js）
  let fixed = false;

  /** 枠に1コマ描く。draw(put) が何を描くかを決め、put(el, w, h) で描く */
  function frame() {
    g.fillStyle = '#000';
    g.fillRect(0, 0, width, height);
    draw((el, sw, sh) => {
      const r = fitRect(sw, sh, width, height);
      if (r) { try { g.drawImage(el, r.x, r.y, r.w, r.h); } catch { /* 読み込み途中 */ } }
    });
  }

  /** 音の流れを1本足す（録画の途中からでも足せる）。close を返す */
  function addAudio(stream) {
    if (!actx || !stream || !stream.getAudioTracks().length) return () => {};
    const node = actx.createMediaStreamSource(stream);
    node.connect(dest);
    const item = { node, close: () => { try { node.disconnect(); } catch { /* 外し済み */ } } };
    sources.push(item);
    return item.close;
  }

  return {
    get recording() { return !!rec && rec.state === 'recording'; },
    /** 録った時間（秒）・書いた大きさ（バイト）・書けなかったときの理由 */
    status() { return { recording: this.recording, sec: rec ? (performance.now() - startedAt) / 1000 : 0, bytes, error }; },

    /** 録画用の AudioContext を作る。⚠️ 押した操作の中で（保存先を選ぶ画面を出す前に）呼ぶ */
    prepare() {
      if (actx) return;
      const AC = window.AudioContext || window.webkitAudioContext;
      actx = new AC();
      dest = actx.createMediaStreamDestination();
      actx.resume().catch(() => {});
    },

    /** 録り始める。out＝書き先（FileSystemWritableFileStream）、mime＝pickMime の結果 */
    start(out, mime) {
      this.prepare();
      writable = out;
      bytes = 0;
      error = null;
      chain = Promise.resolve();
      scanner = mime.startsWith('video/mp4') ? createScanner() : null;
      fixed = false;
      frame();
      drawTimer = setInterval(frame, 1000 / fps);
      const v = canvas.captureStream(fps).getVideoTracks()[0];
      const stream = new MediaStream([v, ...dest.stream.getAudioTracks()]);
      rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 2_500_000, audioBitsPerSecond: 128_000 });
      stopped = new Promise((res) => rec.addEventListener('stop', res, { once: true }));
      rec.addEventListener('dataavailable', (e) => {
        if (!e.data || !e.data.size) return;
        bytes += e.data.size;
        const blob = e.data;
        chain = chain.then(async () => {
          if (error) return;
          if (!scanner) { await writable.write(blob); return; }
          const buf = new Uint8Array(await blob.arrayBuffer()); // 1秒ぶん（約0.3MB）。書いたら手放す
          scanner.push(buf);
          await writable.write(buf);
        }).catch((err) => {
          // 書けない（空き容量・保存先が消えた）。録画を止めて、語り手の画面に理由を出す
          error = String((err && err.name) || err);
          if (rec && rec.state !== 'inactive') rec.stop();
        });
      });
      rec.start(1000); // 1秒ごとに書く（メモリに抱えない）
      startedAt = performance.now();
    },

    addAudio,

    /** 動画の音。el＝枠の <video>。新しい動画になったら（音の流れが変わったら）つなぎ直す */
    setVideo(el) {
      if (!actx || !el) return;
      let track = null;
      try { track = (el.captureStream ? el.captureStream() : el.mozCaptureStream()).getAudioTracks()[0] || null; } catch { track = null; }
      if (video && track && video.track.id === track.id) return;
      if (video) { try { video.src.disconnect(); } catch { /* 外し済み */ } video = null; }
      if (!track) return;
      const src = actx.createMediaStreamSource(new MediaStream([track]));
      const gain = actx.createGain();
      gain.gain.value = videoVolume;
      src.connect(gain).connect(dest);
      video = { track, src, gain };
    },

    /** 動画の音量つまみ（聞き手と同じ量にする。上の ⚠️） */
    setVideoVolume(v) {
      videoVolume = Math.min(1, Math.max(0, Number(v) || 0));
      if (video) video.gain.gain.value = videoVolume;
    },

    /** 録画を止め、ファイルを書き終える。戻り値 { bytes, sec, error } */
    async stop() {
      if (!rec) { // 録り始める前にやめた（保存先を選ばなかった）。用意した AudioContext だけ閉じる
        if (actx) { try { await actx.close(); } catch { /* 閉じ済み */ } actx = null; dest = null; }
        return { bytes, sec: 0, error };
      }
      const sec = (performance.now() - startedAt) / 1000;
      if (rec.state !== 'inactive') rec.stop();
      await stopped;
      clearInterval(drawTimer);
      await chain;
      // 断片に分けた MP4 を、ふつうの MP4 に直す（索引を末尾に足し、もとの索引と断片の表を 'free' にする。中身は動かさない）。
      // ⚠️ 直さないと Windows のメディアプレイヤーがシークバーを出さない（2026-10-24 の実機確認）。直せなくても、断片のままで再生はできる
      if (scanner && !error) {
        try {
          const fix = finalize(scanner.result());
          if (fix) {
            for (const p of fix.patches) await writable.write({ type: 'write', position: p.position, data: p.data });
            await writable.write({ type: 'write', position: fix.position, data: fix.append });
            fixed = true;
          }
        } catch (err) { console.error(err); }
      }
      scanner = null;
      try { await writable.close(); } catch (err) { error = error || String((err && err.name) || err); }
      for (const tr of rec.stream.getTracks()) if (tr.kind === 'video') tr.stop();
      rec = null;
      for (const s of sources.splice(0)) s.close();
      if (video) { try { video.src.disconnect(); } catch { /* 外し済み */ } video = null; }
      const out = { bytes, sec, error, fixed };
      try { await actx.close(); } catch { /* 閉じ済み */ }
      actx = null;
      dest = null;
      return out;
    },
  };
}
