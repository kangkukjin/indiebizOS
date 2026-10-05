"""Synthetic manual corpus; the task is implemented separately in IBL."""
import json
from pathlib import Path


def generate(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    docs=[]
    for n in range(12):
        lines=[]
        for i in range(160):
            term=['주의사항','정기점검','오류복구'][(i+n)%3]
            lines.append(f'문서 {n:02d} 항목 {i:03d}: {term}. 장비 상태를 확인하고 작업 번호를 기록한다. 정확한 원문 위치와 공백을 보존한다. '+ ('추가 검토 필요. '*((i%7)+1)))
        body='  시작 공백 보존\n\n'+'\n\n'.join(lines)+'\n끝 공백 보존  '
        docs.append({'id':f'D{n:02d}','title':f'시험 매뉴얼 {n}','text':body})
    docs.extend([{'id':'EMPTY','title':'빈 문서','text':''},{'id':'SPACE','title':'공백 문서','text':' \n\t  '}])
    (folder/'documents.json').write_text(json.dumps({'documents':docs},ensure_ascii=False),encoding='utf-8')
    (folder/'queries.json').write_text(json.dumps(['주의사항','정기점검','오류복구','존재하지않는검색어'],ensure_ascii=False),encoding='utf-8')
    return docs


if __name__=='__main__':
    import sys
    generate(sys.argv[1])
