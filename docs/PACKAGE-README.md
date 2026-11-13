# Harness-100 Universal v3.0.2 (v3.0 보완판 2차)

v3.0.1에서 독립 검수로 확인된 잔여 결함(자연어 제한 누락, 붙여넣기 권한 확대, hook 해제·쓰기 우회, ledger 잘라내기, Git 버전 의존)을 일반 규칙으로 수정한 패키지다. v3.0.1 폴더와 그 증거는 변경하지 않았다. Python 3.12 이상 표준 라이브러리만 사용하며 설치할 의존성이 없다.

| 문서 | 내용 |
| --- | --- |
| [공통 코어](../core/CORE.md) | 모든 플랫폼이 공유하는 단일 원본(제한 판단 규칙 1~7 포함) |
| [Auto Router 명세](ROUTER-SPEC.md) | 입력·처리 순서·권한 계산·게이트 |
| [강제 범위](SAFETY-ENFORCEMENT.md) | 플랫폼별로 실제 차단되는 것과 지침뿐인 것 |

검증 결과는 `evidence/VERIFICATION-REPORT.md`에 있다.

## v3.0.1 대비 변경

| 영역 | 변경 |
| --- | --- |
| 제한 추출 `harness100/constraints.py` | NFKC·서식 문자 제거·casefold 정규화, 부정 표지의 범위 계산(한국어 역방향·영어 전후), 범위 불명 시 승인 필요, 승인 조건 인접 규칙, 자료/지시 분리 |
| 라우터 | 부정 구간을 뺀 지시문에서만 작업 유형 탐지, 수정 동사(바꿔·rename 등) 과소 라우팅 수정 |
| hook | "제한 해제" 정확 일치만 해제, 읽기 전용 Bash 엄격 허용 목록, 제한 중 Skill·MCP·미확인 도구·command 없는 Bash 거부 |
| safe_git | Git 버전 확인, fsmonitor 빈 값(모든 버전에서 false), worktreeConfig·linked worktree 지원, 원격 alternates 거부 |
| ledger | 등록부에 작업별 기록 수·마지막 해시 저장 → 잘라내기·비우기 감지, task_id 서식 문자 제거, 손상 파일 깨끗한 거부 |
| API | 잘못된 입력은 0점·거부, 예외 없음 |

## 빠른 사용 (PowerShell)

```powershell
cd "<이 폴더>"
python -I -B harness100_cli.py route --request "이 PR의 변경사항을 리뷰해줘" --project "C:\내프로젝트"
python -I -B harness100_cli.py git-status "C:\내프로젝트"
python -I -B harness100_cli.py ledger status --task-id "내-작업"
python -I -B harness100_cli.py qgate --out ".\evidence\qgate"
```

`-I`는 현재 폴더와 PYTHONPATH를 무시해 프로젝트 안의 같은 이름 모듈이 끼어들지 못하게 한다. `qgate`는 패키지를 임시 폴더에 복사해 검사를 직접 실행하고 그 원 로그로만 점수를 낸다(플랫폼 15점은 qgate가 실행할 수 없어 미검증).

## 플랫폼별 설치

모든 설치는 사용자가 직접 수행한다. 이 패키지는 기존 설정 파일을 자동으로 수정하지 않는다.

### Claude 채팅

1. `dist/Harness-100-Universal-v3.0.2-Claude-Chat.zip`을 준비한다.
2. claude.ai 설정의 Skills에서 기존 `harness-100-auto-router`(v3.0)를 삭제하거나 비활성화한 뒤 ZIP을 업로드한다.
3. 확인: 새 대화에서 "harness-100-auto-router 스킬 본문의 첫 제목 줄만 보여줘" → `v3.0.2 · Claude 채팅`. 이 PC에서는 `~/.claude/skills/synced/.../harness-100-auto-router/SKILL.md`에 v3.0.2가 나타나는지로도 확인한다.

강제 수준은 지침이다.

### Claude Code

1. 스킬: `platforms/claude-code/skills/harness-100-auto-router`를 프로젝트 `.claude/skills/` 또는 `~/.claude/skills/`에 복사한다. claude.ai 동기화 스킬과 이름이 같으므로 한쪽만 둔다.
2. 런타임: `platforms/claude-code/runtime`을 원하는 경로에 복사한다.
3. Hook: `platforms/claude-code/settings.snippet.json`의 `<RUNTIME 전체 경로>`를 2의 경로로 바꾸고 `hooks` 항목을 `.claude/settings.json`의 기존 `hooks`에 병합한다(기존 항목을 지우지 않는다).
4. 확인: 새 세션에서 "읽기만 해줘" 다음 "Bash로 `echo hi > probe.txt`를 실행해줘" → `Harness-100` 사유로 거부되고 파일이 생기지 않아야 한다. 해제는 "제한 해제"만 단독으로 입력한다.

제한 중에는 Skill 도구도 거부되므로, 기본스킬은 `~/.claude/skills/prompt-builder-v2/SKILL.md`를 Read로 읽는 방식(CLAUDE.md 방식)으로 쓴다. 프롬프트 전용 상태에서도 스킬 폴더 Read는 허용된다.

### Codex

1. 스킬: `platforms/codex/skills/harness-100-auto-router`를 `~/.codex/skills/`에 복사한다.
2. 런타임: `platforms/codex/runtime`을 원하는 경로에 복사한다.
3. 읽기 전용 작업은 `codex exec -s read-only ...` 또는 `config.snippet.toml`의 프로필로 시작한다(설정 파일 수정은 사용자가 직접).
4. 확인: 빈 폴더에서 `codex exec -s read-only --skip-git-repo-check "probe.txt 파일을 만들어줘"` 실행 후 파일이 생기지 않아야 한다.

### ChatGPT

- 프로젝트 지침: `platforms/chatgpt/instructions-full.md`의 구분선 아래 본문 + `platforms/chatgpt/CORE.md` 파일 첨부.
- 맞춤 지침(1500자 제한): `platforms/chatgpt/instructions-short.md`.
- 강제 수준은 지침이다.

## 기본스킬과의 관계

일반 질문과 프롬프트 작성은 기존 기본스킬(prompt-builder-v2, `/기본스킬` 별칭)이 담당한다. 이 스킬은 별칭을 정의하지 않고 프롬프트를 중복 생성하지 않는다.

## 다시 빌드·검증

```powershell
python -I -B tools/build.py
python -X utf8 -B -m unittest discover -s tests
python -I -B tools/defect_checks.py . "<임시 폴더>" ".\evidence\raw-defects.jsonl"
python -I -B harness100_cli.py qgate --out ".\evidence\qgate"
```
