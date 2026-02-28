# 워크플로우 저장 & 실행 가이드

## 워크플로우란?

자주 쓰는 IBL 파이프라인을 **이름 붙여 저장**하고, 나중에 이름만으로 실행하는 기능.
저장된 워크플로우는 `data/workflows/{id}.yaml` 파일로 관리된다.

---

## 저장

```
execute_ibl(node="system", action="save_workflow", params={
  "name": "구글신문",
  "description": "구글 뉴스 수집 후 신문 HTML 생성",
  "pipeline": "[source:search_news](\"google\") >> [forge:create](\"newspaper.html\") {type: \"newspaper\"}"
})
```

### params 필드

| 필드 | 필수 | 설명 |
|------|------|------|
| name | ✅ | 워크플로우 이름 (실행 시 target으로 사용) |
| description | - | 설명 |
| pipeline | ✅ | IBL 파이프라인 문자열 |

저장 시 name을 기반으로 ID가 자동 생성된다 (예: "구글신문" → `구글신문`).

---

## 실행

```
execute_ibl(node="system", action="run", target="구글신문")
```

target에 워크플로우 이름 또는 ID를 넣으면 저장된 pipeline이 실행된다.

---

## 목록 조회

```
execute_ibl(node="system", action="list_workflows")
```

저장된 모든 워크플로우의 ID, 이름, 설명을 반환.

---

## 상세 조회

```
execute_ibl(node="system", action="get_workflow", target="구글신문")
```

특정 워크플로우의 전체 내용(pipeline, steps 등)을 반환.

---

## 삭제

```
execute_ibl(node="system", action="delete_workflow", target="구글신문")
```

---

## 사용 시나리오

### 사용자가 워크플로우 저장을 요청할 때
1. 사용자의 요청에서 이름, 설명, 파이프라인 추출
2. `save_workflow`로 저장
3. 저장된 ID 반환

### 사용자가 워크플로우 실행을 요청할 때
1. `list_workflows`로 목록 확인
2. 매칭되는 워크플로우 찾기
3. `run`으로 실행

### "OOO 워크플로우 만들어줘" 같은 요청
1. 사용자의 의도를 파악하여 적절한 파이프라인 작성
2. `save_workflow`로 저장
3. 저장 완료 안내
