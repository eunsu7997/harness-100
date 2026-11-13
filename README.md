# Harness-100 Universal v3.0.1 (v3.0 보완판)

v3.0 MVP를 보존한 채 P0(읽기 전용 부작용, 자연어 제한 누락)과 P1(점수 위조, 재검증 우회)을 수정한 패키지다. Python 3.12 이상 표준 라이브러리만 사용하며 설치할 의존성이 없다.

| 문서 | 내용 |
| --- | --- |
| [공통 코어](core/CORE.md) | 모든 플랫폼이 공유하는 단일 원본 |
| [Auto Router 명세](docs/ROUTER-SPEC.md) | 입력·처리 순서·권한 계산·게이트 |
| [강제 범위](docs/SAFETY-ENFORCEMENT.md) | 플랫폼별로 실제 차단되는 것과 지침뿐인 것 |

검증 결과는 `evidence/VERIFICATION-REPORT.md`에 있다.

## 폴더 구성

| 경로 | 용도 |
| --- | --- |
| `core/` | 공통 코어와 모듈(단일 원본) |
| `adapters/` | 플랫폼별 SKILL.md 템플릿과 ChatGPT 지침 원문 |
| `harness100/` | 라우터·제한 추출·게이트·안전 Git·ledger·품질 게이트 |
| `hooks/claude_code_hook.py` | Claude Code 도구 차단 hook |
| `platforms/` | `tools/build.py`가 생성한 플랫폼별 설치본 |
| `dist/` | Claude 채팅 업로드용 ZIP |
| `tests/`, `tools/` | 단위 테스트, 적대적 검사기, 채점기, 빌드 |
| `evidence/` | 원 로그, 재채점, ledger, 보존 해시 |

## 빠른 사용 (PowerShell)

```powershell
cd "<이 폴더>"
python -I -B harness100_cli.py route --request "이 PR의 변경사항을 리뷰해줘" --project "C:\내프로젝트"
python -I -B harness100_cli.py git-status "C:\내프로젝트"
python -I -B harness100_cli.py ledger status --task-id "내-작업"
python -I -B harness100_cli.py qgate --out ".\evidence\qgate"
```

`-I`는 현재 폴더와 PYTHONPATH를 무시해 프로젝트 안의 같은 이름 모듈이 끼어들지 못하게 한다. `qgate`는 패키지를 임시 폴더에 복사해 검사를 직접 실행하고 그 원 로그로만 점수를 낸다. 플랫폼 검사는 실행하지 않으므로 qgate 단독 최대 점수는 85점이며 플랫폼 15점은 미검증으로 남는다.

## 플랫폼별 설치

모든 설치는 사용자가 직접 수행한다. 이 패키지는 기존 설정 파일을 자동으로 수정하지 않는다.

### Claude 채팅

1. `dist/Harness-100-Universal-v3.0.1-Claude-Chat.zip`을 준비한다.
2. claude.ai 설정의 Skills에서 기존 `harness-100-auto-router`(v3.0)를 삭제하거나 비활성화한 뒤 ZIP을 업로드한다. 같은 이름이 두 개 있으면 중복 선택될 수 있다.
3. 확인: 새 대화에서 "harness-100-auto-router 스킬 본문의 첫 제목 줄을 보여줘" → `v3.0.1 · Claude 채팅`이 보여야 한다. 이 PC에서는 동기화 폴더 `~/.claude/skills/synced/.../harness-100-auto-router/SKILL.md`에 v3.0.1이 나타나는지로도 확인할 수 있다.

강제 수준은 지침이다. 도구 차단은 되지 않는다.

### Claude Code

1. 스킬: `platforms/claude-code/skills/harness-100-auto-router`를 프로젝트의 `.claude/skills/`(해당 프로젝트만) 또는 `~/.claude/skills/`(전체)에 복사한다. claude.ai에서 동기화된 같은 이름의 스킬이 있으면 둘 다 보이므로 claude.ai 쪽을 v3.0.1로 교체하거나 한쪽만 둔다.
2. 런타임: `platforms/claude-code/runtime` 폴더를 공백 없는 경로(예: `C:\tools\harness100-runtime`)에 복사한다.
3. Hook: `platforms/claude-code/settings.snippet.json`의 `<RUNTIME 전체 경로>`를 2의 경로로 바꾸고, `hooks` 항목을 프로젝트 `.claude/settings.json` 또는 `~/.claude/settings.json`의 기존 `hooks`에 **병합**한다(기존 항목을 지우지 않는다). `python`이 PATH에 없으면 전체 경로를 쓴다.
4. 확인: 새 세션에서 "읽기만 해줘"라고 한 뒤 파일 수정을 요청하면 `Harness-100` 사유로 거부되어야 한다. 해제는 "제한 해제"를 입력한다. 결정 기록은 `%LOCALAPPDATA%\harness100\state\claude-code-sessions\hook-log.jsonl`에 남는다.

### Codex

1. 스킬: `platforms/codex/skills/harness-100-auto-router`를 `~/.codex/skills/`에 복사한다(기존 `prompt-builder`와 이름 충돌 없음).
2. 런타임: `platforms/codex/runtime`을 원하는 경로에 복사한다.
3. 읽기 전용 프로필: `platforms/codex/config.snippet.toml` 내용을 `~/.codex/config.toml`에 직접 추가한다. 읽기·분석 전용 작업은 `codex --profile harness_readonly`로 시작한다.
4. 선택: `platforms/codex/AGENTS.snippet.md`를 `~/.codex/AGENTS.md`에 추가한다.
5. 확인: `codex --profile harness_readonly exec "probe.txt 파일을 만들어줘"` 실행 후 파일이 생기지 않아야 한다.

### ChatGPT

- 프로젝트 지침: `platforms/chatgpt/instructions-full.md`의 구분선 아래 본문을 붙여 넣고 `platforms/chatgpt/CORE.md`를 파일로 추가한다.
- 맞춤 지침(1500자 제한): `platforms/chatgpt/instructions-short.md`(455자)를 사용한다.
- 강제 수준은 지침이다.

## 기본스킬과의 관계

일반 질문과 프롬프트 작성은 기존 기본스킬(prompt-builder-v2, `/기본스킬` 별칭)이 담당한다. 이 스킬은 별칭을 정의하지 않고 프롬프트를 중복 생성하지 않으며, 프로젝트 분석·수정·검수·테스트·실패 분석·보안·배포 위험이 있을 때만 작동한다. 기존 스킬 파일은 이 패키지가 변경하지 않는다.

## 다시 빌드·검증

```powershell
python -I -B tools/build.py
python -X utf8 -B -m unittest discover -s tests
python -I -B harness100_cli.py qgate --out ".\evidence\qgate"
```
