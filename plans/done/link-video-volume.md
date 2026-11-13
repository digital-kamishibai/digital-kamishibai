# リンクの動画の音量（[Video] <リンク> ... volume -6dB）

## なぜ
ファイルの動画は書き出しで約 −22 LUFS にそろうが、リンクの動画は YouTube の音のまま鳴る。YouTube は −14 LUFS より
大きい音しか下げないので、動画ごとに 10dB 近くばらつく。ブラウザから埋め込みの音は測れないので、作る人が書く。
当日の動画のつまみはすべての動画に効くので、1本だけ下げる用には使えない。

## 決めたこと
- 書き方は dB: `volume -6dB`（0 以下、−40 まで）。LUFS で測った差がそのまま書ける。BGM の gain（dB）と単位がそろう
- リンクの動画だけ。ファイルの動画は書き出しでそろえる（録画は volume の前で取られる、iPhone は volume を無視する）
- work.json の cue に `volume`（dB）。聞き手へ送る links にも入れる。どの端末でも 当日のつまみ × 10^(dB/20) を setVolume へ
- 実機で測った（2026-11-10、本物の YouTube、ヘッドレス Edge）: setVolume(n) → 埋め込みの <video>.volume = n/100（線形・振幅）

## 手順
1. build_work.py に volume（テスト）
2. work.js の検査・resolveLinks、protocol.js の links、ytlink.js の音量の計算（テスト）
3. 語り手・聞き手で item の volume を使う。e2e（差し替え版）で setVolume の数を見る
4. work-format.md・script-template.md・SKILL.md、plugin の版を 0.10.0 へ
