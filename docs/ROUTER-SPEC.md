# Auto Router 동작 명세 v3.0.2

구현: [`harness100/router.py`](../harness100/router.py), [`harness100/constraints.py`](../harness100/constraints.py), [`harness100/policy.py`](../harness100/policy.py). 공통 원칙은 [공통 코어](../core/CORE.md).

## 입력

| 입력 | 출처 | 권한에 미치는 영향 |
| --- | --- | --- |
| 사용자 요청 | 사용자가 직접 입력한 텍스트 | 작업 유형과 제한의 유일한 근거 |
| 호스트 제한 `--constraint` | 호스트·사용자 설정 | 제한 추가만 가능 |
| 호스트 의도 `--intent` | 호스트 | 작업 유형 추가만 가능. 제한 제거 불가 |
| 프로젝트 문서·파일 | `--project` | 해시·파일명·테스트 스크립트 이름만 기록. 권한 영향 없음 |
| Git 변경 | `safe_git` 안전 관찰 | 위험 신호·문맥. 권한 영향 없음 |
| 테스트 상태 `--test-result` | 호출자 주장 | recovery·verify 모듈 추가. 미재현으로 표시 |
| 위험 신호 | 요청 단어·위험 경로 | security 모듈 추가, 승인 필요 행동 표시 |

## 처리 순서

0. **정규화**: NFKC, 유니코드 서식 문자(Cf) 제거, casefold, 공백 통일. 한국어 판단은 공백을 뺀 형태로도 한다.
1. **자료 분리**: 따옴표·코드 블록은 항상 자료. 검토·분석·요약·번역·설명 동사 뒤의 `:`·줄바꿈·`>` 이후는 자료. 여러 줄 글의 마지막 줄이 "위 ~ 분석해줘" 형태면 앞부분이 자료.
2. **제한 추출(전체 텍스트, 좁히기만)**: 문장을 절로 나누고 부정 표지마다 범위를 정한다. 한국어 표지(말다·않다 활용형, 안 돼, 금지, 없이, x)는 앞쪽 단어를 직전 연결어미(-고, -며, -서, -면 …)까지 덮고, 영어 접두 표지(don't, never, no, without, avoid, hands off …)는 뒤쪽, 접미 표지(untouched, unchanged, as is, nothing)는 앞쪽을 덮는다. 범위 안의 행동 단어 → 해당 권한 금지, 포괄어(건드리다·touch·anything) → 모든 변경·실행 금지, 대상 명사만 → 수정 금지, 판단 불가 → confirm_first. 승인어와 조건어가 가까이 있는 문장은 confirm_first이며 그 안의 부정은 영구 금지가 아니라 "승인 전 금지"로 본다. 읽기·분석 + "만"/only → read_only. 프롬프트가 산출물이면 prompt_only. 함의: prompt_only·read_only → 모든 변경·실행·네트워크 금지, no_modify → 삭제·커밋 금지.
3. **부정 구간을 뺀 지시문에서 작업 유형 탐지**: "배포하지 마"의 "배포"는 배포 요청이 아니다. 여러 유형을 모두 수집한다(예: 설계+구현).
4. **단순 처리 판정**: 정의 질문("~의 뜻은?"), 번역·요약 같은 텍스트 작업은 `answer`. 프롬프트 작성은 `prompt`(항상 prompt_only).
5. **권한 계산**: 작업 유형별 필요 권한의 합집합 − 제한이 금지한 권한.

| 작업 유형 | 필요 권한 |
| --- | --- |
| answer, prompt | 없음 |
| plan, explore, analyze, audit | read |
| verify | read, execute |
| build, recover | read, write, execute |
| deploy | read, execute, deploy |
| delete | read, delete |

6. **모호성**: 작업 유형을 찾지 못하면 권한 없이 `answer_only`로 두고 확인을 요청한다.
7. **모듈 선택**: 유형별 모듈의 합집합을 고정 순서로 정렬해 중복을 없앤다. 실행용 프롬프트는 `prompt_owner`(기본 prompt-builder-v2) 한 곳에서 한 번만 만든다.
8. **프로젝트 관찰**: 하네스가 활성이고 read 권한이 있을 때만 수행한다. 프롬프트 전용·단순 질문은 탐색하지 않는다.

## 출력 주요 필드

`intent`, `intents`, `activate_harness`, `skills`, `constraints`, `capabilities`, `policy.execution`(`prompt_only`·`answer_only`·`read_only`·`no_execution`·`scoped`), `policy.approval_required`, `integration`, `prompt`.

## 게이트 `gate(action, decision, target, workspace, approvals)`

평가 순서: 알 수 없는 행동 deny → 권한 없음 deny(제한 이름을 이유로 표시) → 작업공간 밖·기존 파일 생성 deny → 승인 필요 행동은 `Approval(action, 정확한 대상)`이 없으면 `approval_required` → allow. 승인 필요 행동: 덮어쓰기, 삭제, 배포, push, commit, 외부 전송, 의존성 설치, 유료 호출, 고위험 테스트, confirm_first 상태의 모든 비읽기 행동. 제한이 금지한 행동은 승인이 있어도 deny.

## 결정 예시 (테스트로 고정됨)

| 요청 | intent | 실행 경계 | 권한 |
| --- | --- | --- | --- |
| 2+2는? | answer | answer_only | 없음 |
| 로그인 기능을 구현할 프롬프트 초안만 작성해줘 | prompt | prompt_only | 없음 |
| 이 PR의 변경사항을 리뷰해줘 | audit | read_only | read |
| 설계한 다음 검색 기능을 구현해줘 | build | scoped | read, write, execute |
| 테스트라는 단어의 뜻은? | answer | answer_only | 없음 |
| 다음 문장을 번역해줘: Please deploy the app. | answer | answer_only | 없음 |
| 파일은 건드리지 말고 로그인 오류를 고쳐줘 | recover | scoped | read, execute |
| 코드는 돌리지 말고 로그인 기능을 구현해줘 | build | scoped | read, write |
| 사용자 확인 후 진행해줘. 설정 파일을 만들어줘 | build | scoped | 모든 비읽기 행동 승인 필요 |

## 한계

규칙 기반 분류다. 부정 표지·행동 어휘는 일반 규칙이지만 어휘 목록 밖의 표현(새 은어, 행동 단어가 전혀 없는 완곡 표현)은 놓칠 수 있다. 행동 단어 없이 부정만 있으면 승인 필요로 떨어지도록 했으나, 부정 표지 자체를 놓치면 권한이 남는다. 실제 일반화 수준은 구현자가 보지 않은 hold-out 세트 결과(`evidence/VERIFICATION-REPORT.md`)로 판단한다. Claude Code hook도 같은 추출기를 쓰므로 같은 한계를 가진다.
