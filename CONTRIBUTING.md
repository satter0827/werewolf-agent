# Contributing

Werewolf Agentへの変更は、責務と依存境界を保ち、再現可能な検証を伴う必要がある。
大きな変更は、実装前にIssueまたはDraft PRで目的と影響を共有する。

## 開発の流れ

1. 最新の`develop`から短期branchを作成する。
2. 変更原因を所有モジュールまで絞り、同じ原因を持つ箇所を確認する。
3. 実装、設定、文書、テストを同じ変更として整合させる。
4. formatter、lint、型検査、関連テスト、必要な品質プロファイルを実行する。
5. `develop`向けPRを作成し、目的、影響、検証結果を記載する。

環境準備、品質プロファイル、ブラウザーE2E、診断の具体的な操作は
[scripts運用ガイド](scripts/README.md)を参照する。設計変更は対応する`docs/design`の仕様へ反映する。

## Pull Request

PRは一つの目的に絞り、無関係な変更を含めない。後方互換は要件で求められた場合だけ維持し、
不要になった旧path、fallback、重複を削除する。取り込みにはmerge commitを使用する。

## 報告

一般的な不具合と機能提案にはGitHub Issueを使用する。脆弱性は公開Issueへ記載せず、
[Security Policy](SECURITY.md)に従って報告する。
