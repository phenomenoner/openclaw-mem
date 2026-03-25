# Part 2｜已知解法：大家都會列，但每一招都只解一部分

上一篇把問題拆成四層：寫入太寬、分類太粗、檢索太鬆、表達太前台。這一篇要談的是，為什麼現在討論區裡常見的解法幾乎都不算錯，但也幾乎都只打到局部。

如果把 memory personalization 問題理解成單一 bug，就很容易得出單一藥方。現實剛好相反：它是一條多階段 pipeline 的治理問題，所以沒有哪一招能包打天下。

## 1. 記憶衰減：必要，但只是垃圾回收，不是整個治理系統
這是最直覺的一招。

思路很簡單：
- 舊訊號隨時間淡化
- 沒再被提起的內容就降權
- 長期沒被用到的內容就 archive 或冷藏

這一招的重要性不能否認。因為如果系統完全沒有 decay，很多一次性事件會永久霸榜，最後 memory store 變成一個只進不出的倉庫。

但 decay 的侷限也很明顯。

### 它能解什麼
- 降低舊話題長期佔據 recall
- 防止 DB 無限膨脹
- 讓近期與高使用訊號有機會往前排

### 它解不了什麼
- 一開始就把錯的東西寫進 durable memory
- 檢索時機太寬鬆
- 召回了之後還硬要說出口
- 低信任內容重新進 prompt

所以 decay 很重要，但比較像是 memory system 的 **垃圾回收與生命周期管理**，不是決定一切的智慧核心。

## 2. 記憶分級：比 decay 更接近正解，但需要真的分對
很多討論會講 memory tiers。這方向通常比單談 decay 更接近工程真相。

因為不是每種「被記住的東西」都應該享有同樣待遇。

最少至少要分成幾類：
- **穩定 profile / standing facts**：長期身份、明確偏好、穩定規則
- **episodic memory**：某次對話、某次事件、某次短期興趣
- **working memory / task state**：只對當前任務有效的上下文
- **docs / reference knowledge**：應該回頭查文件，不該升格成個人記憶的內容
- **negative / suppressive memory**：不要再提、已過期、已被推翻、曾造成干擾的訊號

這一層做對，很多混亂自然會下降。

### 它能解什麼
- 不同記憶類型可以有不同 retention policy
- episodic 與 durable 不必搶同一個 recall budget
- 文件知識不會跟個人偏好混在一起

### 它解不了什麼
- tier 內部怎麼排序仍然可能很差
- 即使分類對了，retrieval 還是可能過度寬鬆
- 就算 retrieval 對了，回答仍然可能過度表現記憶

所以 memory typing 很重要，但它解的是 **結構混亂**，不是全部。

## 3. Selective retrieval：讓 recall 不再是大水漫灌
很多壞體驗其實不是因為資料庫裡真的有太多垃圾，而是因為每次 context injection 都太貪心。

Selective retrieval 的核心精神是：
- 不是每次都把所有 memory 都看成可用候選
- 更不是只要相關就應該進 prompt
- 要讓當下 turn 真正有幫助的項目有機會出頭

這裡常見的做法包括：
- scope isolation
- working set backbone
- recent / relevant / durable 的 quota mixing
- repeat penalty
- trust / provenance gating

### 它能解什麼
- prompt bloat
- 同一批 durable memory 每輪都洗版
- turn-specific relevance 被 static profile 蓋過

### 它解不了什麼
- 上游寫入品質太差
- system prompt / response policy 仍鼓勵模型「有記憶就要拿出來用」

Selective retrieval 是把 recall 從「倉庫式回填」變成「有門禁的選拔」。它非常重要，但還不是最後一道門。

## 4. Mention policy：最常被忽略，但最直接決定 UX
這其實是我認為目前業界最欠帳的一層。

很多系統會做到：
- 有 memory
- 有 retrieval
- 有 ranking
- 有 context injection

但缺少一個獨立問題：

> 就算這條 memory 被召回了，現在真的應該把它說出口嗎？

這就是 mention policy。

它可以很簡單，也可以很複雜，但它至少該判斷：
- 這條記憶是要拿來隱性幫助排序，還是顯性出現在回答裡？
- 顯性提起會讓回答更準，還是只是讓使用者感受到過度表演？
- 這條訊號該被視為背景條件、偏好 prior，還是本輪主題本身？

如果沒有 mention policy，很多產品再怎麼優化 retrieval，最後還是會把 recall 做成「我知道你以前怎樣，所以我現在又要 cue 一次」。

Karpathy 講的 trying too hard，本質上就是這個 gate 沒立起來。

## 5. 使用者可控記憶：不是只有可編輯，還要可解釋
很多人提「讓使用者可以編輯 memory」。我基本上同意，因為黑盒記憶最糟的地方是它不給你治理權。

但如果只做到可編輯，還不夠。

更完整的要求應該是：
- **可看見**：它到底存了什麼
- **可編輯**：你可以改、刪、撤回
- **可解釋**：它為什麼這次被召回
- **可抑制**：你可以說這條不要再主動提

換句話說，memory UI 不只是記憶清單，而應該是一個治理面板。

## 6. Trust / provenance：很多 personalization 問題，其實也在問「誰有資格重回 prompt」
如果一段低信任、低品質、甚至帶有污染風險的內容，也能在未來被 recall 回來，那 personalization 失敗就不只是煩，而會變危險。

這也是為什麼 trust/provenance 不能只拿來防 prompt injection，它同樣應該進入 memory system。

這一層想解的是：
- 哪些東西可以被存
- 哪些東西可以被撈
- 哪些東西即使文本很像，也不該重回上下文

在這個意義上，selection quality 常常比 storage quantity 更重要。

## 7. 自動整理、auto dream、睡眠重整：方向有魅力，但風險比想像大
這條線最近很容易讓人興奮，因為它很像人腦：
- 白天接收碎片
- 夜裡壓縮整理
- 把 episodic 痕跡重組成更穩定的抽象知識

概念上非常迷人，也確實可能帶來幫助：
- 去重
- 壓縮
- 連結
- 形成更穩定的候選 profile

但它最大的風險也在這裡：
它很容易從雜訊中「夢出一個人設」。

例如：
- 幾次臨時查詢
- 幾次偶發情緒
- 幾個相近但其實不穩定的偏好

經過 consolidation 之後，可能被濃縮成：
- 使用者長期很在意 X
- 使用者是一種 Y 型人格
- 使用者偏好某種固定風格

一旦這些抽象結論再反過來影響 retrieval 與 response，就很容易從一次錯誤，升級成長期錯誤。

所以如果要做這條路，我的態度很清楚：

> consolidation 可以做，但先當 candidate generator，不要直接改寫 canonical memory。

## 8. 工程現實：每多一層治理，都有成本
這也是 Gemini review 提醒得對的一點：談 memory 解法，不能假裝這只是概念設計。

每加一層治理，通常都會多出至少一個代價：
- 延遲更高
- ranking 更複雜
- receipts 更難做清楚
- operator surface 更多
- 測試矩陣更大
- 維運與 rollback 更麻煩

所以真正成熟的 memory system，往往不是功能最多，而是知道哪幾層值得先做、哪幾層應該後做。

如果以優先級來看，我會這樣排：
1. 先把 durable / docs / topology / episodic 分開
2. 再把 retention 與 activation 分開
3. 再做 selective retrieval 與 repeat suppression
4. 再把 mention policy 明文化
5. 最後才談 dream / consolidation 等更野的層

## 這篇的結論
如果只想記一件事，那就是：

> 所有已知解法都不是錯，只是它們各自處理的是不同層的問題。

- decay 在處理生命周期
- typing 在處理結構
- retrieval gating 在處理注入品質
- mention policy 在處理使用者實際感受到的干擾
- trust / provenance 在處理哪些內容有資格回來
- user control 在處理治理權
- consolidation 在處理壓縮與演化，但也帶來更大黑盒風險

真正成熟的設計，不是從中挑一招神藥，而是承認 memory 是一個治理堆疊。

下一篇就來看 `openclaw-mem`：它實際上做了哪些東西、哪些方向已經走對、哪些地方仍然半路上。
