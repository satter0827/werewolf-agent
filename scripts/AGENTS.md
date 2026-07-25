# Scripts

scriptsはrepository内の再現可能な開発操作を所有します。

- qualityはgateの調整だけを行い、個別処理を再実装しない。
- environmentだけが依存取得を行う。
- test sourceを解析して実行対象を決めない。
- reportと共有生成物は`.werewolf-agent`へ保存する。
- 有料providerや任意の外部APIを品質判定へ使用しない。
