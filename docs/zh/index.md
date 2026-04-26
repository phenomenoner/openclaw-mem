---
canonical: https://phenomenoner.github.io/openclaw-mem/
lang: zh-Hant
---

> **English is canonical.**  
> 本頁是獨立撰寫的繁體中文產品說明，方便中文讀者快速理解 `openclaw-mem`。若內容與英文文件有出入，請以 [English home](../index.md) 與 [README](https://github.com/phenomenoner/openclaw-mem#readme) 為準。

# 會留底的代理人記憶

<div class="ocm-hero" markdown="1">

<div class="ocm-eyebrow">給 OPENCLAW OPERATOR 的本地優先記憶層</div>

# 一條可以 grep、diff、回滾的本地帳本。

`openclaw-mem` 把代理人做過的事留下來，變成可搜尋、可引用、可回滾的操作記憶。它先以 sidecar 形式跑在 OpenClaw 旁邊，不急著取代你現有的記憶後端；等本地召回、引用收據與上下文打包真的證明價值，再考慮升級成選用的 Mem Engine。

<div class="ocm-pills" markdown="1">
<span>JSONL + SQLite</span>
<span>五分鐘本地展示</span>
<span>Sidecar 優先</span>
<span>選用混合引擎</span>
</div>

<div class="ocm-terminal" markdown="1">
```text
$ openclaw-mem search "privacy timezone style" --json
{"matches": [{"kind": "preference", "source": "synthetic-demo.jsonl"}]}
```
</div>

<div class="ocm-ctas" markdown="1">
[看五分鐘展示](../showcase/inside-out-demo.md){ .md-button .md-button--primary }
[選擇安裝模式](../install-modes.md){ .md-button }
[閱讀快速開始](../quickstart.md){ .md-button }
</div>

</div>

## 它解決什麼問題

多數 agent memory demo 一開始都很神奇，直到第一個真正的營運問題出現：

- 代理人為什麼記得這件事？
- 這個事實從哪裡來？
- 我能不能檢查、匯出、回滾？
- 我能不能先做本地召回，而不是每次都把問題丟給遠端語意服務？

`openclaw-mem` 是為這個時刻設計的。它不是代管記憶雲，也不是另一個黑盒向量庫；它是一個 operator-grade 的記憶層，可以在本地執行、搜尋、比對、測試，並把上下文帶著引用收據交還給 agent。

## 核心迴路

記憶層應該展示它如何工作。`openclaw-mem` 的基本迴路刻意保持樸素：

```bash
openclaw-mem search "timezone privacy demo style" --json
openclaw-mem timeline --limit 5 --json
openclaw-mem pack "write the demo plan" --json
```

預期形狀像這樣：

```json
{
  "query": "timezone privacy demo style",
  "matches": [
    {
      "id": "demo-preference-001",
      "kind": "preference",
      "summary": "Use Asia/Taipei for time references",
      "source": "synthetic-demo.jsonl"
    }
  ],
  "pack": {
    "token_budget": 900,
    "citations": ["demo-preference-001"]
  }
}
```

你得到的不是神秘的「記憶 blob」，而是一組可以追的紀錄：搜尋結果、時間軸、單筆內容，以及帶 citation 的 `ContextPack`。

## 你會得到什麼

<div class="ocm-grid" markdown="1">

<div class="ocm-card" markdown="1">
### 1. 留下操作軌跡
把工具結果、決策、偏好、規格與操作痕跡捕捉成 append-only JSONL，再匯入 SQLite，形成可查證的本地記憶帳本。
</div>

<div class="ocm-card" markdown="1">
### 2. 先找本地信號
用本地 FTS 搜尋、看 timeline、取回精確紀錄。先檢查自己已經擁有的上下文，再決定是否需要更重的語意召回。
</div>

<div class="ocm-card" markdown="1">
### 3. 帶收據打包上下文
`pack` 產生精簡的 `ContextPack`，讓 agent 拿到有來源、有 citation、可追溯的上下文，而不是一團無法解釋的 prompt stuffing。
</div>

<div class="ocm-card" markdown="1">
### 4. 值得時才升級
預設採用 sidecar-first。只有在 hybrid recall、範圍檢索與 policy controls 真的值得時，才把選用的 Mem Engine 推上 memory slot。
</div>

</div>

## 跟其他方案有什麼不同

| 如果你正在比較 | `openclaw-mem` 的差異 |
| --- | --- |
| 代管記憶 API | 預設本地優先，不強迫走 SaaS 中轉。 |
| 原始向量資料庫 | 儲存操作紀錄並產生可引用的上下文包，不只是 embeddings。 |
| 純文字 log | 提供為 agent recall 設計的 `search → timeline → get → pack` 流程。 |
| 完整 agent runtime | 先作為 OpenClaw 旁邊的 sidecar，不需要替換整個 runtime。 |
| OpenClaw 原生 memory slot | 不必第一天就佔 slot；可以先觀察、驗證，再升級。 |

| 如果你需要 | `openclaw-mem` 給你 |
| --- | --- |
| 可檢查的記憶層 | JSONL + SQLite + CLI audit records。 |
| 新鮮的本地召回 | 先快速 ingest 與本地搜尋，再考慮遠端語意。 |
| 更安全的 agent context | 有 provenance 的精簡 context packs，而不是不透明 memory blobs。 |
| 回滾姿態 | Sidecar-first adoption、明確的 engine promotion、可匯出的 artifacts。 |
| Operator control | 不強迫 SaaS、不強迫 slot ownership，也不預設永遠記住一切。 |

## 看見它，而不只是相信它

<div class="ocm-grid" markdown="1">

<div class="ocm-card" markdown="1">
### 五分鐘 Inside-Out demo
用合成、隱私安全的資料展示：穩定偏好與限制如何變成帶 citation 的 context pack。

[開啟 demo](../showcase/inside-out-demo.md)
</div>

<div class="ocm-card" markdown="1">
### Topology-aware recall
用 docs 與 topology surface 回答「這個功能實作在哪裡？」，而不污染 durable memory。

[查看 topology demo](../showcase/topology-demo.md)
</div>

<div class="ocm-card" markdown="1">
### Reality check
文件明確分開 shipped、partial、experimental 與 roadmap，避免成熟度劇場。

[查看目前狀態](../reality-check.md)
</div>

</div>

## 採用順序

1. **先跑 demo**：用 synthetic data 驗證 recall-and-pack contract。
2. **安裝 sidecar**：在現有 OpenClaw memory slot 旁邊捕捉與 harvest observations。
3. **先用本地 recall**：優先使用 `search`、`timeline`、`get`、`pack`，再考慮更重的系統。
4. **謹慎升級**：只有在 hybrid recall 與 policy controls 值得時，才啟用選用 Mem Engine。

## 三種安裝模式

### 1. 單一 repo 的本地驗證

適合只想確認產品是否真的有用：clone repo、產生 sample JSONL、匯入 SQLite、跑本地搜尋，不需要改 OpenClaw 設定。

### 2. 既有 OpenClaw 安裝上的 sidecar

適合已經在跑 OpenClaw、想改善 capture freshness、observability 與 rollback posture 的 operator：保留目前 memory slot，啟用 capture plugin，排程 harvest，再用 `openclaw-mem` 做本地 recall、triage 與 receipts。

### 3. 升級到選用 Mem Engine

適合想讓 `openclaw-mem` 接管 memory slot 的進階用法：先通過 sidecar smoke test，再切到 `openclaw-mem-engine`，取得 hybrid recall、bounded automation 與 operator-tunable policies。回滾仍應保留為一行 slot change。

## 精確詞彙

- **Sidecar**：本地伴隨層，捕捉與搜尋記憶紀錄，但不擁有 OpenClaw 的現用 memory backend。
- **Memory slot**：OpenClaw 需要 memory 時會查詢的後端。sidecar 不需要取代它。
- **Ingest / harvest**：把捕捉到的 JSONL 匯入可搜尋的 SQLite。
- **Audit record / receipt**：描述發生了什麼、從哪裡來、如何引用的小型紀錄。
- **ContextPack**：為 agent 準備的精簡上下文包，包含相關記憶與 citations。

## 什麼時候不需要它

如果你的 agent 只有一段短對話，沒有長期操作軌跡、沒有稽核需求，也沒有需要反覆恢復的上下文，那模型自己的 context window 可能就夠了。`openclaw-mem` 是給「記憶已經變成操作基礎設施」的情境。

## 從這裡開始

- [Inside-Out demo](../showcase/inside-out-demo.md)：最快驗證 recall-and-pack contract。
- [Choose an install path](../install-modes.md)：選 sidecar、engine 或 hybrid adoption。
- [Quickstart](../quickstart.md)：CLI-first 的本地 setup。
- [Reality check & status](../reality-check.md)：目前 maturity map。
- [Deployment guide](../deployment.md)：production-oriented wiring。

## 倉庫與版本

- [GitHub repository](https://github.com/phenomenoner/openclaw-mem)
- [GitHub releases](https://github.com/phenomenoner/openclaw-mem/releases)
