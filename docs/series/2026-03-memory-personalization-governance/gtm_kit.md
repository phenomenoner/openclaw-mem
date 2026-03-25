# GTM kit (lean)

## Title options
1. 記憶太用力：LLM 個人化為什麼常常「trying too hard」
2. LLM 不是只會忘，也會過度記得你
3. 個人化記憶的真正問題，不是 decay 不夠
4. 從 recall 到 governance：我們該怎麼重新理解 AI 記憶
5. 好的 AI 記憶，不是更會想起你
6. 當 LLM 太努力地證明「我記得你」
7. Memory overreach：個人化助手下一個更麻煩的 UX 問題

## TL;DR
Karpathy 最近點出一個很多人都有感的問題：現在不少 LLM 的 personalization memory 不是太弱，而是太用力。兩個月前你隨口問過一次的題目，之後它卻一直把那件事當成你的核心興趣，時不時就要提起來。這背後不是單純沒有記憶衰減，而是整個 memory stack 都可能出問題：寫入太寬、分類太粗、檢索太鬆、表達太前台。這系列長文會拆這個問題的脈絡、現有解法的優缺點、`openclaw-mem` 的實戰經驗，以及這個領域真正還沒解完的地方。

## Short social copy
### Version A
LLM 記憶現在最煩人的地方，不只是忘得快，而是記得太用力。
Karpathy 那句 "trying too hard" 很準：系統太急著證明自己記得你，反而把早就過期的訊號一直拖回來。

### Version B
我越來越覺得 AI memory 的核心不是 recall，而是 governance。
問題不只是有沒有 decay，而是寫入、分類、檢索、表達整條鏈都可能過度反應。

## Long social copy
Karpathy 最近在 X 上講了一個很準的點：很多 LLM 的 personalization memory 不是太弱，而是太煩。你兩個月前隨口問過一次的題目，系統之後卻一直把它當成你的深層興趣，時不時就要 cue 回來。這個問題不只是沒有 decay，而是整個 memory stack 都在 overreact：寫太多、分太粗、撈太鬆、說太多。我把這件事拆成一組長文，順便拿 `openclaw-mem` 的實戰經驗來看哪些方法真的有用，哪些只是在做更大的 prompt 背包。
