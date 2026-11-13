# Harness-100 v3.1-CC 설치 (Claude Code 전용)

실행 요건: **Python 3.12 이상 권장, 3.10 호환 목표.** 3.10·3.11용 대체 경로는 코드에 들어 있지만 실행 검증은 하지 않았습니다(필수 요건 아님, 제3자 확인 예정). 표준 라이브러리만 사용하며 설치할 의존성은 없습니다.

## 동작 요약

- allow는 사용자가 쓴 grant 줄과 정확히 일치할 때만 나옵니다. 형식: `승인: 수정 <glob> · 실행 <명령 접두>`, 자세한 내용은 [GRANT-SPEC.md](GRANT-SPEC.md).
- 사용자 제한("읽기만", "수정하지 마", "프롬프트만" …)에 걸리면 deny합니다.
- 그 밖에는 defer해서 Claude Code 자체의 확인 창과 권한 규칙에 맡깁니다.
- 확인 창이 없는 모드(auto·dontAsk·bypassPermissions, acceptEdits의 편집)에서는 grant 밖 변경·실행을 deny합니다.
- 읽기 도구, 읽기 전용 Bash, Skill은 막지 않습니다.

## A. 프로젝트 단위 설치 (권장)

1. `platforms/claude-code/runtime` 폴더를 원하는 위치에 복사합니다. 예: `C:\tools\harness100-runtime`
2. 대상 프로젝트의 `.claude/settings.json`에 `platforms/claude-code/settings.snippet.json`의 `hooks` 항목을 병합합니다. `<RUNTIME 전체 경로>`는 1의 경로로 바꿉니다. 기존 `hooks` 항목은 지우지 않습니다.
3. 확인:
   - 새 세션에서 "읽기만 해줘. Bash로 echo hi > probe.txt 실행해봐" → `Harness-100` 사유로 거부되고 파일이 생기지 않아야 합니다.
   - `승인: 수정 probe.txt` 줄과 함께 생성을 요청 → 확인 창 없이 생성돼야 합니다.

| 위험 | 내용 |
| --- | --- |
| 범위 | 그 프로젝트의 세션에만 적용됩니다. 다른 폴더에서 연 세션은 보호되지 않습니다. |
| 저장소 공유 | `.claude/settings.json`을 커밋하면 협업자에게도 hook이 실행됩니다. 런타임 경로가 개인 PC 경로이므로 보통 `.claude/settings.local.json`에 둡니다. |
| 런타임 위치 | 런타임 폴더를 프로젝트 안에 두면, 그 프로젝트에서 실행되는 코드가 hook 파일을 바꿀 수 있습니다. hook 상태·파일 변경은 hook이 deny하지만, 런타임은 프로젝트 밖에 두는 것이 안전합니다. |
| 실패 시 | hook 내부 오류는 종료 코드 2로 도구 호출을 막습니다(fail closed). Python 경로가 틀리면 모든 도구가 막힐 수 있습니다. |

## B. 전역 설치 (`~/.claude/settings.json`)

같은 `hooks` 항목을 사용자 설정에 병합합니다. 직접 하셔야 하며, 이 패키지는 사용자 설정을 자동으로 바꾸지 않습니다.

| 위험 | 내용 |
| --- | --- |
| 영향 범위 | 모든 프로젝트·모든 세션에 적용됩니다. 확인 창이 없는 모드(auto·dontAsk·bypassPermissions)에서는 grant 없는 변경·실행이 전부 deny되므로, 그 모드로 쓰던 자동화 작업이 멈출 수 있습니다. |
| 다른 hook과의 관계 | 다른 PreToolUse hook과 함께 실행됩니다. 어느 하나가 deny하면 막힙니다. allow는 이 hook의 grant 일치에서만 나옵니다. |
| 성능 | 도구 호출마다 Python 프로세스가 1번 실행됩니다(수십~수백 ms). |
| 상태 파일 | 세션별 제한·grant가 `%LOCALAPPDATA%/harness100/state/claude-code-sessions`에 저장됩니다. 이 폴더를 지우면 그 세션의 제한·grant가 사라집니다(재검증 ledger와 별개). |
| 제거 | `hooks` 항목을 지우면 즉시 해제됩니다. |

## 알려진 한계

- 제한 인식은 규칙 기반이라, 목록 밖 표현("off limits", "no commands" 등)은 deny 대신 defer가 됩니다. allow로 넓어지지는 않습니다.
- grant 줄 판정은 형식 기반입니다. 표시(코드 블록, `>`, 따옴표, "요약해줘:" 뒤의 자료) 없이 붙여 넣은 글 속에 정확한 grant 줄이 있으면, 사용자의 줄로 취급됩니다. grant가 든 글은 표시를 붙여 붙여 넣으십시오.
- Claude 채팅·Codex·ChatGPT 어댑터는 이번 버전의 범위가 아닙니다(빌드는 되지만 검증하지 않음).
