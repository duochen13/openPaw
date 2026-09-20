# Comment interpretation framework

Code the original language first. Translate meaning and tone, explaining slang rather than translating word-for-word. Multiple labels may apply. Leave ambiguous cases uncertain.

| Dimension | Question | Example labels |
|---|---|---|
| Topic | What caught their attention? | Market valuation; investing access; housing; inequality; AI; environment/health; interview quality |
| Target | Who or what is being evaluated? | Guest; host; claim; economic system; another commenter; translation |
| Stance | What position is expressed toward that target? | Agree; disagree; mixed; ask; unclear |
| Expressed emotion | What feeling does the wording communicate? | Admiration; concern; anger; contempt; amusement; resignation; curiosity; unclear |
| Trust | What makes a claim credible or suspect? | Track record; apparent expertise; holdings/actions; financial incentives; lived experience |
| Social function | What is the comment doing? | Testimony; rebuttal; correction; joke; advice; affiliation; status contest; promotion |
| Underlying concern | What concern might explain the reaction? | Financial security; fairness; autonomy; belonging; competence; physical safety |
| Evidence and uncertainty | How strong is this reading? | Direct wording vs interpretation; reply context; ambiguous sarcasm; unverified allegation |

Emotion is expressed tone, not a diagnosis of the author's internal state. Underlying concerns are interpretations, not established facts about the person. Do not infer demographics, nationality, or identity from language.

Examples of distinctions that matter:

- Admiring the speaker does not establish agreement with his market forecast.
- Anger about unaffordable housing can coexist with welcoming a price crash.
- A joke can dismiss a prediction, establish community membership, or both.
- A reply can correct its parent. Do not count the whole thread as agreeing.
- Likes measure visible endorsement/engagement under unequal exposure, not population support.

## Sampling and counting

Keep top-level comments, replies, and danmaku separate. Deduplicate by platform and comment ID. Keep Top and Newest strata separate; deduplicate their overlap if producing a combined count. Exclude creator promotion from viewer summaries. Flag suspected commercial promotion without declaring its author a bot.

Label language before making an English-versus-Chinese comparison. Preserve non-English comments separately; do not silently translate them into an English-audience sample. If percentages are later reported, give the exact eligible denominator and label them as sample frequencies, not viewer proportions. Multiple-label percentages may exceed 100%.

For a substantive study, use matching time windows, document access failures and ranking locale, inspect repeated authors, review an overlapping subset with a second coder, and distinguish disagreement about labels from uncertainty in the text. Test cultural hypotheses across several matched videos and channels, including counterexamples.
