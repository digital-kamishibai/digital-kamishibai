# ✅ 完了 リンクの動画の音量を、練習で耳で直す（修正票の Volume）

## なぜ
volume -6dB を台本に dB で書くのは、AI を使わずに作る人には難しい。ブラウザは YouTube の音を測れないので自動ではそろえられない。
既定で下げる案は、元が小さい動画で外れるので採らない。

## 決めたこと
- 練習（draft・受付を開いていない）のとき、リンクの動画の枚に「この動画の音を小さく／大きく」（2dB ずつ、0〜-40dB）
- 上げるのは 0dB まで（埋め込みは元より大きく鳴らせない）。ファイルの動画には付けない
- 修正票: ## [Slide N] video K ／ Volume -6dB (was 0dB)。台本の値に戻したら件を消す。読み直して台本がその値なら反映済み
- 書き戻すのは Claude（references/correction-sheet.md）。check_sheet.py も判定する
- 受付を開いたら、語り手も台本の値（聞き手と同じ）
- 作りかけはブランチ link-volume-practice（92756f1 を公開用へ写すのが先）

## 手順
1. ✅ corrections.js（setLinkVolume・linkVolumeNow・判定・Markdown・保存）＋テスト
2. ✅ 語り手の画面（volBar）・ytlink.js setItemVolume・i18n
3. ✅ check_sheet.py ＋テスト、tests/e2e/link_volume.py
4. ✅ work-format §2.4・§6、correction-sheet.md、plugin 0.11.0
5. 検査 → コミット → 92756f1 を公開用へ写したあとで main へ → 開発用の箱 → 持ち主が実機で

- 2026-11-10 実機で確かめ済み（音量は替わる）。ボタン名が「動画の大きさ」と読めたので「この動画の音を小さく／大きく」に直した（fe10c0f）
- 2026-11-10 同じ枚に同じ区間のリンクの動画が2本あると、動画を選ぶボタンの文字が同じになる件は直さない（持ち主の判断）。ふつうは違う動画・違う区間で文字が違い、同じでも「動画1／動画2」の番号で区別できる
