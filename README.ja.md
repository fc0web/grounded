# grounded

**AIが書いた文章が、本当に原典に基づいているかを確認する。**

決定論的。オフライン。**検証する側にAIを使いません。**

```bash
grounded check answer.md --source contract.pdf --source notes/
```

```
EXACT CHECKS   (present in source, or fabricated)
  checked   31
  grounded  21
  NOT FOUND 10
  rate      67.7%

NOT FOUND IN ANY SOURCE
  ✗ [quote] audit trail review shall be completed within 24 hours of batch manufacture
  ✗ [citation] (Whitfield & Osei, 2024)
  ✗ [citation] arXiv:2401.99887
  ✗ [number] 2.3
  ✗ [entity] Whitfield

FAIL  10 claim(s) are not in any source.
```

終了コードは1。CIにも、コミット前フックにも、モデルが回答前に自分を点検する用途にも使えます。

---

## なぜAIによるファクトチェックではないのか

**モデルが自分の出力を採点すると、同じ方向に二度間違えることがあります。**

`grounded` は文章の意味を判断しません。**無ければ捏造だと言い切れるもの**――引用文、数値、出典表記、固有名詞――を取り出し、指定された文書の中を literal に探すだけです。**あるか、ないか。**判定する側に幻覚の余地がありません。

「ハルシネーションを検出する」より狭い約束ですが、**この道具が実際に守れる約束**です。

---

## インストール

```bash
pip install grounded                 # 本体。外部依存ゼロ
pip install "grounded[pdf]"          # + PDF対応
pip install "grounded[mcp]"          # + MCPサーバー
```

Python 3.10以上。ネットワーク接続、APIキー、モデルのダウンロード、GPU、いずれも不要です。**文書が端末の外に出ることはありません。**

---

## 使い方

### コマンドライン

```bash
# 1つの原典と照合する
grounded check answer.md -s manual.pdf

# 複数指定、ディレクトリごとも可
grounded check answer.md -s spec.pdf -s docs/ -s notes.md

# パイプから
cat draft.txt | grounded check - -s reference.pdf

# 機械可読な出力
grounded check answer.md -s manual.pdf --json

# 引用と出典だけを確認する
grounded check answer.md -s manual.pdf --kind quote --kind citation
```

### Python から

```python
from grounded import check

result = check(answer_text, ["manual.pdf", "notes/"])

if not result.passed:
    for f in result.failures:
        print(f"{f.claim.kind.value}: {f.claim.text}")
```

### MCPサーバーとして

**モデルが回答を出す前に、自分の下書きを検証できます。**

```json
{
  "mcpServers": {
    "grounded": { "command": "grounded-mcp" }
  }
}
```

| ツール | 内容 |
|---|---|
| `verify_against_sources` | 下書き全体を検証し、原典に無いものを返す |
| `check_quote` | 引用を1つだけ、使う前に確認する |
| `verify_audit_log` | 実行記録が改ざんされていないか確認する |

---

## 何を検証するのか

5種類の主張を、**厳密に分離された2つの層**で扱います。

### 厳密層 ― これが製品の中身です

| 種類 | 例 | 規則 |
|---|---|---|
| `quote` | `"shall not obscure previously recorded information"` | 逐語で存在すること |
| `number` | `$2.3 million`、`24 hours`、`15%`、`2,048` | 存在すること |
| `citation` | `[12]`、`(Smith, 2020)`、`arXiv:2401.99887`、DOI、URL、`21 CFR 11.10` | 存在すること |
| `entity` | `Ranbaxy`、`MHRA`、`ISO/IEC 17025` | 存在すること |

照合時に、大文字小文字、全角半角、引用符の種類、ダッシュの種類、空白を吸収します。**行の折り返しで途中改行された引用文も一致します**（ここを取り逃すと、最も重要な捏造がすり抜けます）。

`3 items` のような自明な数値は無視し、単位・小数点・桁区切りを伴うか、十分に長い数値だけを検証対象にします。

### 発見的層 ― 参考情報。既定では動きません

`sentence` は、原典との特徴語の重なりで採点します。低い点数は**捏造かもしれないし、良い言い換えかもしれません**。明示的に要求しない限り失敗扱いにせず、厳密層と混同されないよう別の区画に表示します。

---

## この道具が「やらないこと」

**過大に主張する検証ツールは、無いより悪い**ので、はっきり書きます。

- **言い換えが忠実かどうかは判定しません。** 原典が「売上は減った」なのに「売上は伸びた」と書いても、語が別の箇所にあれば通ります
- **推論や計算の正しさは見ません。** 正しく引用した数値を誤った結論に使っても通ります
- **原典が正しいかは知りません。** 渡された文書との一致を見るだけです
- **盗用検出ではありません。** 向きが逆で、ここでは一致することが**良い**結果です
- **スキャンPDFは読めません。** 先にOCRしてください。テキストが取れないページは、空として扱わず**エラーにします**。空の原典は全ての記述を捏造に見せてしまい、それがこの道具に絶対あってはならない失敗だからです

---

## 監査ログ

任意機能です。実行ごとに、ハッシュ連鎖した追記専用ファイルに1行を追加します。過去の記録を書き換えると、**その位置で連鎖が壊れて検出されます**。

```bash
grounded check answer.md -s manual.pdf --log .grounded/audit.jsonl \
  --at "2026-08-17T14:03:00+09:00"

grounded audit --log .grounded/audit.jsonl -v
```

時刻は時計から読まず**呼び出し側が渡します**。実行が再現可能でテスト可能になるためです。

これは改ざん**耐性**ではなく改ざん**検知**です。ファイル全体を書き直せる人なら整合した連鎖を作り直せます。「この記録は後から書き換えられたか」に答えるものであって、「本気の攻撃者が偽造できないか」に答えるものではありません。

---

## 終了コード

| コード | 意味 |
|---|---|
| `0` | 厳密層の全主張が見つかった（または `--no-fail` 指定時） |
| `1` | 原典に無い主張が1件以上ある |
| `2` | 原典が読めなかった ― **検証は実行されていません** |

`2` を区別しているのは意図的です。**原典が読めなかったことを「全部捏造」と報告してはいけません。**

---

## 試す

原典1つ、それを正しく要約したもの1つ、捏造を混ぜたもの1つが同梱されています。

```bash
grounded check examples/answer_grounded.md   -s examples/source.md   # PASS 40/40
grounded check examples/answer_fabricated.md -s examples/source.md   # FAIL 10件
```

**10件すべてが本物の捏造であり、正しい要約では誤検出がゼロ**です。この2つの性質を守るためにテストがあります。

---

## 開発

```bash
git clone https://github.com/fc0web/grounded
cd grounded
pip install -e ".[dev]"
pytest
```

特に歓迎する貢献：

- 出典表記の形式追加（法律、医学、非英語圏の学術）
- 英語・日本語以外の言語対応
- **誤検出の報告** ― 正しい記述を捏造と報告することが、この道具にとって最も重大なバグです

---

## ライセンス

MIT
