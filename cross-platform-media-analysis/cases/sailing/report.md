# Sailing around the world: Bilibili versus YouTube

Video: 用一只帆船也可以环游世界？ by 小鹿Lawrence. Sources: [YouTube](https://www.youtube.com/watch?v=zxhsbfEgRiU) and [Bilibili](https://www.bilibili.com/video/BV1zYSvBHE3U/). Collected September 17, 2026, Vancouver time.

**The main finding is shared longing expressed through different discussion formats—not a demonstrated Chinese-versus-English cultural difference.** Almost all retrieved YouTube comments are also Chinese. Both samples use the voyage as a point of comparison with ordinary life; the accessible Bilibili replies develop that into extended exchanges, whereas YouTube also contains short appreciation and practical questions.

## Sample

| Measure | Bilibili | YouTube |
|---|---:|---:|
| Platform-displayed views | 2,723,441 | 137,739 |
| Platform-displayed comments | 1,720 | 105 |
| Retrieved records, deduplicated | 124 | 92 |
| Structure | 3 roots + 121 replies | Top-level comments only |
| Uploader / identified captain messages | 3 / 1 | No uploader comments flagged |
| Other retrieved comments | 120 | 92 |

Bilibili’s anonymous endpoint exposed just three roots; requests for newest comments and the second hot page returned empty. Reply pagination returned 51, 34 and 36 replies for those roots. Two roots are non-uploader comments; the third is an uploader engagement prompt. These threads do not represent the whole comment section. Some replies refer to missing context. No danmaku was collected.

YouTube returned 83 Top and 92 Newest comments. All 83 Top IDs also occur in Newest: 83 + 92 − 83 = 92 unique comments, not 175 separate reactions. Retrieval was bounded to five pages per sort; the report makes no complete-corpus claim. Displayed comment totals may include replies, which were not collected on YouTube.

Both videos have the same named creator and corresponding descriptions. Bilibili was published November 30, 2025; YouTube December 3. Runtime differs: 34:06 versus 34:01. Exact edit and subtitle equivalence were not checked.

## The language result changes the research question

Manual language coding of all 92 YouTube comments found 90 primarily Chinese (97.8%), one English (1.1%) and one emoji-only (1.1%). Mixed English names and quoted dialogue are included under primarily Chinese. Language does not establish nationality or residence.

A [YouTube commenter explicitly describes watching on Bilibili before coming to YouTube to like the video](https://www.youtube.com/watch?v=zxhsbfEgRiU&lc=UgzWNzXgZxKebn5rbVB4AaABAg). This is direct self-reported overlap, not evidence of an overlap rate. It means the platforms should not automatically be modeled as independent national audiences.

## Emotion: admiration and envy coexist

In both samples, the voyage can evoke admiration while making the viewer’s own constraints more salient. A [YouTube comment about working late and missing meaningful adventure](https://www.youtube.com/watch?v=zxhsbfEgRiU&lc=UgzoQYjq1d1_Tud7KYN4AaABAg) parallels the life comparison in the [largest accessible Bilibili thread](https://www.bilibili.com/video/BV1zYSvBHE3U/#reply282147601937).

An interpretive sequence is: seeing an alternative life → comparing possibilities → aspiration or a painful perceived gap. Responses can then move toward practical curiosity, humor, reassurance, or resentment. This is a reading of the discussion, not a causal or psychological measurement.

The Bilibili replies include counterweights to romantic envy: physical discomfort, sailing hardship, risk tolerance, and the advantages of watching safely from home. That mixture matters more than labeling the thread simply negative. The creator’s separate Antarctic-trip prompt elicits encouragement and participation, which should not be mistaken for spontaneous evaluation of the sailing episode.

## Auditable YouTube primary-topic counts

| Primary topic | Count / 92 | Share |
|---|---:|---:|
| Appreciation of filming, people or experience | 23 | 25.0% |
| Practical questions, advice or expectations | 15 | 16.3% |
| Fandom, jokes or character talk | 13 | 14.1% |
| Aspiration, envy or life comparison | 10 | 10.9% |
| Community support or minimal response | 10 | 10.9% |
| Travel, food or boat observations | 9 | 9.8% |
| Criticism, correction or risk warning | 7 | 7.6% |
| National flag / political identity | 5 | 5.4% |

These are single-analyst primary-topic assignments, with one category per comment. They are not sentiment percentages or estimates of average viewer opinion. Mixed comments require interpretive choices; [coding notes](data/coding-notes.md) and [row-level assignments](data/youtube-coded.csv) make those choices reviewable. There was no independent second coder.

The five flag-related comments have different stances, including a correction and hostile reactions. Their presence establishes an identity-related cluster in the sample, not a general YouTube attitude. Nine Newest-only comments include harsher criticism and political hostility, but also praise and support. Retrieval cannot explain why they were absent from Top or demonstrate censorship.

## What can and cannot be concluded

The most defensible contrast is about discussion form and observed emphasis: Bilibili’s selected threads make social comparison and peer responses prominent; YouTube’s retrieved top-level comments show a broader mix of appreciation, practical interest, fandom and criticism. Thread depth and selection can themselves generate this contrast.

There is insufficient English-language evidence for the original language-group comparison. A stronger next case would include a substantial English-language audience, comparable thread levels, matched time windows and multiple video pairs. These comments cannot establish the views of silent viewers or national populations.

See the [HTML report](index.html) for diagrams and all 22 selected source-linked examples. Commenters’ claims about history, quotation attribution, costs or individuals are not independently verified here.
