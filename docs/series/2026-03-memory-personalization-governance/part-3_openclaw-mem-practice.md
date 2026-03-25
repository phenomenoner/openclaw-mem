# Part 3｜`openclaw-mem` 的實戰經驗：從「多記一點」轉向「小而可信的 context pack」

如果把 Karpathy 那句 "trying too hard" 當作一個產品測試題，那 `openclaw-mem` 的有趣之處在於：它一開始就不太適合走「盡量多記」這條路。

更精準地說，`openclaw-mem` 真正長出的價值，不是 generic memory storage，而是 **trust-aware context packing** 與 **memory governance**。

這一點很重要。因為如果你把產品故事講成「我們讓 agent 有更多記憶」，那你很容易掉進錯的優化方向：
- 多存一點
- 多撈一點
- 多塞一點進 prompt

但 `openclaw-mem` 真正比較像是在做另一件事：

> 把記憶、文件、拓樸、事件痕跡分層治理，再從中選出一小束可信、可解釋、對當下真的有幫助的 context。

這就是它比較接近未來答案的地方。

## 1. 先把 storage class 分開：不是所有「有用資訊」都該進同一個 memory bucket
`openclaw-mem` 裡一個很關鍵、但其實很容易被忽略的設計，是它明確區分：
- **L1 durable memory**：偏好、決策、穩定規則、長期 continuity
- **L2 docs knowledge**：合約、架構說明、runbook、operator-authored guidance
- **L3 topology knowledge**：entrypoints、路徑、ownership、impact map

這件事看起來像 repo hygiene，其實它正中 memory personalization 問題的核心。

因為很多系統之所以會 overreact，不是因為模型很笨，而是因為：
- 文件知識被誤當成個人記憶
- 原始工具輸出被誤當成 durable fact
- 一次性事件痕跡被誤當成長期偏好

一旦 storage class 本身是混的，後面所有 recall policy 都會被污染。

所以 `openclaw-mem` 給出的第一個實戰教訓很簡單：

> 不要先想怎麼存更多，先想哪些東西根本不該住同一個樓層。

## 2. 把 retention 跟 activation 分開，是記憶治理真正開始的地方
`docs/specs/auto-recall-activation-vs-retention-v1.md` 有一個我非常認同的方向：**retention != activation**。

這句話的意思是：
- 一條記憶值得被保留
- 不代表它每一輪都值得被拿出來用

很多 memory 系統最致命的錯，就是把 importance 同時當成：
- 該不該留下來
- 該不該現在注入 prompt

結果就是：
- must_remember pool 越大
- recall 越像固定前綴
- 同一批 durable items 越容易每輪都洗版
- 真正跟這一輪相關、但等級較低的東西，反而擠不進來

`openclaw-mem` 在這裡的方向是對的：
- retention 是長期治理問題
- activation 是當下選拔問題
- 這兩件事不該被一個 importance 分數直接綁死

這其實就是在對 Karpathy 的 complaint 下刀。因為「兩個月前隨口聊過一次，之後一直被提」很多時候不是 retention 錯，而是 activation 失控。

## 3. Working Set backbone + hot recall quota，是在對抗 static prefix 化
同一份 spec 裡還有兩個很值得記的設計：
- **Working Set 作為 backbone lane**
- **hot recall quota mixing**

Working Set 的意義在於：
有些東西就是穩定背景條件，沒必要每次都靠 recall 重新競爭上榜。把它們作為 backbone，可以減少普通 recall 一直重複選同一批內容。

hot recall quota 的意義則是：
別讓 must_remember 自動吃掉整個 budget。要保留空間給：
- 近期有用訊號
- lower-tier 但 turn-relevant 的記憶
- wildcard 類型的邊緣但實用的項目

這一套的精神，其實就是從「把記憶當倉庫」轉成「把記憶當選拔賽」。

它不是保證完美，但至少方向正確：
- 不讓 durable winners 永久壟斷
- 不讓 recall 退化成固定 prefix
- 讓當下 relevance 有機會贏一次

## 4. Repeat penalty 很樸素，但非常接近真實 UX 痛點
很多記憶系統會掉進一個盲點：
- 某些東西確實高度重要
- 所以每輪都很容易被選中
- 但每輪都選中，不代表每輪都該被看見

repeat penalty 這種設計，表面上只是 ranking tweak，實際上很有 UX 價值。

因為它承認了一個現實：

> 一條記憶即使永遠正確，也可能因為過度重複而變成噪音。

這件事在 personalization 特別關鍵。使用者感受到的「你怎麼又提這個」常常不是因為記錯，而是因為同一條訊號被過度穩定地推回 context。

所以 repeat suppression 並不是在否定 durable memory，而是在保護它不要因為出場率太高而變得討厭。

## 5. `openclaw-mem` 最有說服力的不是 storage，而是 selection quality
`docs/showcase/trust-aware-context-pack-proof.md` 之所以重要，是因為它把一個常常被講得很抽象的事情，做成了可驗證的 before/after：
- 同一個 query
- 同一個 DB
- item limit 不變
- 只是打開 trust policy

結果是：
- quarantined row 被排除
- trusted row 補位進來
- pack 變小
- citations 和 receipts 還在

這個 proof 的價值不只在 security，也在 product framing。

它提醒了一件很重要的事：

> memory system 的真正競爭力，很多時候不是存更多，而是選得更乾淨。

這跟 personalization overreach 有直接關係。因為很多煩人的 memory 體驗，本質上也是 selection quality 太差：
- 舊訊號重新進場
- 低信任訊號重新進場
- 沒有資格回來的東西重新進場

如果 selection 不變，再大的記憶庫都只會放大問題。

## 6. Episodic lane 的 retention defaults，其實就是 typed lifecycle 的雛形
`docs/specs/episodic-auto-capture-v0.md` 裡有個很務實的點：不同 event kind 有不同 retention defaults。

例如：
- `conversation.user` 60d
- `conversation.assistant` 90d
- `tool.call` / `tool.result` 30d
- `ops.decision` forever

這件事看起來只是清理策略，但它其實代表了一種成熟度：
系統已經承認，不同事件類型不應該享有相同的存活條件。

這跟把所有東西都丟進同一個 durable bucket 相比，是很大的進步。

它也剛好支持一個本文一直在講的觀點：
**typed retention 比 blanket memory 更接近答案。**

## 7. `openclaw-mem` 已經走對的，不代表它已經解完
說實話，這一套現在還不能宣稱「已經把 personalization overreach 解掉」。

它比較像是已經踩對幾個有價值的方向：
- durable/docs/topology 分層
- retention 與 activation 分離
- working set backbone
- quota-mixed hot recall
- repeat penalty
- trust-aware selection
- typed retention defaults
- receipts / explainability posture

但還有幾塊仍然是半成品或 roadmap：
- lifecycle manager 仍是 roadmap
- mention policy 還沒有變成清楚、可操作的 contract
- explainability 雖然有 receipts，但還需要更像「回答人類問題」而不是「輸出系統欄位」
- adaptive personalization 也還沒有真正解：如何讓使用者興趣自然演化，而不是黏在舊訊號上

換句話說，它現在比較像一個**實戰實驗室**，而不是終局答案。

## 8. 這套實戰經驗最重要的結論：small, trusted, cited beats big memory blob
如果要把 `openclaw-mem` 的學到的東西濃縮成一句最值錢的話，我會選這句：

> 比起更大的記憶，更好的做法往往是更小、更可信、可引用、可解釋的 context pack。

因為使用者真正需要的不是「系統永遠記得一切」，而是：
- 它不要亂把文件當成記憶
- 不要把一次性事件當成永久偏好
- 不要把低信任內容又塞回來
- 不要每次都拿一樣的老訊號出來表演 continuity

這也是為什麼 `openclaw-mem` 值得談的，不是它有多像一個超級腦袋，而是它正在往一個比較成熟的方向走：

**記憶治理，勝過記憶堆積。**

下一篇，我們就來談這個領域還沒解完的問題：哪些東西現在還沒有被真正做對，未來可能往哪裡長，哪些方向又看起來性感但其實很危險。
