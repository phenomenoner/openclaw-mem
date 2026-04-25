# Memory your agent can’t lie about

<div class="ocm-hero" markdown="1">

<div class="ocm-eyebrow">LOCAL-FIRST MEMORY FOR OPENCLAW OPERATORS</div>

# A local ledger you can grep, diff, and roll back.

`openclaw-mem` captures what happened, makes it searchable, and packs the right context back into the agent with cited audit records. Start as a sidecar beside OpenClaw. Promote it to the memory slot only when it earns the seat.

<div class="ocm-pills" markdown="1">
<span>JSONL + SQLite</span>
<span>5-minute local demo</span>
<span>Sidecar first</span>
<span>Optional hybrid engine</span>
</div>

<div class="ocm-terminal" markdown="1">
```text
$ openclaw-mem search "privacy timezone style" --json
{"matches": [{"kind": "preference", "source": "synthetic-demo.jsonl"}]}
```
</div>

<div class="ocm-ctas" markdown="1">
[Verify in 60 seconds](reality-check.md){ .md-button .md-button--primary }
[Read the quickstart](quickstart.md){ .md-button }
[Choose an install path](install-modes.md){ .md-button }
</div>

</div>

!!! tip "中文一句話"
    `openclaw-mem` 是給 OpenClaw 的本地優先記憶層：把工具結果、決策、偏好與操作痕跡變成可搜尋、可引用、可回滾的記憶，而不是把一切丟給黑盒向量庫。

## Start here: one operator path

If you are evaluating `openclaw-mem`, take the shortest trustworthy route:

1. **Verify the local proof** — run the [60-second reality check](reality-check.md) with a temporary SQLite DB.
2. **Install the sidecar** — follow the [quickstart](quickstart.md), then choose a [sidecar / engine / hybrid install path](install-modes.md).
3. **Check what is automatic** — read the [automation status](automation-status.md) before assuming anything is wired into the live agent loop.
4. **Track the product arc** — use the [product-facing roadmap](openclaw-user-improvement-roadmap.md) for current gaps and next bets.

## What runs automatically today?

| Surface | Status | Operator meaning |
| --- | --- | --- |
| Sidecar observation capture | Automatic when the plugin is enabled | Captures JSONL observations, backend annotations, and denoised tool/action receipts. |
| Harvest / triage / graph capture jobs | Scheduled on configured hosts | Turns captured records into searchable stores and maintenance receipts. |
| `pack`, graph routing, optimize assist, continuity tools | Available as CLI or opt-in lanes | Powerful, but not assumed to be in every live agent turn unless explicitly promoted. |
| Mem-engine Proactive Pack | Optional promotion path | Adds bounded pre-reply recall orchestration without making graph/docs a competing truth store. |

This split is intentional: **Store / Pack / Observe** stays inspectable, and automation is promoted only when it has receipts.

## The promise

Most agent memory demos feel magical until the first production question lands:

- **Why did the agent remember this?**
- **Where did that fact come from?**
- **Can I inspect, export, or roll it back?**
- **Can I keep fresh local recall without paying a remote semantic tax every time?**

`openclaw-mem` is built for that moment. It is not a hosted memory cloud. It is an operator-grade memory layer you can run, diff, test, and reason about.

## Proof shape

A memory layer should show its work. The core loop stays deliberately plain:

```bash
openclaw-mem search "timezone privacy demo style" --json
openclaw-mem timeline --limit 5 --json
openclaw-mem pack "write the demo plan" --json
```

Expected shape:

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

No mystery memory blob. Just records, search, timelines, and compact packs the agent can cite.

## What you get

<div class="ocm-grid" markdown="1">

<div class="ocm-card" markdown="1">
### 1. Store the trail
Capture observations into append-only JSONL, ingest them into SQLite, and keep durable receipts for tool outcomes, decisions, preferences, specs, and ops breadcrumbs.

**中文：** 先把脈絡留下來，而且留下的是可檢查的紀錄。
</div>

<div class="ocm-card" markdown="1">
### 2. Find the signal
Search locally with FTS, inspect timelines, fetch exact records, and avoid asking a remote model to rediscover context you already own.

**中文：** 先本地搜尋，先看證據，再決定要不要升級語意召回。
</div>

<div class="ocm-card" markdown="1">
### 3. Pack context with receipts
Build compact `ContextPack` bundles for the agent, with cited memories instead of mystery prompt stuffing.

**中文：** 回填給 agent 的不是一坨雜訊，而是可引用、可追蹤的上下文包。
</div>

<div class="ocm-card" markdown="1">
### 4. Upgrade only when it pays
Keep the sidecar as the safe default. Add the optional memory engine for hybrid recall, scoped retrieval, and policy-aware automation when you need more power.

**中文：** 預設不搶 slot；真的需要 hybrid engine 時再升級。
</div>

</div>

## Why it is different

| If you are comparing... | The difference |
| --- | --- |
| Hosted memory APIs | `openclaw-mem` is local-first and inspectable by default, not a required SaaS hop. |
| Raw vector databases | It stores operational records and builds cited context packs, not just embeddings. |
| Plain logs | It gives search, timeline, get, and pack flows designed for agent recall. |
| Full agent runtimes | It starts as a sidecar beside OpenClaw instead of replacing your whole runtime. |
| Native OpenClaw memory slots | It does not have to own the slot. It can observe first, then promote only if justified. |

| If you need... | `openclaw-mem` gives you... |
| --- | --- |
| A memory layer you can inspect | JSONL + SQLite + CLI audit records |
| Fresh local recall | fast ingest and local search before remote semantics |
| Safer agent context | compact packs with provenance instead of opaque memory blobs |
| Rollback posture | sidecar-first adoption, explicit engine promotion, exportable artifacts |
| Operator control | no forced SaaS, no forced slot ownership, no “remember everything forever” default |

## Words we mean precisely

- **Sidecar**: a local companion layer that captures and searches memory records without owning OpenClaw’s active memory backend.
- **Memory slot**: the backend OpenClaw asks when it needs memory. The sidecar does not need to replace it.
- **Ingest / harvest**: scheduled import from captured JSONL into searchable SQLite.
- **Audit record / receipt**: a small record that says what happened, where it came from, and how to cite it.
- **ContextPack**: a compact, cited bundle of relevant memories prepared for the agent.

## When not to use it

If your agent only has one short chat, no ops trail, no audit need, and no repeated context to recover, the model context window is probably enough. `openclaw-mem` is for the moment memory becomes operational infrastructure.

## See it, don’t just believe it

Start with the [60-second reality proof](reality-check.md), then use these deeper demos when you want to inspect richer behavior.

<div class="ocm-grid" markdown="1">

<div class="ocm-card" markdown="1">
### 5-minute Inside-Out demo
A synthetic, privacy-safe demo showing how stable preferences and constraints become a cited context pack.

[Open the demo](showcase/inside-out-demo.md)
</div>

<div class="ocm-card" markdown="1">
### Topology-aware recall
Use docs and topology surfaces to answer “where is this implemented?” without polluting durable memory.

[See topology demo](showcase/topology-demo.md)
</div>

<div class="ocm-card" markdown="1">
### Reality check
The docs separate what is shipped, partial, experimental, and roadmap. No fake maturity theater.

[Check current status](reality-check.md)
</div>

</div>

## 中文展示版

### 給 OpenClaw operator 的記憶基礎設施

如果你已經讓 agent 做長線工作，你要的不是「它好像記得」，而是：

- 記憶來源可以追；
- 召回結果可以查；
- 上下文可以打包；
- 錯了可以回滾；
- 本地資料不用被迫送進黑盒雲端。

`openclaw-mem` 的產品楔子很簡單：**讓 agent 的長期脈絡變成一條可驗證的操作鏈。**

先用 sidecar 捕捉與搜尋，證明價值後，再把 optional engine 打開做 hybrid recall 與更細的 policy 控制。這樣你得到的是「可治理的記憶」，不是另一個難以解釋的魔法層。

## 中文對外定位

**會留底的代理人記憶。** 擷取是 JSONL，召回是 `search → timeline → get`，上下文打包有 citation。五分鐘從 sidecar 起步；要不要升格成主記憶，看它有沒有掙到那個位子。


## Current proof pack

If you are evaluating the project beyond the 5-minute demo, start with the current proof assets:

- [Trust-aware pack proof](showcase/trust-aware-context-pack-proof.md)
- [Command-aware compaction proof](showcase/command-aware-compaction-proof.md)
- [Metrics JSON](showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](showcase/artifacts/index.md)
- [Proactive Pack](proactive-pack.md)
- [Portable pack capsules](portable-pack-capsules.md)

## Adoption path

1. **Run the demo** — prove the recall-and-pack contract on synthetic data.
2. **Install the sidecar** — capture and harvest observations beside your current OpenClaw memory slot.
3. **Use local recall first** — search, timeline, get, and pack before reaching for heavier systems.
4. **Promote carefully** — enable the optional engine only when hybrid recall and policy controls justify the added surface.

## Start here

- [Inside-Out demo](showcase/inside-out-demo.md) — fastest proof of the product contract
- [Choose an install path](install-modes.md) — sidecar, engine, or hybrid adoption
- [Quickstart](quickstart.md) — CLI-first local setup
- [Reality check & status](reality-check.md) — honest maturity map
- [Deployment guide](deployment.md) — production-oriented wiring

## Repository and releases

- [GitHub repository](https://github.com/phenomenoner/openclaw-mem)
- [GitHub releases](https://github.com/phenomenoner/openclaw-mem/releases)
