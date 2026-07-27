# Streamlitゼロベース再レビュー

React撤去後のStreamlitと品質検査を、当初要件、実装、自動Browser E2E、保存済み画像の順に
照合する。Reactは監査と変更の対象に含めない。

## 初回監査

画面の配色と構造は「月明かりの卓」に沿う一方、Release成果物だけでは状態別の受入判定が
できなかった。待機、発言、送信中、対象選択が一枚へ集約され、設定のdesktop画像は320pxへ
変更した後に保存されていた。設定のmobile画像はsidebarが本文を覆い、記録の空状態、記録あり、
縮退表示には独立画像がなかった。

これは製品UIの見た目ではなく、状態遷移と証跡取得を一つのscenarioへ詰め込んだ検査責務の
問題である。合格結果と目視可能な証拠が対応していなかった。

## 修正

- 待機、発言、送信中、対象選択、完了、観戦、記録の空・記録あり、設定、320px、縮退表示を
  独立した証跡へ分けた。
- Streamlit内部のscroll位置を状態遷移ごとに揃え、mobile sidebarは遷移先の見出しを確認してから
  keyboardで閉じる。
- 接続情報を外したStreamlitをBrowser E2E内で独立起動し、縮退表示にも通常画面と同じ品質判定を
  適用する。
- 縮退表示からAPI、database、処理queueなどの内部内訳と例外詳細を削除し、現在可能な操作と
  復旧方法だけを表示する。詳細原因は構造化ログに残す。
- 縮退表示の見出しを`h1`、`h2`の順へ直し、不要になったruntime表示文言を削除した。
- `client.toolbarMode = "viewer"`をrepository設定へ追加し、Deployなどの開発者操作を一般画面から
  外した。Browser検査でも実装メタ情報として拒否する。
- CLIの公開設定取得がHTTP APIへ移行済みであることに合わせ、残っていたSupabase直結前提の
  testを公開client contractへ直した。

## 再監査

再生成した23枚の画像をcontact sheetと原寸画像で確認した。desktopはstatus ribbon、tableau、
操作railの密度が分かれ、mobileはstatusとseatが二列になる。入力欄、補助文、disabled状態、
section間隔は識別でき、sidebarは本文を覆わない。アイボリー、藍、深緑、琥珀、鈍い赤は意味を
持つ箇所に限定され、過度な装飾、gradient、外部assetはない。

原寸監査で見つけたDeploy表示をviewer modeで除去した後、Releaseは22 gate、Browser E2E 12件、
成果物整合性を通過した。最終判定は`.werewolf-agent/quality/latest/profiles/release/report.json`を
正本とする。

Browser画面確認スキルによる対話操作はBrowser接続policyにより実行できなかった。この項目だけを
`blocked`とし、自動Browser E2Eと保存済み画像の判定には混ぜない。
