# ✅ 完了 自分の作品の台本を「台本・zip のファイルを開く」で選んで止まる（#12）

## 起きたこと

作り手が、準備の画面の「台本・zip のファイルを開く」で自分の作品の `script.md`（`Based on` の行が無い）を選び、
`scriptNotVariant` の案内を読んでも「作品フォルダを選ぶ」へたどり着けなかった（実機で）。

## 決めたこと（候補3つから持ち主が選んだ）

- ボタンの名前・並べ方は変えない。**案内の中に「作品フォルダを選ぶ」ボタンを置き**、押すとその場でフォルダを選ぶ窓が出る
  （`#pickWorkHere`。`pickFolder` で上のボタンと同じ道。押すのが利用者の操作なので `showDirectoryPicker` が使える）
- 案内の文は、どのボタンで何が開けるかを名指しする（`scriptNotVariant`）＋「このボタンは、上の『作品フォルダを選ぶ』と同じ」（`scriptOwnFolder`）
- フォルダを選べない端末（`view.js` の `canPickFolder`: 窓が無く、iPad・iPhone・Android）にはボタンを出さず、
  作品フォルダを丸ごと zip にして「台本・zip のファイルを開く」で開くよう言う（`scriptOwnZip`）。iPad は zip で開く、の理由は崩さない
- 退けた案: ボタンの名前を「見本から作った台本・作品の zip を開く」に変える／自分の作品と見本の台本で行を分ける

## 確かめ

- `tests/player/view.test.js`・`tests/player/i18n.test.js`（案内の名指しとボタンの名前がずれない）
- `tests/e2e/vary_sample.py`: 案内の中にボタン → そのボタンの input で選んだ作品フォルダが開く（窓は差し替え）→ iPad では zip の案内
