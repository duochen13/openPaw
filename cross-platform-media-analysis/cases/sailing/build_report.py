"""Build a clean standalone comparison and collection manifest for the sailing case."""
import csv
import datetime
import html
import json
from pathlib import Path
from collections import Counter
from zoneinfo import ZoneInfo

CASE=Path(__file__).resolve().parent
PROJECT=CASE.parents[1]
DATA=CASE/'data'
read=lambda name:json.loads((DATA/name).read_text())
esc=lambda s:html.escape(str(s),quote=True)
y=read('youtube-comments.json');b=read('bilibili-comments.json');stats=read('sample-statistics.json')
ym=read('youtube-metadata.json');bm=read('bilibili-metadata.json')
yt_by_rank={r['rank']:r for r in y if r['sort']=='top'}
new_by_rank={r['rank']:r for r in y if r['sort']=='newest'}
b_by_id={r['id']:r for r in b}
now=datetime.datetime.fromisoformat(max(ym['collected_utc'], bm['collected_utc']))
stamp=now.astimezone(ZoneInfo('America/Vancouver')).strftime('%B %d, %Y')
examples=[]
def example(platform,key,topic,emotion,meaning,uncertainty):
 r=b_by_id[str(key)] if platform=='bilibili' else (yt_by_rank if platform=='top' else new_by_rank)[key]
 examples.append({'platform':r['platform'],'id':r['id'],'sample':platform,'topic':topic,'expressed_emotion':emotion,'english_paraphrase':meaning,'uncertainty':uncertainty,'url':r['url']})
example('bilibili','282147601937','An alternative life','Envy / emotional longing','The commenter is struck by the existence of a completely different way of living.','A prominent root with 2,682 likes; not an estimate of how many viewers feel this way.')
example('bilibili','282067542145','Envy and belonging','Envy / playful affiliation','Expresses envy of another person’s life; replies repeat and remix the sentiment.','Repetition inside a thread reflects interaction and imitation, not independent topic selection.')
example('bilibili','284325019040','Money and self-comparison','Mixed envy / admiration','Contrasts bargain-hunting in everyday life with the crew’s opportunity, while explicitly admiring the people aboard.','Mixed emotion; do not reduce it to hostility toward wealthy travelers.')
example('bilibili','283106942545','Unequal freedom','Resentment','Describes a world divided between people who work hard and people who enjoy it.','A single structural critique, not the position of the entire thread.')
example('bilibili','284058615456','Physical discomfort','Disinterest / weariness','Personal experience with repeated vomiting makes the voyage less appealing.','The cause of the commenter’s symptoms is unspecified; do not infer an occupation or illness.')
example('bilibili','283527644257','Risk and reward','Caution / reassurance','Argues that ocean travel offers both extraordinary joy and hardship; viewers should consider their tolerance.','A counterexample to reading the thread as unqualified envy.')
example('bilibili','285651382432','Vicarious enjoyment','Reassuring / humorous','Suggests that watching from home offers scenery without weather exposure or risk.','May also be a way to cope with social comparison.')
example('bilibili','282075035521','Creator invitation','Excitement / engagement prompt','The uploader promises an Antarctic trip if the video reaches a like target and asks about group travel.','Creator-authored; excluded from non-uploader counts. The prompt shapes its replies.')
example('bilibili','282075489041','Crew relationship','Warmth / affiliation','The named captain invites the creators back aboard.','Identified participant, not an independent audience response.')
example('top',6,'Life comparison','Envy / sadness / admiration','A 36-year-old working late contrasts their life with the crew’s shared adventure and sense of purpose.','Age and circumstances are self-reported; 90 displayed likes are not population support.')
example('top',17,'Aspirational action','Hope / motivation','Frames travel as motivation to earn money and eventually achieve freedom to explore.','A future intention, not evidence of actual action.')
example('top',5,'Learning interest','Curiosity','Reports starting to learn about sailing after watching.','Self-report; behavior is not independently verified.')
example('top',4,'Filmmaking','Appreciation','Says the video held their attention for its entire duration.','Praise for production does not imply willingness to live at sea.')
example('top',13,'Shared fandom','Excitement','Connects the episode to being a One Piece fan.','This reference also comes from the video’s own framing; not proof of a platform difference.')
example('top',37,'Cross-platform audience','Support / affiliation','Says they watched on Bilibili and came to YouTube to like the video.','Direct evidence of at least one self-reported overlapping viewer; overlap rate is unknown.')
example('top',67,'Practical access','Curiosity','Asks the price of a trip.','A question signals interest, not necessarily an intention or ability to book.')
example('top',73,'Onboard connectivity','Curiosity','Asks whether internet access is available and reliable at sea.','Practical feasibility question rather than an emotional endorsement.')
example('top',59,'Attribution challenge','Skepticism','Challenges a literary quotation’s attribution using an AI answer.','Neither the quotation nor the AI answer was independently checked.')
example('top',58,'National flag scene','Correction','Points to an on-screen response in the flag-related exchange.','A flag mention need not express the same political stance as other flag comments.')
example('newest',27,'National identity','Hostility','Expresses disgust at the sight of the Chinese flag.','One hostile political reaction; no basis to infer nationality or generalize to YouTube.')
example('newest',66,'National identity','Derision / hostility','Turns the flag scene into derogatory commentary about patriotism and mainland Chinese people.','The stereotype is the commenter’s, not an endorsed conclusion.')
example('top',49,'English response','Appreciation','Thanks the creator for sharing a different experience.','The only primarily English comment in the retrieved 92; insufficient for an English-audience comparison.')
with (DATA/'annotated-examples.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(examples[0]));w.writeheader();w.writerows(examples)
manifest={'collected_utc':now.isoformat(),'youtube':{'video_id':ym['videoId'],'records':len(y),'unique_comments':92,'top':83,'newest':92,'overlap':83,'creator_comments':0,'reply_threads_collected':False,'displayed_comments':105,'complete_corpus_claim':False,'sample_limit':'Up to five pages per sort, anonymous web client; comment count may include replies.'},'bilibili':{'bvid':bm['bvid'],'records':len(b),'top_level':3,'replies':121,'uploader_comments':sum(r['creator'] for r in b),'identified_other_participant_comments':sum(r['participant'] for r in b),'other_comments':sum(not r['creator'] and not r['participant'] for r in b),'unique_author_keys':len({r['author_key'] for r in b}),'displayed_comments':1720,'complete_corpus_claim':False,'access_limit':'Hot endpoint exposed 3 roots. Newest and hot page 2 returned empty. Retrieved all 121 replies reported across those roots; some reply context may be missing or deleted.','danmaku_collected':False},'classification':stats['method'],'selected_examples':len(examples),'pair_verification':'Same named creator, corresponding Chinese titles/descriptions; duration differs by 5 seconds. Not verified frame-by-frame or subtitle-by-subtitle.'}
(DATA/'collection-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
bar_rows=''.join(f'<div class="bar-row"><span>{esc(t["label"])}</span><div class="track"><div class="bar" style="width:{t["count"]/92*100:.4f}%"></div></div><strong>{t["count"]}</strong><span>{t["percent"]:.1f}%</span></div>' for t in sorted(stats['primary_topics'],key=lambda t:-t['count']))
evidence=''.join('<tr><td><a href="'+esc(r['url'])+'" target="_blank" rel="noopener noreferrer">'+esc('Bilibili' if r['platform']=='bilibili' else 'YouTube '+r['sample'])+' ↗</a></td><td>'+esc(r['topic'])+'<br><small>'+esc(r['expressed_emotion'])+'</small></td><td>'+esc(r['english_paraphrase'])+'</td><td>'+esc(r['uncertainty'])+'</td></tr>' for r in examples)
links={}
for name,platform,key in [('envy','top',6),('overlap','top',37),('cost','top',67),('english','top',49),('flag','newest',27),('correction','top',59)]:links[name]=(yt_by_rank if platform=='top' else new_by_rank)[key]['url']
template=(CASE/'template.html').read_text()
values={'DATE':stamp,'BILI_VIEWS':f'{bm["stat"]["view"]:,}','YT_VIEWS':f'{int(ym["viewCount"]):,}','TOPIC_BARS':bar_rows,'EVIDENCE':evidence,**{k.upper()+'_URL':esc(v) for k,v in links.items()}}
for k,v in values.items():template=template.replace('{{'+k+'}}',v)
assert '{{' not in template
(CASE/'index.html').write_text(template)
# Workspace entry opens the latest report; retain a case-specific standalone copy.
entry=template.replace('href="data/','href="cases/sailing/data/').replace('href="report.md"','href="cases/sailing/report.md"').replace('href="../../reports/grantham-comparison.html"','href="reports/grantham-comparison.html"')
(PROJECT/'index.html').write_text(entry)
print('Built sailing/index.html and workspace index.html; previous Grantham report preserved.')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
