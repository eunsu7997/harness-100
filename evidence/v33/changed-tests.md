# v3.3에서 바꾼 기존 테스트 5개

비교 대상: `harness-100-v3.2-cc/tests/`(원본)와 `harness-100-v3.3-cc/tests/` (#1~#4 `test_v31_grant.py`, #5 `test_v32.py`).

| # | 테스트 | 바꾸기 전 기대값 | 바꾼 뒤 기대값 | 이유 | 방향 |
| --- | --- | --- | --- | --- | --- |
| 1 | `HookDecisions.test_modes_without_prompt_deny_outside_grants` | grant(`수정 README.md · 실행 pytest`) 뒤 모든 모드에서 Edit·Bash = allow | plan 모드만 **deny**, 나머지 모드는 allow | 결정 3: plan 모드는 grant와 관계없이 쓰기·실행 deny | **엄격** (plan: allow → deny) |
| 2 | `HookDecisions.test_reads_and_skills_never_denied` | 모든 모드에서 Read·Grep·Skill·`ls -la`(Bash) = defer | plan 모드의 `ls -la`(Bash)만 **deny**, 나머지는 defer | 결정 3: 읽기 전용 명령도 실행이므로 plan에서 deny | **엄격** (defer → deny) |
| 3 | `RoundTwoRules.test_plan_mode_and_outside_project_writes_are_denied` | `승인: 수정 **` 뒤 plan 모드 Write `probe.txt` = allow | **deny** | 결정 3 | **엄격** (allow → deny) |
| 4 | `RoundTwoRules.test_rule_b_only_a_whole_single_line_message_is_a_grant` | `"승인: 수정 src/**\n이제 고쳐줘"` = grant 아님 | **grant 1개**(인정). 거부 목록에 첫 줄 위장 8개 추가: 빈 줄, `From:`, `아래 로그:`, `>` 인용, 두 번째 grant 줄, 대문자 머리말, 6줄 요청, 401자 요청 | 수정 4(사용자 결정): 첫 줄 단독 grant + 짧은 요청 인정 | **완화** (거부 → 허용) |
| 5 | `tests/test_v32.py::Fix2ExactCommand.test_v32_fix2_powershell_backslash_is_literal` 마지막 단정 (재검증 1회차) | Bash `"pytest" -q` = allow(POSIX 따옴표 해제 후 토큰 같음) | **allow 아님** | 재검수 A491~A552: 명세 v3.2 2절 "공백 개수 차이만 무시". 원문 비교로 변경(GRANT-SPEC E4) | **엄격** (allow → defer) |

## 거부 → 허용으로 바뀐 기대값

**1건(#4).** 근거는 사용자 지시 v3.3 1-4입니다. "메시지 첫 줄에 단독으로 있는 grant 줄을 인정하고, 둘째 줄부터는 요청으로 본다."

- 같은 테스트에 붙여넣기 위장 8개를 거부 단정으로 추가했습니다.
- `tests/test_v33.py::Fix4FirstLineGrant`가 다음 두 가지를 고정합니다.
  - 붙여 넣은 글이 grant 줄로 시작해도 allow되지 않음(9개 사례, default·bypassPermissions)
  - 첫 줄 grant 메시지 안의 "읽기만" 제한은 그대로 적용됨
