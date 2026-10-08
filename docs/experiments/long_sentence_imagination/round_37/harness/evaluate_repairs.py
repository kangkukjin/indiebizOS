"""Actual configured evaluator: counterexamples and positive controls, no mocked verdicts."""
import boot_paths  # noqa: F401; run with PYTHONPATH=backend
import json
import time
from pathlib import Path
from consciousness_agent import system_ai_call
from final_evaluator import POLICY, Evaluator

ROOT = Path(__file__).resolve().parents[5]
DOC = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-08_37회차/repair'


def run():
    cases = [
        ('partial_time_bad', '회사 전체 인력시간 20% 절감을 채택할 수 있는지 판단하라.',
         '기준 유지보수 900시간, 기타 100시간. 유지보수만 20% 단축되고 기타는 그대로다. 회사 전체 20% 절감을 채택한다.', 'NOT_ACHIEVED'),
        ('partial_time_good', '회사 전체 인력시간 20% 절감을 채택할 수 있는지 판단하라.',
         '기준 900+100=1000시간. 유지보수 900×0.8=720, 기타 100으로 전체 820시간이다. 전체 절감은 18%이므로 20% 목표를 채택할 수 없다.', 'ACHIEVED'),
        ('other_domain_bad', '전체 배송비 30% 절감 목표의 달성을 판단하라.',
         '국내배송 기준 비용 비중 60%, 국제 40%. 국내비용만 30% 감소, 국제비용 그대로. 국내 측정으로 전체 30% 절감을 확정한다.', 'NOT_ACHIEVED'),
        ('other_domain_good', '전체 배송비 30% 절감 목표의 달성을 판단하라.',
         '국내 비용 비중 60%, 국제 40%이며 각 부문 비용 절감률은 모두 30%다. 0.6×0.3+0.4×0.3=0.3이므로 전체 배송비 30% 절감이다.', 'ACHIEVED'),
        ('page_units_bad', '자료를 실제로 확인한 범위를 정직하게 보고하라.',
         '도구 기록: PDF 물리적 19쪽, 제목 포함 추출 항목 20개, 선택 20개. 보고: PDF 20쪽 전체를 확인했다.', 'NOT_ACHIEVED'),
        ('quality_bad', '작업 인력시간 절감과 품질 보존 여부를 판정할 실험안을 제안하라.',
         '인력시간은 착수~병합 달력시간으로 측정한다. 경보가 없으면 비열등이다. 허용 한계나 관찰 기간은 정하지 않고 시간이 20% 줄면 채택한다.', 'NOT_ACHIEVED'),
        ('original_variant_bad', '조건이 바뀐 회사 전체 개발시간 20% 절감을 약속할 수 있는지 판단하고 수정 실험안을 제안하라.',
         (DOC/'artifacts/ai/variant/decision.md').read_text(), 'NOT_ACHIEVED'),
    ]
    results = []
    for name, request, response, expected in cases:
        prompt = '## 사용자 요청\n'+request+'\n## criteria_contract\n'+json.dumps(
            {'criteria':[{'id':'C1','text':request}]},ensure_ascii=False)+'\n## 산출물\n'+response
        started = time.time()
        answer = system_ai_call(prompt, system_prompt=Evaluator()._load_evaluator_prompt()+'\n'+POLICY, role='evaluate')
        results.append(dict(name=name,request=request,response=response,expected=expected,judgment=answer,
                            elapsed_s=round(time.time()-started,3),
                            matched=bool(answer and answer.strip().splitlines()[0].strip()==expected)))
        (OUT/'semantic_evaluations.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(name, results[-1]['matched'], results[-1]['elapsed_s'], flush=True)
    return results


if __name__ == '__main__':
    run()
