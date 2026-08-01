# React再導入手順

削除済みブラウザーUIの復元元と再導入条件を記録する。現行製品のブラウザーUIはPython製Streamlit、
ブラウザーE2EはPython Playwrightであり、React、Node.js、npmを使用しない。

## 復元元

撤去commitは`396dde8`、その親である廃止前の基準revisionは
`e865cf48c7fb63b0ff7b19e4b1e8ae0da2bd3863`である。現在のcheckoutへ
旧ソースコードを直接戻さず、別worktreeで参照する。

```powershell
git worktree add ..\werewolf-agent-react-reference e865cf48c7fb63b0ff7b19e4b1e8ae0da2bd3863
```

## 再導入条件

1. 現行OpenAPI、認証、公開情報、管理者情報の境界へ適合させる。
2. game操作はHTTP APIだけを使用し、domain ruleや勝敗判定をclientへ複製しない。
3. 設定、依存lock、container、CI、architecture manifestを現行品質基盤へ新規に統合する。
4. unit、integration、desktop/mobileブラウザーE2E、accessibility、外部通信拒否を実装する。
5. Streamlitとの役割分担と運用責任をdesign文書で決定してから公開する。

旧package、生成client、containerをそのまま復帰させる互換手順は提供しない。
撤去後に追加されたsetup revision、エージェントdeliberation、FeatureSpec、quality impact、ブラウザーカタログを
旧実装へ逆移植せず、現行契約に対する新しいclientとして実装する。
