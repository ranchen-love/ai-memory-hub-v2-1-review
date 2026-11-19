# AI Memory Hub — 自分で管理できる AI メモリ基盤

**Languages:** [简体中文](../../README.md) · [English](README.en.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português (Brasil)](README.pt-BR.md) · [Русский](README.ru.md)

---

> **会話の文脈も、ファイルも、管理権限もあなたのもの。** AI サービスに依存しない、ローカル優先の長期メモリ・プロジェクト継続・AI エージェント間引き継ぎのための基盤です。

**バージョン 2.3.0 · Python 3.11 以上 · MIT ライセンス · CLI**

長い AI チャットには、重要な判断や試行錯誤が埋もれます。添付ファイルと生成物は文脈から切り離され、別の AI に作業を渡すと同じ説明を繰り返すことになります。**AI Memory Hub** は、明示的に許可した会話の文脈、証拠、プロジェクト状態、実ファイルのバイト列を、特定の AI 事業者から独立したローカル Vault に記録します。

## 解決したい課題

- **作業を再開しやすくする：** 目的、制約、決定、検証結果、未解決事項、次の手順を保存します。
- **出典を追跡する：** 保存内容には出典、履歴、証拠、ファイルの SHA-256 を関連付けます。
- **リンクだけでなく実ファイルを保存する：** ユーザーの添付物と AI の成果物をバージョン管理します。
- **エージェントを切り替えられる：** 承認した情報と特定バージョンのファイルだけを引き継ぎます。
- **取得範囲を選べる：** ソースと機密レベルを明示し、原文（L3）は別途承認します。

## V2.3 で利用できる機能

| 機能 | 内容 |
| --- | --- |
| 長期メモリ候補 | 事実、好み、決定の候補とレビュー。チャット本文を自動的に確定済み事実へ昇格させません |
| 会話の 4 層 | L0 索引、L1 要約、L2 詳細チェックポイント、任意の L3 出典付き可視メッセージ |
| プロジェクトの継続性 | 状態、判断、検証、未完了作業の履歴と引き継ぎ |
| ファイル保管 | 承認されたアップロード・AI 生成ファイルの実バイト、SHA-256 重複排除、履歴、検証付き取り出し |
| 入力アダプター | ローカル JSON、明示的マニフェスト、コーディング Agent の作業領域、取得済み ChatGPT JSON/対応 ZIP |
| AI 間の引き継ぎ | オフライン ZIP、双方の同意、指定 `ID@REV`、受信 Vault での実バイト確認 |
| 同期ポリシー | 週次・手動全量・イベント・日次・引き継ぎの 5 つの独立スイッチ |
| 障害復旧 | 重複しない再実行、出典と履歴の保存、バックアップ、復元、ロールバック検証 |

**実装済みと自動運用は別です。** Windows と Ubuntu の合成データテストを通過していますが、すべての AI のチャットを自動監視したり、クラウド同期や定期実行を勝手に設定する製品ではありません。

## V2.3：再利用できる完全な個人メモリワークスペース

V2.3 は Python エンジンだけではありません。**検証済みローカルエンジンと、利用者ごとに初期化できるワークスペース**を一体化しました。19 の組織モジュールに対応する中立的なテンプレートには `AGENTS.md`、`core/`、`memory/`、`candidates/`、`projects/`、`sessions/`、`assets/`、`life-archive/`、`integrations/`、`workflows/` などが含まれ、個人の実データは含みません。
人生記録は **12 分類・52 の下位領域・134 の登録フィールド**を備え、出典、期間、機密性を検証します。開始時の状態はすべて `unknown` です。長期メモリの候補は検証、重複・矛盾の確認、根拠付きの承認、**別操作による有効化**、取り消しと履歴管理を経ます。

### 自分のワークスペースを作る

Python 3.11 以上で V2.3 のソースディレクトリから実行します。Git 外に**独立したワークスペースと Vault**を作り、合成デモだけを配置します。デモのコピーだけではソースのアクセス権は付与されず、`source grant` が必要です。

```sh
python -m pip install .
ai-memory-hub workspace init --path ../workspace-demo-v23 --demo
ai-memory-hub workspace check --path ../workspace-demo-v23
ai-memory-hub --root ../workspace-demo-v23-vault source grant sample normalized --path ../workspace-demo-v23/demo-inbox --consent
ai-memory-hub --root ../workspace-demo-v23-vault local run --source sample
ai-memory-hub --root ../workspace-demo-v23-vault memory review
ai-memory-hub --root ../workspace-demo-v23-vault project list
ai-memory-hub --root ../workspace-demo-v23-vault local status
```

候補は自動的には確定済みの事実になりません。[ワークスペース導入](../workspace.md)、[19 モジュールの対応表](../workspace-parity.md)、[Agent 入口](../../AGENTS.md)、[人生記録フィールド](../../life-archive/field-registry.json)を参照してください。

### Agent 間のバージョン確認と候補管理

承認された記憶をローカルのスナップショットとして渡せます。受信側では `version check` が変更を検出し、`version reload` が変更範囲と一回限りの確認票を返し、`version confirm` で明示的に確認した後だけ `synced_sha` が更新されます。**検出した `detected_sha` は同期済みとは限りません**。読み取りできなければ `unknown` です。確認票は Agent の理解を証明せず、全 AI サービスへの自動接続も行いません。[接続とバージョン確認](../../integrations/memory-bootstrap.md)を参照してください。
`candidate suggest`、`candidate advance`、`candidate history` は根拠と許可を要する候補管理機能です。[メモリのライフサイクル](../../workflows/memory-lifecycle.md)も参照してください。健康拡張は**匿名化した集計の形式検証のみ**で、端末の原データ同期ではありません。ソフトウェアは **2.3.0**、既存 Vault の記録形式は **2.1**、新しいワークスペース形式は **1.0** です。

### L0–L3：会話を必要な深さだけ読む

| レベル | 保持する情報 | 主な用途 |
| --- | --- | --- |
| **L0 · 索引** | タイトル、会話 ID、関連プロジェクト、リビジョン | 関連する会話を探す |
| **L1 · 要約** | L0 に加え、提供された会話の概要 | 深く読む必要があるか判断する |
| **L2 · 詳細チェックポイント** | 目標、制約、決定、却下した案と理由、検証、未完了の行動、ファイル参照 | 長いチャットを再読せずプロジェクトを再開する |
| **L3 · 任意の原文** | 出典と履歴のある実際の可視メッセージ | 原文確認が必要なときだけ追加同意を得て読む |

これは自動生成した四種類の要約ではなく、**段階的に読むための情報層**です。L1/L2/L3 が保存されていなければ内容を創作しません。L3 は `private` または `restricted` の Vault と個別の承認が必要です。L2 を後で更新しても元の L3 を書き換えません。

**小さな工夫：** 候補の承認と事実の有効化は別操作。ファイルの URL と保管済みの実バイトを区別。Agent ごとに `detected_sha` と `synced_sha` を別々に維持。入力の再試行は項目単位の回执に基づき、未変更のデータを重複登録しません。

## アーキテクチャ

```mermaid
flowchart LR
  A["許可されたローカル出力 / マニフェスト / チェックポイント"] --> B["ソース許可とアダプター"]
  B --> C["L0–L3 · プロジェクト · 記憶候補"]
  B --> D["ファイル履歴 · SHA-256"]
  C --> E["ローカル Vault"]
  D --> E
  E --> F["確認済みのオフライン引き継ぎ"]
  F --> G["認可された受信側 Vault"]
```

**Vault** は Git リポジトリ外に作る利用者管理のローカルディレクトリで、SQLite の索引と内容ハッシュによるファイル保存を利用します。1 つの Vault は 1 つの機密区分を扱い、OS のアクセス制御で保護します。

L0 は会話の識別、L1 は概要、L2 は目標・決定・検証・次の行動、L3 は別途同意を得た実際の可視メッセージです。L2 を更新しても過去の L3 原文や出典は書き換えません。

## 活用例

**別の AI でプロジェクトを継続：** 課題、却下した案、検証結果、残作業を L2 に残し、確認した引き継ぎパッケージで受け渡します。ファイルは選択した版だけ転送できます。

**生成した成果物の保管：** ユーザーの元ファイルを `user_upload`、AI の生成物を `ai_generated` として登録し、後から同じバージョンを検証・復元します。

**ChatGPT の履歴を読み込む：** 公式手順で自身のエクスポートを取得し、そのローカル JSON/ZIP の読み取りを明示的に許可します。可視メッセージ本文には追加承認が必要で、添付ファイルは別途登録します。

## 5 分で試す（合成データ）

Python 3.11 以上が必要です。リポジトリをチェックアウトし、必要なら `python -m pip install .` を実行してください。Windows は PowerShell、Linux/macOS はターミナルを使用します。Vault は必ずリポジトリの**外**に作成してください。

```sh
python -m ai_memory_hub --root ../hub-demo init --preset ordinary
python -m ai_memory_hub --root ../hub-demo source grant demo normalized --path examples --consent
python -m ai_memory_hub --root ../hub-demo local run --source demo
python -m ai_memory_hub --root ../hub-demo local status
python -m ai_memory_hub --root ../hub-demo session show calibration-session --layer L2
python -m ai_memory_hub --root ../hub-demo asset check calibration-notes
python -m ai_memory_hub --root ../hub-demo asset copy calibration-notes --consent
```

`examples/memory-hub.json` にはファイルを含む 4 件の合成データがあります。再実行しても同じデータは重複登録されません。`asset copy` は検証済みファイルのコピーを Vault 内に作ります。

### 許可した実データの取り込み

Vault を初期化してから、`memory-hub.json` を持つ明示的なディレクトリを `source grant ID normalized --path PATH --consent` で登録し、`local run --source ID` を実行します。`local status` で読み取り結果と失敗・成功状態を確認します。
ChatGPT には `chatgpt_export` と取得済み `.json` / 対応 `.zip` を指定します。L3 を保存する場合のみ追加の `--allow-raw` を許可します。自動的なプラットフォーム監視機能はありません。詳細は[入力アダプター](../adapters.md)と[導入ガイド](../deployment.md)を参照してください。

### 別 Vault へのプロジェクト引き継ぎ

`handoff` は初期状態では無効です。両方の Vault で有効化し、転送するファイル版を個別に選びます。

```sh
python -m ai_memory_hub --root ../hub-demo config set handoff on
python -m ai_memory_hub --root ../hub-demo transfer pack --project greenhouse-demo --asset calibration-notes@1 --consent
python -m ai_memory_hub --root ../recipient init --preset ordinary
python -m ai_memory_hub --root ../recipient config set handoff on
python -m ai_memory_hub --root ../recipient transfer receive --input APPROVED_COPY.zip --consent
python -m ai_memory_hub --root ../recipient transfer inspect PACKAGE_ID --consent
python -m ai_memory_hub --root ../recipient transfer file PACKAGE_ID calibration-notes@1 --consent
```

`APPROVED_COPY.zip` は送信側が作成した、確認済みパッケージを安全な経路でコピーしたものです。`PACKAGE_ID` は受信時に返される識別子です。**ZIP は暗号化されません。** SHA-256 は完全性を検証しますが、送信者の本人確認にはなりません。L3 と未指定ファイルは送信されません。

## 5 つの独立スイッチ

| 設定 | 通常モードの初期値 | 動作 |
| --- | --- | --- |
| `weekly` | ON | 週次処理の入口。スケジューラー自体はインストールしません |
| `full` | ON | 手動の全量・選択ソース取り込み |
| `event` | OFF | 明示的なイベント呼び出し |
| `daily` | OFF | 任意の日次補完 |
| `handoff` | OFF | 明示的な引き継ぎ |

`config set FEATURE on|off` で変更します。`local run --source ID` は初期状態で `full` を使用します。クラウド側のメモリ管理タスクとローカルのアーカイブ実行は別です。スイッチが ON でも本番の定期実行が確認されたことにはなりません。

## プライバシー、制限、更新

Vault 自体にはアプリ内暗号化がなく、OS 権限・ディスク暗号化・バックアップ管理を利用者が設定します。ソースの許可を取り消すと今後の読み取りを止めますが、保存済み履歴は自動削除されません。オフライン ZIP は暗号化されないため、安全な転送手段と受信者の承認が必要です。URL 参照と、バイト列を実際に保存したファイルは別物です。
ソフトウェアの版は 2.3.0、既存レコードのスキーマは互換性のため `2.1` のままです。引き継ぎには別途 2.2 形式を使用します。アップグレード前にバックアップし、復元したコピーで試してください。

## ドキュメントと貢献

[導入・バックアップ・転送](../deployment.md) · [利用ガイド](../guide.md) · [アダプター](../adapters.md) · [データ仕様](../protocol.md) · [セキュリティ](../../SECURITY.md) · [MIT ライセンス](../../LICENSE)
開発や不具合報告には合成データを使い、個人のエクスポートや添付ファイルをコミットしないでください。テストは `python -m unittest discover -s tests -v`、`python scripts/smoke_release.py`、`python scripts/smoke_v22.py` で実行できます（必要に応じて `python -m pip install jsonschema`）。

**公開状況：** V2.3 のコアは実装・合成テスト済みですが、GitHub リポジトリの一般公開と正式な 2.3.0 Release は別の手続きです。
