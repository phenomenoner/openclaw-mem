# Part 2｜已知解法：大家都會列，但每一招都只解一部分

上一篇把問題拆成四層：寫入太寬、分類太粗、檢索太鬆、表達太前台。這一篇要談的是，為什麼現在討論區裡那些常見答案幾乎都不算錯，但也幾乎都只打到局部。

memory personalization 不是一條 bug，而是一條多階段 pipeline 的治理問題。所以沒有哪一招能包打天下。

## 1. 記憶衰減：必要，但比較像垃圾回收，不是整個治理系統
Decay 是最直覺的一招：
- 舊訊號隨時間淡化
- 沒再被提起的內容就降權
- 長期沒被用到的內容就 archive 或冷藏

### 它能解什麼
- 降低舊話題長期佔據 recall
- 防止記憶庫無限膨脹
- 讓近期與高使用訊號有機會往前排

### 它解不了什麼
- 一開始就把錯的東西寫進 durable memory
- 檢索時機太寬
- 召回後還硬要說出口
- 低信任內容重新進 prompt

所以 decay 很重要，但它比較像 memory system 的 **lifecycle hygiene**，不是治理本身。

## 2. 記憶分級：比 decay 更接近正解，但前提是真的分對
不是每種「被記住的東西」都應該享有同樣待遇。最少至少要分：
- **stable profile / standing facts**：長期身份、明確偏好、穩定規則
- **episodic memory**：某次對話、某次事件、某次短期興趣
- **working memory / task state**：只對當前任務有效的上下文
- **docs / reference knowledge**：應該回頭查文件，而不是升格成個人記憶的內容
- **negative / suppressive memory**：不要再提、已過期、已被推翻、曾造成干擾的訊號

### 它能解什麼
- 不同記憶類型可以有不同 retention policy
- episodic 與 durable 不必搶同一個 recall budget
- 文件知識不會跟個人偏好混在一起

### 它解不了什麼
- tier 內部怎麼排序仍然可能很差
- retrieval 仍然可能過度寬鬆
- 回答仍然可能過度表現記憶

所以 memory typing 解的是 **結構混亂**，不是全部。

## 3. Selective retrieval：讓 recall 不再是大水漫灌
很多壞體驗不是資料庫裡垃圾太多，而是 context injection 太貪心。Selective retrieval 的精神是：
- 不是每次都把所有 memory 都當成可用候選
- 更不是只要相關就應該進 prompt
- 要讓對這一輪真的有幫助的項目有機會出頭

常見做法包括：
- scope isolation
- working set backbone
- recent / relevant / durable quota mixing
- repeat penalty
- trust / provenance gating

### 它能解什麼
- prompt bloat
- 同一批 durable memory 每輪都洗版
- turn-specific relevance 被 static profile 蓋過

### 它解不了什麼
- 上游寫入品質太差
- generation prompt 仍鼓勵模型「有記憶就要拿出來用」

Selective retrieval 很重要，因為它把 recall 從倉庫式回填，變成有門禁的選拔。

## 4. Mention policy：最常被忽略，但最直接決定 UX
這其實是我認為目前業界最欠帳的一層。

很多系統會做到：
- 有 memory
- 有 retrieval
- 有 ranking
- 有 context injection

但缺少一個獨立問題：

> 就算這條 memory 被召回了，現在真的應該把它說出口嗎？

有些記憶只適合當背景 prior：
- 幫助排序
- 幫助排除錯方向
- 幫助維持語氣一致

但它們不該直接變成一句「你之前好像很喜歡 X」。

如果沒有 mention policy，很多產品再怎麼優化 retrieval，最後還是會把 recall 做成「我知道你以前怎樣，所以我現在又要 cue 一次」。

Karpathy 講的 trying too hard，本質上就是這個 gate 沒立起來。

## 5. 使用者可控記憶：不是只有可編輯，還要可解釋
很多人提「讓使用者可以編輯 memory」，我基本同意，因為黑盒記憶最糟的地方是它不給你治理權。

但如果只做到可編輯，還不夠。更完整的要求應該是：
- **可看見**：它到底存了什麼
- **可編輯**：你可以改、刪、撤回
- **可解釋**：它為什麼這次被召回
- **可抑制**：你可以說這條不要再主動提

memory UI 不只是記憶清單，而應該是一個治理面板。

## 6. Trust / provenance：很多 personalization 問題，其實也在問「誰有資格重回 prompt」
如果一段低信任、低品質、甚至帶污染風險的內容，也能在未來被 recall 回來，那 personalization 失敗就不只是煩，而會變危險。

這也是為什麼 trust/provenance 不能只拿來防 prompt injection，它同樣應該進入 memory system。這一層在處理的是：
- 哪些東西可以被存
- 哪些東西可以被撈
- 哪些東西即使文本很像，也不該重回上下文

selection quality 常常比 storage quantity 更重要。

## 7. Auto dream / consolidation：方向有魅力，但風險比想像大
這條線很容易讓人興奮，因為它很像人腦：
- 白天接收碎片
- 夜裡壓縮整理
- 把 episodic 痕跡重組成較穩定的抽象知識

它的吸引力是真的：
- 去重
- 壓縮
- 連結
- 形成較穩定的候選 profile

但最大的風險也在這裡：它很容易從雜訊中 **夢出一個人設**。

幾次偶發查詢、幾個短期情緒、一些相近但不穩定的偏好，經過 consolidation 之後，可能被濃縮成「使用者長期很在意 X」。一旦這些抽象結論再反過來影響 retrieval 與 generation，錯誤就會從一次性噪音升級成長期錯誤。

所以我的態度很簡單：

> consolidation 可以做，但先當 candidate generator，不要直接改寫 canonical memory。

## 8. 工程現實：每多一層治理，都有成本
談 memory 解法，不能假裝這只是概念設計。每加一層治理，通常都會多出至少一個代價：
- 延遲更高
- ranking 更複雜
- receipts 更難做清楚
- operator surface 更多
- 維運與 rollback 更麻煩

所以真正成熟的 memory system，往往不是功能最多，而是知道哪幾層值得先做、哪幾層應該後做。

如果以優先級來看，我會這樣排：
1. 先把 durable / docs / topology / episodic 分開
2. 再把 retention 與 activation 分開
3. 再做 selective retrieval 與 repeat suppression
4. 再把 mention policy 明文化
5. 最後才談 dream / consolidation 這類更黑盒的層

## 這篇的結論
如果只記一件事，那就是：

> 所有已知解法都不是錯，只是它們各自處理的是不同層的問題。

- decay 在處理生命周期
- typing 在處理結構
- retrieval gating 在處理注入品質
- mention policy 在處理使用者實際感受到的干擾
- trust / provenance 在處理哪些內容有資格回來
- user control 在處理治理權
- consolidation 在處理壓縮與演化，但也帶來更大黑盒風險

真正成熟的設計，不是從中挑一招神藥，而是承認 memory 是一個治理堆疊。

下一篇，我們來看 `openclaw-mem` 的實戰：哪些方向已經走對，哪些地方仍然只是半成品。