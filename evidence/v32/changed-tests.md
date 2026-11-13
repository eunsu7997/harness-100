# v3.2에서 바꾼 기존 테스트 7개

비교 대상은 `harness-100-v3.1-cc/tests/`(원본)와 `harness-100-v3.2-cc/tests/`(round 0 고정본, `evidence/v32/round0/source-sha256-round0.txt`)이다.

방향 표시:
- **엄격**: 허용이던 것을 허용하지 않도록 바꿨거나, 불허 단정을 추가했다.
- **동일**: 판정 기대는 그대로이고 대상만 맞췄다.
- **완화**: 불허이던 것을 허용하도록 바꿨다.

| # | 테스트 | 바꾸기 전 기대값 | 바꾼 뒤 기대값 | 이유 | 방향 |
| --- | --- | --- | --- | --- | --- |
| 1 | `test_safety.Gate.test_restrictions_block_actions` | gate `create_file`("코드는 돌리지 말고 로그인 기능을 구현해줘") = **allow** | 승인 없이 = **approval_required**. 정확한 Approval이 있으면 = allow(새 단정) | 수정 4: gate는 정확히 일치하는 승인에서만 allow | **엄격** (allow → approval_required) |
| 2 | `test_evidence_hook.Hook.test_model_cannot_tamper_with_state_and_corruption_fails_closed` | 상태 파일 `s1.json` 삭제·쓰기 = deny, 손상 후 Write = deny | 같은 기대(deny). 대상 파일만 `sha256("s1").json`으로 바꾸고, 파일이 실제로 있는지 단정 추가 | 수정 3: 상태 파일 이름이 세션 ID 해시로 바뀜. 옛 이름을 그대로 두면 엉뚱한 파일을 손상시켜 시험이 무의미해짐 | **동일** (+ 무의미해지는 것을 막는 단정) |
| 3 | `test_v31_grant.GrantSyntax.test_matching` | grant `실행 pytest`가 `pytest -q tests`를 덮음(True, 접두어 일치). 불허 9개: `pytestx`, `pytest && rm -rf .`, `pytest; curl x`, `pytest > out.txt`, `pytest \| tee x`, `py.test`, `python -m pytest`, ``pytest `rm x` ``, `pytest $(rm x)` | grant를 `실행 pytest -q tests`로 정확히 적고 그 명령만 True(공백 차이는 같은 토큰). 불허 10개: `pytest`, `pytest -q`, `… -x`, `… --basetemp=/`, `pytestx`, `… && rm -rf .`, `…; curl x`, `… > out.txt`, `python -m pytest -q tests`, `./pytest -q tests`. 다른 폴더에서 같은 명령 = None(새 단정). 수정 판정은 hook이 검사한 실제 경로로 함 | 수정 2: 접두어 일치 폐지, (폴더, 전체 명령) 정확 일치 | **엄격**. 단 원래의 불허 사례 4개(`pytest \| tee x`, `py.test`, ``pytest `rm x` ``, `pytest $(rm x)`)가 목록에서 빠짐 → 테스트 범위 축소. 다음 수정 회차에서 복원 예정 |
| 4 | `test_v31_grant.HookDecisions.test_grant_allows_only_its_scope_and_restrictions_win_later` | grant `실행 pytest` 뒤 `pytest -q` = allow | grant를 `실행 pytest -q`로 바꾸고 `pytest -q` = allow. `pytest` ≠ allow(새 단정) | 수정 2: 정확 일치. 허용 사례는 grant를 그 명령으로 좁혀 유지 | **엄격** (grant 문구 축소 + 불허 단정 추가) |
| 5 | `test_v31_grant.HookDecisions.test_risky_commands_need_a_prefix_that_names_them` | grant `실행 git · 실행 pip · 실행 npm run` 뒤 `git status` = allow, 위험 명령 7개 ≠ allow, grant `실행 git push origin main · 실행 npm run deploy` 뒤 두 명령 allow | grant를 `실행 git status · 실행 pip list · 실행 npm run build`로 바꾸고 `git status` = allow. 불허에 `git`, `git push origin main --force` 추가. 나머지 같음 | 수정 2: 접두어 grant(`실행 git`)는 v3.2에서 `git` 하나만 덮음 | **엄격** (grant 문구 축소 + 불허 단정 2개 추가) |
| 6 | `test_v31_grant.RoundTwoRules.test_rule_a_risky_actions_need_the_action_named` | `실행 git` 뒤 `git status` = **allow**. grant `실행 git push` 뒤 `git push origin main` = allow. grant `실행 pip install requests` 뒤 `python -m pip install requests` = **allow** | `git status` ≠ allow. grant를 `실행 git push origin main`으로 바꾸고 그 명령 = allow. `python -m pip install requests` ≠ allow. 불허에 `git push`, `git push origin main --force` 추가 | 수정 2: 정확 일치(정규화·접두어 없음) | **엄격** (allow → not allow 2건, 불허 단정 추가) |
| 7 | `test_v31_grant.RoundTwoRules.test_read_only_command_granted_is_allowed` | grant `실행 echo` 뒤 `echo hi` = allow(bypassPermissions) | grant를 `실행 echo hi`로 바꾸고 `echo hi` = allow. `echo bye` ≠ allow(새 단정) | 수정 2: 정확 일치 | **엄격** (grant 문구 축소 + 불허 단정 추가) |

## 거부 → 허용으로 바뀐 기대값

**없음.** 어떤 단정도 불허(deny / not allow / None)에서 허용(allow / True)으로 바뀌지 않았다.

허용 기대를 유지한 경우(#3·#4·#5·#6·#7의 양성 대조)는 모두 grant 문구를 그 명령 하나로 좁힌 뒤 그 명령만 허용하는 형태다. 예: `실행 pytest`를 `실행 pytest -q`로 좁혔다. 허용 범위가 넓어진 경우는 없다.

## 범위가 줄어든 점 (숨기지 않음)

- #3에서 원래 있던 불허 사례 4개가 빠졌다: `pytest | tee x`, `py.test`, ``pytest `rm x` ``, `pytest $(rm x)`.
  - v3.2 규칙(정확 일치, 셸 제어 문자 거부)에서도 넷 다 불허 대상이다. 같은 종류의 사례(`&&`, `;`, `>`)가 남아 있고, `tests/test_v32.py::Fix2ExactCommand::test_v32_fix2_exact_command_only`가 `&&`·`;` 변형을 따로 확인한다.
  - 그래도 이 테스트의 범위가 줄어든 것은 사실이다. round 0 코드 고정 이후라 즉시 되돌리지 않았고, 다음 수정 회차(round 1)에서 복원한다.
