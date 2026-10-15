# 73회차 저녁 점검 — 원격 기기 6대 중 응답 4대

## 기기표
- 맥12 guestpc-3fd796167b18 pc/resident-v1: 연결 true 멈춤 false 응답 true 
- KHJoffice guestpc-7da97e970821 pc/resident-v1: 연결 true 멈춤 true 응답 false paused
- 맥26 guestpc-9dc41d53987d pc/resident-v1: 연결 false 멈춤 false 응답 false not_connected
- 삼성1 guestpc-4e51c614b25b phone/indiebiz-v1: 연결 true 멈춤 false 응답 true 
- tv1 guestpc-70e163471313 pc/resident-v1: 연결 true 멈춤 false 응답 true 
- 삼성0 guestpc-fc7b12fba936 phone/indiebiz-v1: 연결 true 멈춤 false 응답 true 

## 작업표 (12행×2, 기대 합계 156)
- 맥12 (guestpc-3fd796167b18): 방식 pc_shell_python, 합계 일치 true, 재사용 true
- KHJoffice (guestpc-7da97e970821): 방식 pc_shell_python, 합계 일치 true, 재사용 true
- 맥26 (guestpc-9dc41d53987d): 방식 unavailable, 합계 일치 false, 재사용 false
- 삼성1 (guestpc-4e51c614b25b): 방식 phone_ibl, 합계 일치 true, 재사용 true
- tv1 (guestpc-70e163471313): 방식 pc_shell_python, 합계 일치 true, 재사용 true
- 삼성0 (guestpc-fc7b12fba936): 방식 phone_ibl, 합계 일치 true, 재사용 true

## 사진 연쇄
{"device_id": "guestpc-4e51c614b25b", "captured": true, "phone_path": "/data/user/0/com.indiebiz.phoneagent/files/photos/photo_1792048343627.jpg", "phone_sha256": "89f30f6b69404e8edcab3739c756c31c6c5e70856323b62360d64c46a04c8c62", "phone_size": 1853398, "previous_sha256": null, "hash_unchanged": false, "blocked_at": "collect", "blocked_reason": "폰 ops 에 transfer 없음(실행 계약 1 미설치) — 허브 회수·PC 재계산 미실행", "hub_sha256": null, "pc_sha256": null, "all_equal": null, "hash_step": {"ok": true, "sha256": "89f30f6b69404e8edcab3739c756c31c6c5e70856323b62360d64c46a04c8c62", "size": 1853398, "dir": "/data/user/0/com.indiebiz.phoneagent/files/photos", "name": "photo_1792048343627.jpg", "receipt": {"kind": "guestpc", "task_id": "257a09ef470c4c6997f2e3e018f74344"}}, "receipts": {"photo": {"kind": "guestpc", "task_id": "c931bbb4719e4bf69ef2e5cb9a543d9b"}}, "reused": true, "reuse_note": "재촬영 0 — 이전 사진 파일의 해시만 다시 읽음"}

## 못 한 일
[{"device_id": "guestpc-7da97e970821", "alias": "KHJoffice", "what": "문진·처리", "why": "paused"}, {"device_id": "guestpc-9dc41d53987d", "alias": "맥26", "what": "문진·처리", "why": "not_connected"}, {"device_id": "guestpc-9dc41d53987d", "what": "처리", "why": "not_connected"}]

상태표·신원·접수증·원격 경로 전문은 result.json. 사진 내용은 보지도 저장하지도 않았다(크기·해시만).
소리·화면·설정 변경 0. 응답하지 않은 기기는 다른 기기로 대신하지 않았다.
