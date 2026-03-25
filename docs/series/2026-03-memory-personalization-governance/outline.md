# Series outline

## Core thesis
好的 LLM 記憶不是更會想起你，而是更知道什麼時候不該把想起來的東西說出口。

## Part 1 — 問題的脈絡：LLM 記憶為什麼開始讓人煩
- Karpathy 那句 "trying too hard" 在抱怨什麼
- 這不是單純 forgetting，而是 over-remembering / over-mentioning
- 為什麼這個問題現在更明顯：persistent memory、agent products、跨 session personalization、長上下文錯覺
- 四段式診斷：寫入過寬、分類過粗、檢索過鬆、表達過度
- 為什麼「正確的記憶」也可能造成錯的 UX

## Part 2 — 已知解法：大家都會列，但每一招都只解一部分
- 記憶衰減 / lifecycle
- 記憶分級 / typed memory
- selective retrieval / activation gating
- mention policy / strategic silence
- user-controlled memory / explainability
- trust / provenance / quarantine
- dream / consolidation 的吸引力與風險
- 工程現實：每多一層治理，都有 latency、成本、維運複雜度

## Part 3 — `openclaw-mem` 的實戰經驗：從「多記一點」轉向「小而可信的 context pack」
- 為什麼產品故事不是 generic memory storage
- L1/L2/L3 分層：durable memory、docs、topology
- retention vs activation split
- Working Set backbone + hot recall quota + repeat penalty
- trust-aware context packing：smaller / safer / cited
- episodic retention defaults 與 operator legibility
- 做對了什麼、還沒做完什麼

## Part 4 — 待解問題與未來方向：從 recall engine 走向 memory governance
- 如何讓 personalization 隨時間演化，而不是黏住舊訊號
- 如何把 "should retrieve" 與 "should mention" 拆開變成可解釋 contract
- consolidation / dream 應該是候選生成器，不該黑盒改寫 canonical memory
- 需要什麼 benchmark：不只量 recall，還要量 suppression、abstention、context-appropriate application
- 長期方向：讓 memory system 像一個有門禁、可審計、可撤回的治理層，而不是更大的 prompt 背包
