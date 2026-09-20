"""Explicit analyst coding of 92 unique YouTube comments, with one primary topic each.

Assignments are recorded by collection position for auditability, not keyword inference.
Top and Newest overlap; the nine newest-only comments are assigned separately.
"""
import csv
import json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
rows=json.loads((ROOT/'data/youtube-comments.json').read_text())
TOPICS={
'appreciation':'Appreciation of filming, people or experience',
'aspiration':'Aspiration, envy or life comparison',
'practical':'Practical questions, advice or expectations',
'observation':'Travel, food or boat observations',
'humor':'Fandom, jokes or character talk',
'community':'Community support or minimal response',
'criticism':'Criticism, correction or risk warning',
'flag':'National flag / political identity',
}
GROUPS={
'appreciation':[1,3,4,14,16,18,19,26,27,28,35,38,40,41,45,46,47,48,49,50,81],
'aspiration':[2,5,6,12,17,22,36,39,64,82],
'practical':[31,32,54,61,62,66,67,68,69,71,73,74,76,77,83],
'observation':[10,25,29,30,34,42,53,56,60],
'humor':[7,9,11,13,20,33,43,51,55,57,63,65,70],
'community':[8,15,23,24,37,44,52,75],
'criticism':[21,59,78,79],
'flag':[58,72,80],
}
NEW_ONLY={23:'community',27:'flag',28:'appreciation',43:'criticism',60:'criticism',65:'appreciation',66:'flag',72:'criticism',92:'community'}
assignment={}
for category,ranks in GROUPS.items():
 for rank in ranks:
  assert rank not in assignment
  assignment[rank]=category
assert set(assignment)==set(range(1,84))
top={r['id']:r for r in rows if r['sort']=='top'}
newest={r['id']:r for r in rows if r['sort']=='newest'}
assert set(top)<=set(newest)
assert {r['rank'] for cid,r in newest.items() if cid not in top}==set(NEW_ONLY)
coded=[]
for cid,r in {**newest,**top}.items():
 category=assignment[r['rank']] if cid in top else NEW_ONLY[r['rank']]
 language='English' if cid==next(x['id'] for x in rows if x['sort']=='top' and x['rank']==49) else 'Emoji only' if cid==next(x['id'] for x in rows if x['sort']=='top' and x['rank']==75) else 'Chinese (including mixed terms)'
 coded.append({**r,'primary_topic':category,'primary_topic_label':TOPICS[category],'language':language,'in_top':cid in top,'in_newest':cid in newest})
(ROOT/'data/youtube-coded.json').write_text(json.dumps(coded,ensure_ascii=False,indent=2))
with (ROOT/'data/youtube-coded.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(coded[0]));w.writeheader();w.writerows(coded)
counts=Counter(r['primary_topic'] for r in coded)
stats={'unique_youtube_comments':len(coded),'languages':dict(Counter(r['language'] for r in coded)),'primary_topics':[{'key':k,'label':TOPICS[k],'count':counts[k],'percent':round(counts[k]/len(coded)*100,1)} for k in TOPICS],'top_unique':len(top),'newest_unique':len(newest),'overlap':len(set(top)&set(newest)),'newest_only':len(set(newest)-set(top)),'method':'Single analyst manual primary-topic classification; one category per comment; no independent second coder. Language labels describe text, not nationality. Counts are comment frequencies in the retrieved sample, not population estimates.'}
(ROOT/'data/sample-statistics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
print(json.dumps(stats,ensure_ascii=False,indent=2))
