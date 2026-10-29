# Electron 내장 브라우저 종료 크래시와 런처 재연결 수리

## 관측과 원인 범위

macOS 진단 보고서의 2026-10-29 01:52·17:58·19:47·21:40 네 건은
Electron 39.2.7 메인 스레드 `CrBrowserMain`에서 같은 SIGSEGV로 종료됐다.
주소는 `0xefefefefefeff007`이며, 해당 빌드의 공식 arm64 Breakpad 심볼
(UUID `4C4C443555553144A1C47C0945B428000`)로 아래 흐름을 확인했다.

```
WebContentsTreeNode::DestroyOwnedInnerWebContents
WebContentsImpl::~WebContentsImpl
FrameTree::Shutdown
RenderFrameDevToolsAgentHost::FrameDeleted
RenderFrameDevToolsAgentHost::DestroyOnRenderFrameGone
DevToolsAgentHostImpl::ForceDetachAllSessionsImpl + 100
```

심볼 없는 ips에 표시된 V8·PNG 등의 가장 가까운 공개 함수 이름은 실제
호출 함수로 해석하지 않는다. 직접 관측된 실패 경로는 내장 웹뷰 파괴 중
DevTools 세션 정리이며, AI 내장 브라우저의 `webContents.debugger` 사용과
관련된다. 어느 사용자 동작이나 사이트가 네 건 각각을 유발했는지는 미확정이다.

[Electron #53819](https://github.com/electron/electron/issues/53819)는 연결했던
웹뷰의 제거에 따른 유사 크래시와 단순 detach·지연의 한계를 보고한다.
이 이슈가 닫혔다는 사실만으로 해결을 판단하지 않았다.
[39.2.7 소스](https://github.com/electron/electron/blob/v39.2.7/shell/browser/api/electron_api_debugger.cc)와
[44.10.0 소스](https://github.com/electron/electron/blob/v44.10.0/shell/browser/api/electron_api_debugger.cc)를
대조하면 후자에는 Debugger 소멸 시 native client 해제·해제 중 메시지 차단과,
같은 WebContents 내 프레임 교체 때 불필요한 세션 재연결을 피하는 처리가 있다.
객체 수명 수정은 [44.4.1 릴리스](https://releases.electronjs.org/release/v44.4.1)에도 명시돼 있다.

별도 결함으로 `data/electron_dev.log` 923,358,664바이트에서 `onerror` 소켓
폐기 메시지 24,545,946건을 관측했다. 기존 폐기는 `onclose`만 제거한 채
`close()`를 호출하고 뒤늦게 전역 참조를 비웠다. 닫는 도중 다시 오류가
발생하면 같은 소켓의 폐기로 재진입할 수 있었고, 오래된 콜백이 새 소켓을
닫을 수도 있었다. 위 네 native 크래시의 직접 원인과는 구분한다.

## 변경

- Electron을 수정이 포함된 `44.10.0`으로 고정하고 lockfile과 로컬 바이너리를 갱신.
  소스 설치·빌드 Node 최소값은 22.12, 빌드 CI는 Node 24. 배포용 백엔드
  도구의 별도 Node 번들 버전은 이 설치 도구와 다른 계약이다.
- `EmbeddedTabs`는 사용 중인 debugger wrapper를 명시 보유한다. AI 제어
  반환·앱이 요청한 탭 종료 전에 detach하고, UI/부모 창에서 제거된 탭의
  기록·리스너·활성 소유권도 정리한다. 닫힌 탭의 새 CDP 명령을 거절한다.
  사용자 탭을 보존하는 제어 반환과 실제 탭 삭제는 계속 구분한다.
- `launcher-connection.js`가 소켓·heartbeat·재시도 타이머를 소유한다.
  참조와 모든 콜백을 먼저 회수한 다음 close한다. 콜백은 자신이 생성된
  소켓과 현재 소켓을 대조한다. 재시도는 단 하나이며 앱 종료 뒤 되살아나지
  않는다. 연결 대기 및 pong 미응답은 제한 시간 뒤 복구한다.

## 검증과 한계

회귀의 집은 `backend/test_electron_lifecycle.py`이며 Node 단위 시험과 실제
Electron 자식 프로세스 시험을 함께 실행한다. 실제 시험은 별도 userData와
로컬 HTTP 페이지만 쓰며 라이브 백엔드·사용자 쿠키·키체인을 사용하지 않는다.
소스 CI의 macOS 시험 준비에도 Electron 바이너리 설치를 추가했다.

- 소켓의 동기 error 재진입, 100회 실패, 이전 세대 콜백, pong 시간 초과,
  전송 실패, 종료 뒤 재연결 금지와 탭 해제·재연결을 검사한다.
- native 시험은 snapshot·click·iframe 읽기·페이지 이동 뒤 네 종료 경로
  (CDP 대기 중 DOM 제거, 앱의 tab close, 이동 중 DOM 제거, 부모 창 종료)를
  반복하고 강제 GC 뒤 기록·활성 탭·guest가 남지 않는지 확인한다.
- 최초 200회 시험에서 iframe 로딩 전 본문 검사가 발견되어 fixture의
  준비 사건을 `dom-ready`에서 `did-finish-load`로 보완했다. assertion은 유지했다.
  보완한 fixture의 44.10.0 실제 실행은 200회 모두 통과했다. 관련 Python
  검사 51개, Electron/런처 Node 검사, TypeScript 검사와 production 빌드,
  실제 보조 창 3개의 언어 전환·재실행 지속성도 통과했다.
- 기존 39.2.7에서도 단순 로컬 100회 반복은 통과했다. 따라서 반복 시험 통과가
  이전 결함의 결정적 재현·제거 증명은 아니다. 수정된 native 소스와 관측된
  실패 경로, 실제 기능·종료 회귀를 함께 근거로 삼는다.
- 장시간 사용·외부 사이트 전체·Windows 설치 실행은 이 Mac의 검증 범위 밖이다.

실행 로그와 JUnit은 로컬 `outputs/electron-crash-check/`에 보관한다.
