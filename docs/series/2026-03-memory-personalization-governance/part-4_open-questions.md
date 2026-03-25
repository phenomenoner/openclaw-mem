# Part 4｜待解問題與未來方向：從 recall engine 走向 memory governance

前面三篇講到這裡，其實答案已經開始浮出來了：

未來 memory system 的關鍵，不會是誰存得最多，也不會是誰最像在背誦你的過去，而是誰更像一個**有門禁、有政策、有審計能力的治理層**。

也就是說，這個領域真正要長大的方向，不是 bigger memory，而是 **memory governance**。

## 1. 真正要解的不是「記住」，而是「怎麼更新、怎麼退場」
到現在為止，多數 memory 產品都還是把重點放在 retention：
- 怎麼抓訊號
- 怎麼存
- 怎麼搜
- 怎麼在下一輪拿回來

但真正麻煩的問題，常常出現在更後面：
- 一個興趣過了多久應該降權？
- 偶發話題什麼時候算過期？
- 如果使用者的偏好改了，舊偏好要怎麼退場？
- 如果某條記憶曾經造成干擾，系統要怎麼學會下次閉嘴？

這些都不是單純 recall engine 能回答的。
這是治理問題。

所以未來成熟系統一定要處理一件事：

> personalization 不是把 profile 越積越厚，而是讓 profile 能隨時間演化、淡化、被撤回、被覆蓋。

## 2. 「should retrieve」和「should mention」應該正式拆開
這大概是我現在最想看到業界補上的 contract。

因為很多系統即使做了 retrieval gating，最後仍然把 recalled memory 直接外顯到回答裡，於是又回到 Karpathy 抱怨的那種「trying too hard」。

真正成熟的系統應該至少要有兩道獨立問題：
1. 這條 memory 現在值不值得進入 reasoning context？
2. 就算值得，它值不值得被顯性提起？

有些記憶只適合當背景 prior：
- 幫助排序
- 幫助語氣
- 幫助排除某些錯方向

但它們不該直接變成一句「你之前好像很喜歡 X」。

這件事如果不被明文化，產品就會一直把 recall 當成表演連續性的舞台。

## 3. Memory receipts 應該回答人類問題，而不是只回答系統問題
很多系統現在開始有 receipts、trace、selection logs，這是好事。
但接下來要更進一步。

因為操作人員真正想問的是：
- 為什麼你今天提了這個？
- 為什麼上次提、這次沒提？
- 為什麼這條被 archive？
- 為什麼這條只是影響排序，卻沒有被說出口？

如果 receipt 只會輸出 score、tier、candidate count，那它離真正可治理還有一段距離。

未來真正有價值的 explainability，不只是「系統留下了記錄」，而是：
**人類看得懂這個決策。**

## 4. Dream / consolidation 會來，但不該直接握有寫死真相的權力
我相信 consolidation 類方法一定會持續被探索。因為它真的很誘人：
- 可以去重
- 可以壓縮
- 可以把零碎 episodic 訊號整理成較穩定結構
- 可以降低 storage 與 retrieval 負擔

但未來如果要做這條線，產品上最好守住一條紅線：

> consolidation 可以產生候選，不應黑盒改寫 canonical memory。

理由很簡單：
- 一旦它從幾次偶發行為中濃縮出錯的人設
- 這個錯誤就不再是零碎噪音
- 而會升級成高層結論，反過來統治後面的 retrieval 與 generation

所以比較成熟的設計會像：
- 產生 candidate summary
- 附來源與證據鏈
- 要嘛等人工確認
- 要嘛在明確 policy 下進入較弱權重的 provisional lane

而不是「睡一覺起來，系統就覺得更懂你了」。

## 5. 未來 benchmark 不該只量 recall accuracy
這個領域接下來最缺的，其實不是再多幾個 memory demo，而是更對題的 benchmark。

現在很多評測還是偏向：
- 找不找得到
- top-k 對不對
- 多輪之後能不能 recall 某個事實

這些很重要，但還不夠。

更成熟的 benchmark 應該至少加入：
- **suppression**：該不該把某條記憶壓下來
- **abstention**：不確定時能不能不硬用 memory
- **context-appropriate application**：某偏好該不該在這個情境套用
- **interest drift**：使用者興趣改變後，系統多久調整
- **scope isolation**：多專案 / 多角色時會不會 bleed
- **mention discipline**：是否把本來只該當背景的記憶過度前台化

這也是為什麼 BenchPreS 和 LongMemEval 這類工作值得看：它們至少把問題往「情境是否適當」與「長期互動是否真實」推進了一步，而不是只做 toy retrieval。

## 6. 最後會勝出的系統，會更像治理層而不是記憶背包
如果把未來長相講得更具體一點，我認為比較像下面這樣：

### A. 多層記憶，不同權限
- profile
- episodic
- task-local working set
- docs/reference
- topology/structure
- suppression / deprecated memories

### B. 多條 policy，不同職責
- write policy
- retention policy
- retrieval policy
- mention policy
- trust / provenance policy
- lifecycle / archive / revive policy

### C. 明確的人類介面
- memory visible
- memory editable
- memory suppressible
- recall explainable
- lifecycle inspectable

### D. 預設比較克制
真正成熟的系統，預設不該是：
- 盡可能多記
- 盡可能多撈
- 盡可能多表現 continuity

而應該是：
- 高信心、低污染、可解釋地保留
- 在需要時有選擇地喚起
- 能幫助回答，但不搶走回答本身

## 7. 回到起點：Karpathy 那句話真正有價值的地方
Karpathy 那句 post 之所以值得認真看，不是因為它提出了一個全新技術詞，而是因為它把一種大家都感受到、卻很容易被誤診的失敗模式說破了。

那個失敗模式不是：
- 你沒有記住我

而是：
- 你太努力地表演自己記得我

這兩者看起來很像，方向卻完全不同。

如果把它看成 forgetting 問題，你會一直往更大的記憶、更長的 context、更積極的 retrieval 去做。
如果把它看成 governance 問題，你就會開始問：
- 哪些東西值得留下
- 哪些東西該被抑制
- 哪些東西該只在背景中生效
- 哪些東西應該有退出機制

這就是我覺得接下來幾年 memory systems 真正會分出高下的地方。

## 收束
如果要把整組系列收成一句最乾淨的結論，我會寫成這樣：

> 好的 LLM 記憶不是更會想起你，而是更知道什麼時候不該把想起來的東西說出口。

未來真正成熟的記憶系統，也不會只是更大的 recall engine。
它會是一層能夠寫入、分類、檢索、抑制、解釋、撤回的治理系統。

記憶本身不是答案。
**如何治理記憶，才是答案。**
