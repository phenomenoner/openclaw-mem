# Positioning

## Series working title
記憶太用力：LLM 個人化為什麼常常「trying too hard」

## Positioning statement
給正在碰長對話、個人化、agent 記憶的技術操作者與產品讀者，這是一組拆解 **LLM personalization overreach** 的長文：它不是在討論模型「有沒有記住你」，而是在討論系統如何因為寫入過寬、分類過粗、檢索過鬆、表達過度，而把原本該幫助對話的記憶變成干擾。和一般 AI 記憶文章不同，這組文章不把答案簡化成「加 decay 就好」，而是把問題拉回可驗證的 context/memory orchestration，並用 `openclaw-mem` 的實戰設計與限制來談哪些方法真的站得住。

## Target reader
- 智慧但不一定天天寫 LLM infra 的讀者
- 在做 agent、memory、personalization、RAG、context orchestration 的工程/產品操作者
- 對「黑盒記憶」有直覺疑慮，想知道系統層面真正卡在哪的人

## Desired outcome
讀完後，讀者應該接受四件事：
1. Karpathy 指到的不是單純 forgetting，而是 **memory overreach**。
2. 問題不只在 decay，而在整個 memory stack：寫入、分類、檢索、表達。
3. 好的記憶系統不是記得越多越好，而是 **該沉默時會沉默**。
4. `openclaw-mem` 的價值更像 **trust-aware context packing + memory governance**，不是粗暴地把更多記憶塞回 prompt。

## Success criteria
一篇好的系列至少要做到：
- 不把問題講成「模型很笨」或「多加一個 memory database 就解決」
- 清楚區分 retention、activation、retrieval、mention 這幾個層次
- 說清楚現有解法各自能解什麼、解不了什麼
- 誠實寫出 `openclaw-mem` 已做、未做、做了但仍不夠的地方
- 對未來方向有判斷，不做空泛 roadmap 許願

## Series spine
**好的 LLM 記憶不是更會想起你，而是更知道什麼時候不該把想起來的東西說出口。**
