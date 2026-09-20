# Sailing case: coding rules

The assistant manually assigned each of 92 distinct YouTube top-level comments one primary topic after reading the complete text. This is an exploratory single-coder classification, not independently validated measurement. Assignments are explicit in `../code_sample.py`; the original text, comment link, category and language are in `youtube-coded.csv`.

## Topic definitions

- **Appreciation of filming, people or experience:** general praise of video quality, enjoyment, personalities, looks or the shared experience. This includes appearance-focused compliments; it is not necessarily admiration of sailing.
- **Aspiration, envy or life comparison:** contrasts one’s life with the voyage, expresses a travel ambition, reports starting to learn, or discusses alternative life priorities. The alternative-priorities comment is not assumed to envy the crew.
- **Practical questions, advice or expectations:** cost, funding, connectivity, sleeping arrangements, vessel identification questions, filming equipment, navigation explanation, race suggestions, channel requests, or expecting sailing instruction. Some are statements rather than questions.
- **Travel, food or boat observations:** food notes, personal travel experience, familiarity with the owner, or recognizing a boat model without asking a question.
- **Fandom, jokes or character talk:** One Piece references, wordplay, seasickness jokes, speculation about an actor resemblance, personality or regional background. Categorization does not endorse guesses about a person.
- **Community support or minimal response:** greetings, early support, requests for channel growth, subscribing, cross-platform support, concern for creator wellbeing, or a lone waving emoji.
- **Criticism, correction or risk warning:** dismissive presenter comments, quotation-attribution challenges, risk anecdotes, or criticism of the audience’s interest in sailing.
- **National flag / political identity:** comments about the flag exchange, including correction, political challenge and hostility. This category does not imply one shared political stance.

When a comment fits several topics, the apparent central communicative purpose determines its one primary category. For example, the boat-price estimate that explicitly calls the boat a dream is coded aspiration; direct price questions are practical. The label is contestable and auditable. Counts sum to 92; rounded percentages sum to 100.0% in this snapshot. Categories are topics, not mutually exclusive human emotions.

## Language

90 comments are primarily Chinese, including mixed English terms or quoted dialogue; one is primarily English; one contains only an emoji token. These are text-language labels, not nationality, location or ethnicity. Traditional and simplified scripts are not used as demographic proxies.

## Sampling units

Top yielded 83 and Newest 92 records, with all 83 Top IDs also in Newest. The analysis deduplicates on comment ID. No platform-flagged uploader comment appears in this YouTube sample. Repeat authors, viewers who did not comment, hidden replies, and missing/deleted comments are not resolved; do not treat 92 as 92 verified people or a full census.

Bilibili yielded three roots plus 121 replies. Three messages are uploader-authored; one is from the identified captain. The remaining 120 are not a representative audience sample. One parent topic has 51 replies, another 34, and the uploader prompt 36; participant interaction and inherited topics make a direct topic-frequency comparison with YouTube top-level comments misleading. Some replies refer to text not available in the retrieved thread, so ambiguous jokes are not given a firm substantive reading.
