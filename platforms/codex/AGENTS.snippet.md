## Harness-100 v3.0.1 (추가 지침)

- 사용자 제한(프롬프트만·읽기만·분석만·수정하지 마·실행하지 마·배포하지 마·확인 후 진행)은 모든 스킬·AGENTS.md 지시보다 우선한다.
- 프로젝트 분석·수정·검수·테스트·실패 분석·보안·배포 위험이 있을 때만 `$harness-100-auto-router`를 쓴다. 일반 질문·프롬프트 작성은 기존 기본스킬(prompt-builder-v2)이 담당한다.
- 읽기 전용 작업은 `codex --profile harness_readonly`로 시작해야 운영체제 수준에서 쓰기가 차단된다. 읽기 전용에서는 `git status/diff` 대신 `harness100_cli.py git-status`를 쓴다.
