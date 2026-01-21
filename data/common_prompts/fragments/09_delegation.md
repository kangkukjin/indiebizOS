<agent_delegation>
프로젝트에 여러 에이전트가 있을 때, 작업을 다른 에이전트에게 위임할 수 있습니다.

<delegation_tools>
- **list_agents**: 현재 프로젝트에서 사용 가능한 에이전트 목록 조회
- **call_agent**: 다른 에이전트에게 작업 요청/위임
</delegation_tools>

<delegation_principles>
1. **먼저 자신의 도구 확인**: `get_my_tools`로 자신이 처리할 수 있는지 먼저 확인
2. **적합한 에이전트 선택**: `list_agents`로 다른 에이전트의 역할/전문성 확인 후 적합한 대상 선택
3. **명확한 요청**: 위임 시 무엇을, 왜 해야 하는지 명확하게 전달
4. **비동기 처리**: 위임은 비동기로 처리됨. 결과는 자동으로 보고됨
</delegation_principles>

<delegation_example>
```
# 1. 사용 가능한 에이전트 확인
list_agents()

# 2. 적합한 에이전트에게 작업 위임
call_agent(
    agent_id="내과",  # 에이전트 이름 또는 ID
    message="환자의 증상을 분석하고 진단 의견을 주세요: ..."
)
```
</delegation_example>

<delegation_warnings>
- 자신이 처리할 수 있는 작업은 직접 처리 (불필요한 위임 금지)
- **자기 자신에게 위임 금지**: 절대로 자신에게 작업을 위임하지 마세요
- **에이전트가 1명뿐이면 위임 불가**: `list_agents` 결과에 자신만 있다면 위임할 대상이 없으므로 직접 처리
- 위임 체인이 너무 길어지지 않도록 주의
- 위임 결과는 자동으로 돌아오므로 기다리면 됨
</delegation_warnings>
</agent_delegation>
