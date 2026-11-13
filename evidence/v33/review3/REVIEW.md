# v3.3 round 2 재검수 (review3) — 부분 독립 블랙박스

## 신원과 한계
- 부분 독립: 읽은 것은 `docs\GRANT-SPEC.md`, `platforms\claude-code\settings.snippet.json`뿐. hook은 `python -I -B hooks\claude_code_hook.py` 블랙박스 실행만 했다. 코드·테스트·이전 세트·이전 리뷰는 보지 않았다. 판정은 명세(v3.3 > v3.2 > v3.1)에 근거한다.
- 항목마다 새 상태 폴더를 썼다. 작업 폴더 `...\Temp\h100-v33-review3\`, 프로젝트 `...\proj`(그 안에 정션 `junc` 하나를 만들었다).
- 한계: 실제 도구는 실행되지 않으므로 파일 시스템 효과는 검증하지 못했다. 정션 외 심볼릭 링크 파일은 만들지 못했다. A279·A280은 러너의 상태 조작이 불완전해서 `statexp.py`로 다시 했고 결과를 A364·A365로 붙였다.

## 세트 M
- SHA-256 (실행 전 저장, `setM.sha256`): `c0eef0a72462b6a75690c9c0b22c1f0626206b01d3ce695759252735779c9726`
- 200 항목: path_fields 40, control_chars 30, first_line_grant 45, decided_rules 45, exact_command 40.
- probes 207 (도구 호출), matched 199, 일치율 96.1%. 항목 단위로는 192/200.
- 기대 allow(양성 대조) 41개 모두 allow. 실제 형식의 Edit(old/new/replace_all), MultiEdit, NotebookEdit(new_source, cell_id, cell_type, edit_mode), Bash(description/timeout/run_in_background), PowerShell을 썼고 과차단은 없었다.
- exit 2: 0. 가장 느린 결정 0.78초(프로세스 시작 포함). 2초 초과 없음.

### 불일치 8건 (모두 allow가 아닌 쪽, G1 아님)
| id | 기대 | 결과 | 판단 |
|---|---|---|---|
| FI027 | defer | deny | 첫 줄 `아래 내용을 봐줘:`의 "봐줘"가 읽기 전용 제한으로 인식돼 Bash를 deny. 더 좁은 쪽이지만 일상 문구 과차단 가능성. |
| FI038 | defer | deny | grant를 다른 cwd에서 보낸 뒤 P에서 실행. 명세는 defer인데 hook은 deny. |
| EX026, EX027, EX028 | defer | deny | 세션 ID `S1`, `s1 `, `other`는 기록이 없다. 명세 3절은 기록 없음 = deny라서 hook이 맞고 내 기대가 틀림. |
| EX036, EX037 | defer | deny | 같은 이유(`a_b`, `sess`는 기록 없음). |
| DE035 | not_allow | allow | permission_mode 키 없음 = default로 보고 grant 일치 allow. 명세(E6)상 맞고 내 기대가 틀림. |

### G1 (세트 M)
없음. allow인데 기대가 allow/any가 아닌 것은 DE035 하나이고, 유효한 정확 grant(`수정 src/**`, 파일이 그 안)가 덮으며 mode 키가 없으면 default라 명세와 일치한다. `any` 기대 중 allow였던 FI031(`작업 종료 해줘`는 단독 줄이 아님, grant 유지), FI034(`승인 취소 해줘`는 단독 줄이 아님), FI037(앞 공백은 trim), FI044(두 번째 grant 뒤에도 첫 grant 유지), EX025(cwd 끝 `\`는 같은 폴더)도 모두 정확 grant가 덮는다.

### reconfirm / rejection
- 정의: UserPromptSubmit 응답에 grant 인정 문구(`승인 범위(재확인 없이 진행)`)가 있으면 reconfirm, grant로 인정되지 않아 빈 응답이거나 `작업 범위` 문구만 나오면 rejection으로 셌다.
- 세트 M: reconfirm 171, rejection 34 (빈 6 + 작업 범위 28).
- 공격: reconfirm 315, rejection 80 (빈 51 + 작업 범위 29).

## 공격 (블랙박스)
- 공격 수 365 (`attacks.jsonl` 363 + 상태 조작 A364·A365). 기법: 경로 정규화·보호 경로·UNC·ADS·8.3·정션, glob 형식·ReDoS, 정확 일치 우회(유니코드 공백·제어·따옴표·셸 문자), git 옵션 변형, 모드 변형·타입 변형, 도구 이름 변형, 입력 모양(중복 키·비문자열), 이벤트·세션 변형, cwd 변형, grant 메시지 위장(줄바꿈 변종 U+2028/VT/NEL/CR 숨은 grant, 코드 블록, 인용, 취소·종료·제한), 상태 파일 복사·교환·손상·삭제.
- exit 2: 9건(A259~A262, A264~A268). 모두 깨진·빈·잘못된 이벤트 이름 입력이고 stderr에 fail-closed 메시지.
- 2초 넘은 결정: 없음(최대 0.23초). ReDoS 계열(A349·A350)도 빠름.
- 기대와 달라 non-allow가 아닌 불일치(deny 기대에 defer 등): 없음.

### 공격 중 allow (전부)
**정확 grant가 덮는다고 판단 (covered)**
- A056~A065 (`수정 src/**` 아래로 정규화되는 경로: `proj\..\proj\src\a.py`, 상대 `src\a.py`, `./src/a.py`, `SRC\A.PY`, `src\\a.py`, `src\.\a.py`, `src/a.py`, 소문자 경로, 끝 `\`, U+2215 포함 파일명). 모두 실제 위치가 src 안이다.
- A143 양성 대조. A149 `실행 rm -rf build`, A152 `실행 curl http://x`는 위험 명령을 grant에 그대로 적은 정확 일치.
- A173 `git --namespace=x status`, A182 `git --no-pager status`, A183 `git -p status`, A184 `GIT_DIR=x git status`: 명령 전체가 grant와 글자 그대로 같고 결정 1의 5개 옵션이 아님. 참고: A184는 환경변수로 `--git-dir`과 같은 효과를 내므로 명세 근거(저장소 변경)와는 어긋나는 구멍이지만 명세 문구상 정확 grant로 덮인다.
- A253 `{"command":"pytest -q","command ":"rm -rf x"}`, A254 `{"command":"pytest -q","Command":"rm x"}`: 실행되는 `command` 키 값이 grant와 같다.
- A256, A257 중복 키(JSON 뒤 값이 이긴다): 유효 값이 grant 안 경로·명령.
- A289, A290, A292, A293, A294 (`proj\..\proj`, `proj\.`, 대문자, `proj/`, 슬래시): 같은 폴더.
- A301, A302 grant 끝 `\r\n`·`\r`(앞뒤 줄바꿈은 제외 대상), A312 `기간 세션 · 기간 작업` 중복, A315·A318 첫 줄 grant + `수정하지 마`/`do not modify`(Bash 실행은 쓰기가 아님), A328·A330 제한 뒤의 새 grant와 `제한 해제`, A338, A339, A344(두 번째 grant가 첫 grant를 지우지 않음), A346 `수정 src/**, **`, A347 ` / ` 구분자.
- A349, A350 glob 형식이 유효하고 경로가 일치. A351, A352 `src/**` 안의 긴 경로. A356 기준선.

**정확 grant가 덮지 않음 (G1 위반, 명세 "애매하면 막는다" 기준)**
- A208: `permission_mode`가 JSON `null`(키는 있음)인데 `pytest -q`를 allow. E6은 "키가 아예 없을 때만 default"라고 하므로 null은 deny여야 한다. 다른 비문자열 값(1, 0, true, 목록, 객체)은 모두 non-allow였다.
- A284: PreToolUse에 `cwd` 키가 없는데 allow. grant는 (폴더, 명령) 일치가 필요한데 폴더를 확인하지 못했다.
- A285: `cwd`가 빈 문자열 `""`인데 allow. 같은 이유.
(A284·A285는 실제 Claude Code가 cwd를 항상 주므로 영향이 작고, 명세에 cwd 누락 규칙이 없어 판단이 갈릴 수 있다. A208도 영향은 작다. 그래도 "애매하면 막는다"에 맞지 않아 위반으로 적는다.)

### 막힌 것 중 확인된 점
- 보호 경로(`.claude`, `.git`, 대소문자·끝 점·공백 변형), 작업 폴더 밖, UNC, `\\?\`, ADS, `~`, `%VAR%`, 8.3, 드라이브 상대, 정션(`junc`, 정션 아래 경로) 전부 non-allow.
- `**` grant로 작업 폴더 자체, `src/**`로 `src` 자체 쓰기 deny. 숨은 줄 구분자(U+2028, VT, NEL, CR, FS)로 숨긴 `승인: 수정 **`은 인정되지 않음.
- plan 모드와 비정확 모드 문자열(`plan​`, 전각, 대소문자, 공백, 빈 문자열, 숫자·true·목록·객체) 쓰기·실행 deny 또는 non-allow.
- 세션 기록 없음·손상·잘림·삭제·복사(다른 세션 ID)·교환 모두 deny.
- 알 수 없는 도구 이름 변형(`write`, `Write `, `mcp__*` 등)과 비문자열 입력은 non-allow.

## 파일
- `setM.jsonl`, `setM.sha256`, `setM-results.jsonl`, `attacks.jsonl`, `attacks-results.jsonl`, `REVIEW.md` (모두 `evidence\v33\review3\`).
