# 안전 정책 강제 범위

"지침으로 쓴 것"과 "기술적으로 막는 것"을 구분한다. 표의 강제 여부는 이 PC에서 확인한 범위다. 확인 근거는 `evidence/VERIFICATION-REPORT.md`.

| 정책 | Claude 채팅 | Claude Code (hook 설치 시) | Codex | ChatGPT |
| --- | --- | --- | --- | --- |
| 프롬프트만 → 도구 사용 안 함 | 지침 | PreToolUse deny | 지침 | 지침 |
| 읽기 전용 → 파일 쓰기 금지 | 지침 | Write/Edit/쓰기성 Bash deny | read-only 프로필 시 OS 차단(미검증) | 지침 |
| 읽기 전용 → Git 필터·hook 미실행 | 지침 | Bash의 `git` deny + 안전 관찰 제공 | 지침 + `git-status` 도구 | 지침 |
| 수정하지 마 | 지침 | Write/Edit deny, 실행 명령은 ask | 지침 | 지침 |
| 실행하지 마 | 지침 | 읽기 외 Bash deny | 지침 | 지침 |
| 배포·push·commit·삭제·설치·네트워크 명령 | 지침 | 항상 ask(제한 시 deny) | 승인 정책 의존 | 지침 |
| 저장소 문서가 제한 해제 | 지침 | 제한은 사용자 입력에서만 추출 → 해제 불가 | 지침 | 지침 |
| 점수 위조 방지 | qgate 사용 시 | qgate 사용 시 | qgate 사용 시 | 해당 없음 |
| 재검증 2회 한도 | 지침 | ledger CLI 사용 시 | ledger CLI 사용 시 | 지침 |

## 프롬프트 지침만으로는 강제할 수 없는 것

- Claude 채팅·ChatGPT에서 모델이 지침을 어기고 도구를 호출하는 것.
- 허용된 명령(예: 테스트 실행)이 내부에서 파일을 쓰거나 네트워크에 접근하는 것. hook은 명령 문자열만 본다. OS 샌드박스가 필요하다.
- MCP 도구의 실제 부작용. hook은 제한 활성 시 ask로 돌릴 뿐 판정하지 못한다.
- 사용자가 hook·설정을 끄거나 ledger 저장소 폴더 전체를 지우는 것(로컬에서 감지 불가, 외부 기준점 필요).
- 테스트 코드 자체를 바꿔 항상 통과하게 만드는 것. qgate의 `suite_sha256`을 에이전트가 수정할 수 없는 곳에 고정해 두고 `--expect-suite-sha256`로 비교해야 한다.

## 읽기 전용 Git 관찰 (`safe_git`)

저장소의 `.git/config`를 Git이 읽지 않도록 임시 shadow GIT_DIR(HEAD·refs·index 사본 + 하네스가 쓴 설정)을 만들고, 상속 환경변수(GIT_*)를 모두 버리며, 원격·lazy fetch·submodule·hook·fsmonitor를 끈다. Git 실행 파일은 PATH에서 찾되 프로젝트 내부에 있으면 거부하고, 작업 디렉터리는 저장소가 아닌 임시 폴더다. 임시 폴더는 프로젝트 밖에 생기며 종료 시 삭제된다. linked worktree와 알 수 없는 저장소 확장은 지원하지 않고 "unknown"을 반환한다. clean filter가 적용되지 않으므로 필터 대상 파일은 수정됨으로 보일 수 있다.
