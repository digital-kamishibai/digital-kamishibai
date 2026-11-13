# 上演の画面を、スクロールせずに語れる配置にする

## Context

上演の画面（`player/narrator.html` の `#screenShow`）で、語り手が困っていること:

1. **台本を読むのにスクロールが要る** — 台本の枠（`.notes`）は `height: calc(100vh - 250px)` の固定だが、上のタブ・帯（`.toolbar`）・練習中の帯などが 250px を超えるので、**ページ全体もスクロールする**。台本の枠の中のスクロールと二重になる。字の大きさも 1.4rem 固定。
2. **次の絵がスクロールしないと見えない** — 左の列は「聞き手の画面 → 戻る／次へ → 動画の選び・練習用の欄（seat/cut/vol/pic/cand）→ 札 → 次の絵」の順で、次の絵が一番下。
3. **スマホ・タブレット** — 1279px 以下は全部縦に積む（`app.css` の `@media (max-width: 1279px)`）。横向きの iPad（1180px・1024px）でも縦積みになり、台本は絵・ボタン・札の**下**＝ページを大きくスクロールしないと読めない。帯のボタンは折り返して3行になる。

目標: **上演の画面ではページがスクロールしない**。台本はその枠の中だけでスクロールし、次の絵と「戻る／次へ」はいつも見えている。PC・横向きタブレット・縦向きタブレット・スマホで、それぞれ語りやすい配置にする。

決めたこと（持ち主に確認済み）: 横長の画面では、次の絵は **「次へ」のボタンの横** に小さく置く。

## 進め方

着手したら、このプランを `plans/show-layout.md` に写す（リポジトリの決まり）。ブランチ `show-layout` で進める（作りかけを main に置かない）。

### 1. 画面の高さに収める（全幅共通）

- `narrator.js` の画面切り替え（106 行目あたり、`screen = next` の所）で `document.body.dataset.screen = screen` を付ける。
- `app.css`: `body.narrator[data-screen="show"]` のときだけ
  - `body` を `height: 100dvh; display: flex; flex-direction: column`、`main` を `flex: 1; min-height: 0`、`#screenShow` を縦の flex にする。
  - 帯や知らせ（`#joinBanner`・`#practiceNote`・`#varyNote`・`.toolbar`・`#soundPanel`・`#sheetPanel`・`#composePane`）は自分の高さだけ取る。大きくなるもの（`#sheetPanel`・`#composePane`）は `max-height: 40dvh; overflow-y: auto`。
  - `.show`（`#showGrid`）は `flex: 1; min-height: 0`。左の列（`.side`）・右の列（`.script`）はそれぞれ `overflow-y: auto`。
  - `.notes` は固定の高さ（`calc(100vh - 250px)`）をやめ、右の列の中で `flex: 1; min-height: 0; overflow-y: auto`。
  - 逃げ道: `.show` に `min-height: 320px` 程度。知らせが大量に開いて足りないときだけページがスクロールする（いまより悪くはしない）。
- 直す欄（`.edit-notes` の `calc(100vh - 360px)`）・語りを変える欄は、右の列のスクロールの中に入るので、高さは `min-height` だけ残して列に任せる。

### 2. 次の絵を「次へ」の横へ（横長）

- `narrator.html`: `#nextLabel`・`#next` を `.nav` の中、`#nextBtn` の右へ移す（`<figure class="nav-next">` に包む。中身の id はそのまま＝`renderSlide()` の 1394–1396 行目は変えずに動く）。
- `app.css`: `.nav-next img.next` は高さを `.nav` の行に合わせた小さめ（例: 幅 9〜12rem、16:9）。いまの `img.next { width: 45% }` は置き換える。
- 札（`#chips`）と練習用の欄は、そのまま `.nav` の下（左の列の中でスクロール）。

### 3. 台本を読みやすく

- **字の大きさのつまみ**: 台本の見出しの行（`.script .row`、時計の横）に `A−` `A+`。`.notes` の `font-size` を CSS 変数 `--notes-size` で持ち、この端末のブラウザに覚える（`localStorage`。境目 `dk-split` と同じ形: `try/catch`・既定値なら消す）。範囲と刻みは `view.js` に純粋な関数 `clampNotesSize()` として置く（`clampSplit()` と同じ形）。
- **キーで台本を送る**: `document` の keydown（2171 行目）に `ArrowDown`／`ArrowUp` を足し、`#notes` を枠の 8 割ぶん `scrollBy`（滑らかに）。枚送りのキー（→・PageDown・Space・←・PageUp）は変えない。入力欄の中では効かない（いまの除外をそのまま使う）。
- 枚を送ったら台本は頭へ（`notes.scrollTop = 0` はいまのまま）。

### 4. 横向きタブレットも左右に並べる

- 縦積みに切り替える条件を `@media (max-width: 1279px)` から **`(max-width: 899px), (orientation: portrait)`** に変える。1024px・1180px の横向き iPad は左右に並ぶ。
- 900〜1279px の横長では、帯のボタンを少し詰める（`padding`）・境目の既定 42% はそのまま。
- `.splitter` はタッチでも動く（`pointer*` と `touch-action: none` は既にある）。

### 5. 縦向き・スマホの配置

縦積みのときの並び（`.show` を縦の flex にし、`order` で並べ替える）:

```
[タブ（アプリ名は隠す）]
[帯（1行・横にスクロール）]
[聞き手の画面 16:9（高さ最大 30dvh）]
[台本（残りの高さ・ここだけスクロール）]
[戻る | 3/12 | 次へ | 次の絵]   ← 画面の下に固定（親指が届く）
[札・練習用の欄（台本の下、左の列ごと折りたたみ ▸）]
```

- `.side` を `display: contents` にして、`#stageFrame`・`.nav`・その他を `.show` の直接の子として `order` で並べる。`.nav` は `position: sticky; bottom: 0`（背景を付ける）。
- 札と練習用の欄は、縦積みのときは `<details>`風の「札・練習 ▸」1行に畳む（開くと台本の上に重ならず、台本が縮む）。上演中に札（聞き手の状態）を見たいので、**札に警告がある（`.chip.warn`）ときは畳んだ行に印を出す**（`renderChips()` で数える）。
- `.toolbar` は縦積みのとき `flex-wrap: nowrap; overflow-x: auto`（折り返さない＝下が上下に動かない。`#talkLamp` の `.off` と同じ考え）。
- `.tabs .app` は狭いとき隠す。
- スマホ横向き（高さ 400px 前後）: 条件 4 で左右に並ぶ。高さが足りないので `@media (max-height: 500px)` で帯・タブの余白を詰め、聞き手の画面を左の列の幅いっぱいにする。

### 6. 触らないもの

- 聞き手の画面（`listen.html`）・録画（録るのは聞き手の画面だけ）・送る合図。
- 絵の候補を見くらべる `#candPanel`（全画面の重ね）。
- 受付・準備の画面（`data-screen` が show のときだけ効かせる）。

## 主に触るファイル

- `player/css/app.css` — 上演の画面の配置（65–122 行目、223–230 行目のメディアクエリ）
- `player/narrator.html` — 次の絵を `.nav` へ・字の大きさのつまみ・縦積みの折りたたみ
- `player/js/narrator.js` — `body.dataset.screen`、字の大きさ、↓↑ のキー、畳んだ行の警告の印
- `player/js/view.js` — `clampNotesSize()` など（`clampSplit()` の隣）
- `player/js/i18n.js` — 新しい文言（英・日）
- `tests/player/view.test.js` — 字の大きさの関数のテスト
- `tests/e2e/show_layout.py`（新規）— 下の確かめ

## 確かめ

1. `npm test`（`node --test`）— `clampNotesSize()` を足したテストが通る。
2. 新しい e2e `tests/e2e/show_layout.py`（`site_sample.py` の形を借りる: `burn` で見本 `?test&sample=six-friends-smoothie` を開き、`Emulation.setDeviceMetricsOverride` で幅を変える）。幅×高さ: 1920×1080・1366×768・1180×820・1024×768（iPad 横）・820×1180・768×1024（iPad 縦）・844×390（スマホ横）・390×844（スマホ縦）。それぞれで:
   - ページがスクロールしない: `document.scrollingElement.scrollHeight <= innerHeight + 1`、横にもはみ出さない
   - `#nextBtn`・`#prev`・`#next`（最後の枚以外）・`#notes` が画面の中に見えている（`getBoundingClientRect` が viewport の内側）
   - 長い台本の枚で `#notes` がスクロールでき、`ArrowDown` で `scrollTop` が増え、`ArrowRight` で枚が進んで `scrollTop` が 0 に戻る
   - `A+` で字が大きくなり、読み込み直しても残る
   - 直す欄を開いても例外が無く、`閉じる` まで行ける（練習用の版の写しで。既存 `tests/e2e/family_basic.py` 系の流れを流用）
   - 各幅の画面を撮って作業フォルダに残す
3. 既存の e2e のうち上演の画面を触るもの（`site_sample.py`・`family_basic.py`・`video_cut.py`・`picture_choose.py`・`layout_color.py`）を回して壊れていないこと。
4. **実機は持ち主に頼む**（開発用の箱の URL・Ctrl+F5・何が見えれば成功か、を1行ずつ）: PC の全画面、iPad の横と縦、スマホの縦で、見本を「1台で通して見る」→ スクロールせずに台本・次の絵・次へが見えるか。iPad のタッチで境目が動くか。
5. Skill は変えないので `plugin.json` の版は上げない。コミット前に家族固有情報の検査（持ち主の手順）。
