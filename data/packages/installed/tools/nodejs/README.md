# Node.js 도구

## 목적

에이전트가 JavaScript/Node.js 코드를 실행할 수 있게 합니다.

## 요구사항

- Node.js가 시스템에 설치되어 있어야 합니다
- `node` 명령이 PATH에 있어야 합니다

## 설치 확인

```bash
node --version
```

## 사용 예시

에이전트에게 "자바스크립트로 1부터 10까지 합 계산해줘" 요청 시:

```javascript
let sum = 0;
for (let i = 1; i <= 10; i++) sum += i;
console.log(sum);
```

## 제한사항

- 실행 시간: 30초
- 네트워크 접근: 가능 (fetch, http 등)
- 파일 시스템: 프로젝트 경로 내에서 가능
