(development)=
# 開発

変更は要求、設計境界、実装、検証、文書を一つの単位として扱う。人が判断するのは
要求の優先順位、外部サービスの権限、公開判断であり、再現可能な作業は repository
内のコマンドへ実装する。

## 開発の流れ

1. README、対象設計書、近い実装とテストを読み、要求を外部挙動と制約に分ける。
2. 変更する責務と依存方向を決め、大きな境界変更は設計書へ先に反映する。
3. 再現テストまたは契約テストを用意し、最小の責務へ実装する。
4. formatter、lint、型、対象テストを実行する。
5. 文書、設定例、generated contract、不要な旧構造を同じ変更で整える。
6. 品質 profile を実行し、生成された report で結果を確認する。

## 環境構築

```powershell
uv sync --frozen --all-groups --all-extras
uv run --no-sync werewolf-agent doctor
```

依存が同期済みの環境では `uv run --no-sync` を使う。品質 runner は依存取得や
browser download を行わないため、必要な image と browser は実行前に準備する。

## 実装規則

- domain rule は domain、ID を含む利用者要求は usecase に置く。
- 外部サービス接続は adapters、起動と入出力は interfaces に置く。
- 可変値は設定へ寄せ、設定名と検証を一か所で定義する。
- 後方互換用の fallback を残さず、不要な path と処理を削除する。
- 失敗を再現できる test を先に追加し、乱数 seed と fixture を固定する。
- public Python API には Google style の docstring を記述する。

## 文書の更新

完成した仕様と構造は `docs/design`、断片的な調査と引き継ぎは `docs/notes` に置く。
Sphinx の公開面は `docs/index.md` から到達できるようにする。構造、API docstring、
参照切れは `uv run --no-sync python -m scripts.docs inspect` と Sphinx build で検査する。
