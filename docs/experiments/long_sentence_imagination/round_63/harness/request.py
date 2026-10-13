"""Build /ibl/execute requests for round 63. Never computes answers."""
import argparse,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
OUT=Path(os.environ.get('R63_OUT',str(ROOT/'outputs/long_sentence_imagination/2026-10-13_63회차'))).resolve()
PROJECT='d3bbe55090f54d52b435184e068b4148'
THREADS={'trainer':'b7144a55d2714fbba37f16a98a820dd1','agent':'9bf7c088a4504112ac35b677995cb3dd','decoy':'8ee19ab799bc424fbe8d3a55a69ca8ad'}
DECOY_VERSION='f2794cc0522b48d9a6294113fa1ebd6f'
PAPERS=[(1,'2307.03172','Lost in the Middle: How Language Models Use Long Contexts','Lost_in_the_Middle__How_Language_Models_Use_Long_Contexts.pdf'),
 (2,'2406.15319','LongRAG: Enhancing Retrieval-Augmented Generation with Long-context LLMs','LongRAG__Enhancing_Retrieval_Augmented_Generation_with_Long_context_LLMs.pdf'),
 (3,'2501.01880','Long Context vs. RAG for LLMs: An Evaluation and Revisits','Long_Context_vs__RAG_for_LLMs__An_Evaluation_and_Revisits.pdf'),
 (4,'2409.01666','In Defense of RAG in the Era of Long-Context Language Models','In_Defense_of_RAG_in_the_Era_of_Long_Context_Language_Models.pdf'),
 (5,'2404.06654',"RULER: What's the Real Context Size of Your Long-Context Language Models?",'RULER__What_s_the_Real_Context_Size_of_Your_Long_Context_Language_Models_.pdf'),
 (6,'2406.13121','Can Long-Context Language Models Subsume Retrieval, RAG, SQL, and More?','Can_Long_Context_Language_Models_Subsume_Retrieval__RAG__SQL__and_More_.pdf'),
 (7,'2402.14848','Same Task, More Tokens: the Impact of Input Length on the Reasoning Performance of Large Language Models','Same_Task__More_Tokens__the_Impact_of_Input_Length_on_the_Reasoning_Performance_of_Large_Language_Models.pdf'),
 (8,'2411.03538','Long Context RAG Performance of Large Language Models','Long_Context_RAG_Performance_of_Large_Language_Models.pdf')]
NEW=(9,'2410.05983','Long-Context LLMs Meet RAG: Overcoming Challenges for Long Inputs in RAG','Long_Context_LLMs_Meet_RAG__Overcoming_Challenges_for_Long_Inputs_in_RAG.pdf')
def paper(t):
    return {'id':t[0],'arxiv':t[1],'title':t[2],'path':str(OUT/'papers/pdf'/t[3])}
p=argparse.ArgumentParser();p.add_argument('program');p.add_argument('label');p.add_argument('--check',action='store_true');p.add_argument('--who',default='trainer');a=p.parse_args()
code=(ROOT/'docs/experiments/long_sentence_imagination/round_63/programs'/a.program).read_text()
inputs={'project':PROJECT,'thread':THREADS[a.who],'out':str(OUT/a.who/'out'),'decoy':DECOY_VERSION,'papers':[paper(t) for t in PAPERS],'new':paper(NEW)}
payload={'code':code,'edition':2,'origin':'training','project_id':'수동모드','inputs':inputs,'budget':{'steps':5000000,'rows':100000}}
if a.check:payload['check']=True
(OUT/'runs'/f'{a.label}_request.json').write_text(json.dumps(payload,ensure_ascii=False))
print(OUT/'runs'/f'{a.label}_request.json')
