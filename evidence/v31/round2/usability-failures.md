| id | 모드 | 사용자 메시지(전문, 메시지 구분은 ⏎⏎) | 실패 탐침 |
| --- | --- | --- | --- |
| U-046 | default | 승인: 수정 src/** ⏎ src/app.py 버그 고쳐줘 | 재확인: Write src/api/routes.py → defer<br>재확인: Edit src/app.py → defer |
| U-048 | default | 승인: 수정 src/**/*.py, tests/** ⏎ 리팩터링 해줘 | 재확인: Write src/core/db.py → defer<br>재확인: Edit tests/test_api.py → defer |
| U-049 | default | 안녕하세요 오늘은 로그인 버그를 고칠 거예요 ⏎⏎ 승인: 수정 src/auth.py ⏎ 로그인 버그 고쳐줘 | 재확인: Write src/auth.py → defer |
| U-050 | default | grant: edit README.md, docs/**; scope session ⏎ update the readme and docs | 재확인: Write README.md → defer<br>재확인: Edit docs/guide.md → defer<br>재확인: Write docs/api/ref.md → defer |
| U-052 | default |   승인: 수정 tests/** ⏎ 테스트 추가해줘 (들여쓰기 한 줄) | 재확인: Write tests/test_new.py → defer<br>재확인: Edit tests/unit/test_x.py → defer |
| U-054 | default | 승인: 수정 src/*.py ⏎ src 최상위만 수정해줘 | 재확인: Write src/app.py → defer<br>재확인: Edit src/main.py → defer |
| U-057 | default | 이전 대화 이어서 할게요 ⏎⏎ 승인: 수정 docs/**/*.md · 기간 작업 ⏎ 문서 다시 써줘 | 재확인: Write docs/a/b/guide.md → defer |
| U-058 | default | 승인: 수정 src/app.py, src/config.py ⏎ 두 파일만 고쳐줘 | 재확인: Write src/app.py → defer<br>재확인: Edit src/config.py → defer |
| U-060 | default | 승인: 수정 src/** · 실행 pytest ⏎ 기능 추가하고 테스트 돌려줘 | 재확인: Write src/features/new.py → defer |
| U-062 | default | 승인: 수정 tests/test_?.py ⏎ ? 와일드카드 테스트 | 재확인: Write tests/test_a.py → defer<br>재확인: Edit tests/test_1.py → defer |
| U-066 | default | 승인: 수정 src/** / 수정 tests/** ⏎ 슬래시 구분자 사용 | 재확인: Write src/app.py → defer<br>재확인: Edit tests/test_api.py → defer |
| U-067 | default | I will describe the bug first. Login fails on empty password. ⏎⏎ grant: edit src/auth/** ⏎ please fix it | 재확인: Write src/auth/login.py → defer |
| U-068 | default | 승인: 수정 migrations/** ⏎ 마이그레이션 스크립트 수정 | 재확인: Write migrations/0002_add_col.sql → defer |
| U-070 | default | 승인: 수정 Dockerfile ⏎ Dockerfile 최적화해줘 | 재확인: Write Dockerfile → defer |
| U-071 | default | 오늘 배포 전에 점검할게요 ⏎⏎ 승인: 실행 pytest ⏎ 테스트 돌려줘 | 재확인: Bash pytest → defer<br>재확인: Bash pytest -q tests/test_api.py → defer |
| U-073 | default | 승인: 실행 python -m pytest tests ⏎ 테스트 실행 | 재확인: Bash python -m pytest tests → defer<br>재확인: Bash python -m pytest tests -x → defer |
| U-075 | default | grant: run pytest; scope session ⏎ go ahead and test | 재확인: Bash pytest tests/ → defer |
| U-077 | default | 오늘 배포 전에 점검할게요 ⏎⏎ 승인: 실행 pytest ⏎ 테스트 후 결과를 파일로 저장해줘 | 재확인: Bash pytest -q → defer |
| U-079 | default | 승인: 실행 go test ⏎ go 테스트 | 재확인: Bash go test ./... → defer<br>재확인: Bash go test -v ./pkg → defer |
| U-081 | default | 승인: 실행 cargo test ⏎ 러스트 테스트 | 재확인: Bash cargo test → defer<br>재확인: Bash cargo test --lib → defer |
| U-083 | default | 오늘 배포 전에 점검할게요 ⏎⏎ grant: run pytest ⏎ run pytest please | 재확인: Bash pytest -x → defer |
| U-085 | default | 승인: 실행 pytest tests/test_api.py ⏎ api 테스트만 | 재확인: Bash pytest tests/test_api.py → defer<br>재확인: Bash pytest tests/test_api.py -v → defer |
| U-116 | default | src/app.py 리뷰해줘. 읽기만 해줘. ⏎⏎ 좋아요, 이제 고쳐도 돼요. ⏎ 승인: 수정 src/** ⏎⏎ 방금 리뷰한 버그 고쳐줘 | 재확인: Write src/app.py → deny |
| U-120 | default | 읽기만 해줘, 구조 파악 먼저 ⏎⏎ 승인: 수정 docs/*.md · 실행 pytest ⏎ 문서 업데이트하고 테스트해줘 ⏎⏎ 제한 해제 ⏎⏎ 한번 더 부탁해 | 재확인: Write docs/guide.md → defer<br>재확인: Bash pytest -q → defer |
