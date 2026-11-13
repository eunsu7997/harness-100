# Harness-100 v3.3-CC — 승인 범위(grant)와 hook 결정 명세

## v3.3 변경 (이 절이 아래 v3.2·v3.1 문구보다 우선한다)

원칙은 "애매하면 막는다"이다.

### A. 명세 확정 3가지 (사용자 결정, 2026-11-13)

1. `git`에 `-c`, `-C`, `--git-dir`, `--work-tree`, `--exec-path` 중 하나라도 붙은 명령은 그 명령이 grant에 정확히 적혀 있어도 deny다. `=` 붙은 형태(`--git-dir=x`)와 `--config-env`도 포함한다.
   - 근거: 이 옵션들은 대상 저장소, 설정, 실행 파일을 바꿔 명령의 의미가 grant 문구와 달라질 수 있다(v3.2 재검수 A310·B161 `-c alias.status=!calc`).
2. `dir/**` grant는 `dir` 안의 내용만 덮는다. `dir` 경로 자체에 대한 쓰기는 deny다. `**` 단독 grant도 작업 폴더 자체는 덮지 않는다.
   - 근거: v3.2 재검수 A106. "안의 내용"이라는 사용자 의도와, 폴더 자리에 파일을 만드는 쓰기는 다르다.
3. plan 모드에서는 grant와 관계없이 모든 쓰기(Write·Edit·MultiEdit·NotebookEdit)와 모든 실행(Bash·PowerShell, 읽기 전용 명령 포함)을 deny한다. 읽기 도구(Read·Glob·Grep)와 Skill은 그대로다.
   - 근거: v3.2의 표("plan / grant 일치 = allow")와 v3.1 문구("plan 모드 쓰기 deny")가 충돌했다(G-056·P46·P48). 계획 단계에서 실행하지 않는다는 쪽으로 확정한다.

### B. 도구 입력의 경로 필드

- 도구별 경로 필드는 다음과 같다.
  - Write, Edit, MultiEdit: `file_path`
  - NotebookEdit: `notebook_path`
- 위 도구의 입력에 경로를 담을 수 있는 다른 필드가 있으면 deny다. 대상: `file_path`, `notebook_path`, `path`, `paths`, `filepath`, `filename`, `file`, `target`, `target_file`, `destination`, `dest`, `output`, `new_path`, `old_path`.
  - 예: NotebookEdit에 `file_path`가 함께 오거나, Write에 `path`가 함께 오는 경우.
  - 판정 대상이 둘 이상이 되는 구성은 "알 수 없는 경로 필드 구성"으로 보고 deny한다.
- 알 수 없는 도구(아래 목록 밖, `mcp__*` 포함)는 deny다. 알려진 도구:
  - 읽기: Read, Glob, Grep, LS, NotebookRead
  - 쓰기: Write, Edit, MultiEdit, NotebookEdit
  - 실행: Bash, PowerShell
  - 메타: Skill, TodoWrite, AskUserQuestion, ToolSearch
  - 네트워크: WebFetch, WebSearch
  - 위임: Agent, Task

### C. 제어 문자

쓰기 도구의 경로 필드와 실행 도구의 `command`에 다음 문자가 하나라도 있으면 deny다. 공백으로 바꾸거나 지우지 않는다.
- C0 제어 문자(U+0000~U+001F, 탭·CR·LF 포함, 끝에 붙은 줄바꿈 포함)
- DEL(U+007F)
- C1 제어 문자(U+0080~U+009F)
- 서식 문자(유니코드 범주 Cf, 예: U+200B, U+FEFF)

### D. 첫 줄 grant (사용성)

메시지의 **첫 줄**이 정확한 grant 줄이고 아래 조건을 모두 만족하면 그 줄을 grant로 인정하고, 둘째 줄부터를 요청으로 처리한다.
- 첫 줄 자체가 규칙 B의 문자 조건을 지킨다. 대문자·전각·탭·NBSP·서식 문자·두 칸 공백이 없어야 한다.
- 둘째 줄부터의 요청 부분이 짧고 단순하다. 5줄 이하, 400자 이하이고, 다음 중 어느 것도 없어야 한다.
  - `>`로 시작하는 줄, 코드 블록(``` 또는 ~~~)
  - 다른 grant 모양 줄(`승인:`·`grant:`가 줄 어디에든)
  - 붙여넣기 서두로 끝나는 줄(`:`·`：`로 끝나는 줄)
  - 메일·로그 머리(`From:`, `To:`, `Subject:`, `Date:`, `-----`, `[INFO]`, `[ERROR]`, 날짜·시각으로 시작하는 줄)
  - 빈 줄
- 위 조건 중 하나라도 어기면 그 메시지 전체는 grant가 아니다. 이 경우 규칙 B(메시지 전체가 grant 줄 하나)만 적용된다.
- 첫 줄이 grant가 아니면(붙여넣기 서두가 첫 줄인 경우 포함) 메시지 안의 어떤 grant 줄도 인정하지 않는다.

### E. 재검증 1회차 명확화 (round 0 결과 반영, 모두 좁히는 방향)

위 A~D를 그대로 적용하며 모호했던 부분만 "애매하면 막는다"로 정한다.
1. (결정 1) 붙여 쓴 형태도 해당한다: `-c<값>`(`-ccore.x=y`), `-C<경로>`(`-C.`, `-C/`). 명령의 어느 단어가 `git`(또는 `git.exe`, 대소문자 무시)이면 그 뒤 위치 어디에 있어도 deny다.
2. (결정 2) `dir/**` grant가 있을 때 `dir` 경로 자체에 쓰는 것은 확인 창이 있는 모드에서도 deny다. 끝이 `/`이거나 `//`가 든 glob(`src/**/`)은 형식 오류로 보고 그 수정 절 전체를 버린다.
3. (결정 3) `permission_mode`가 정확한 소문자 값(`default`, `manual`, `plan`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`)이 아니면(`Plan`, `PLAN`, `plan `, 줄바꿈·서식 문자 포함) grant와 관계없이 모든 쓰기·실행을 deny한다. 값이 없으면 종전처럼 `default`로 본다.
4. (v3.2 2절 "정확 일치") 실행 grant와 명령은 **원문 그대로** ASCII 공백으로만 나눠 비교한다. 따옴표·백슬래시를 풀지 않는다. `"pytest" -q`, `pytest '-q'`, `p\ytest -q`는 `실행 pytest -q`와 다르다. grant 줄의 `python tests\run.py`도 글자 그대로 비교한다.
5. (D) 첫 줄 grant 뒤 요청 부분에 `승인 취소`·`작업 종료` 줄이 있으면 그 메시지는 grant가 아니다(취소·종료만 적용).

재검증 2회차 명확화 (round 1 결과 반영, 모두 좁히는 방향):
6. (E3) `permission_mode`가 빈 문자열 `""`이면 값이 있으나 정확한 값이 아니므로 쓰기·실행 deny다. 키가 아예 없을 때만 `default`다.
7. (B) 경로 필드 이름은 대소문자·`_`·`-`·공백을 무시하고 비교한다(`FILE_PATH`, `filePath`, `file_path `, `working_directory`). B의 목록에 `out`, `dir`, `directory`, `folder`, `cwd`, `workdir`, `working_directory`, `src`, `source`, `to`, `from`, `uri`, `url`, `notebook`, `location`, `root`를 더한다. 쓰기 도구는 최상위의 자기 경로 필드 하나만 허용하고, 중첩 객체(MultiEdit `edits` 등) 안의 경로 필드도 deny다. 실행 도구(Bash·PowerShell)의 입력에 이런 필드가 하나라도 있으면 deny다.
8. (E4) grant나 명령에 따옴표(`'` `"`)가 하나라도 있으면 공백 개수도 무시하지 않는다. 명령의 앞뒤 공백을 뺀 원문이 grant 원문과 글자 그대로 같아야 한다.

---

# (이하 v3.2-CC 명세)

## v3.2 변경 (이 절이 아래 v3.1 문구보다 우선한다)

v3.2는 자연어 해석을 넓히지 않는다. 승인 범위를 좁고 정확하게 만드는 것만 한다.

### 1. 보호 경로 (어떤 grant로도 쓰기 불가)

다음 경로에 쓰는 Write·Edit·MultiEdit·NotebookEdit는 grant가 있어도 deny다. `승인: 수정 **`, `승인: 수정 .claude/**`, `승인: 수정 .git/hooks/*`도 포함된다.
- 작업 폴더의 `.claude/`(하위 전체, 대소문자 무시)
- 작업 폴더의 `.git/`(하위 전체, 대소문자 무시)
- 하네스 런타임(hook·설정)과 hook 상태 폴더
- 작업 폴더 밖 전부(홈 폴더 포함)

경로는 실제 절대 경로로 해석한 뒤 작업 폴더 안인지 판정한다. 다음처럼 실제 위치가 달라질 수 있는 경로는 쓰기 판정에서 deny다.
- `~`, `~user`로 시작
- 환경 변수 `%VAR%`, `$VAR`, `${VAR}` 포함
- 드라이브 상대(`C:x.txt`)
- UNC(`\\server\share`, `//server/share`), `\\?\`, `\\.\`
- 8.3 짧은 이름(`PROGRA~1`처럼 `~숫자`가 있는 경로 성분)
- NTFS 스트림(`a.py::$DATA`, `a.py:stream`)
- NUL 문자
- 경로 중간이나 끝의 성분이 심볼릭 링크·정션인 경우

### 2. 실행 승인 = (작업 폴더, 전체 명령) 정확 일치

- `승인: 실행 pytest -q`는 그 grant를 보낸 메시지의 작업 폴더에서 정확히 `pytest -q`만 허용한다(토큰 단위 비교, 공백 개수 차이는 무시).
- 다음 경우는 그 grant로 실행할 수 없다. 이 경우 결정은 defer이고, 확인 창이 없는 모드에서는 deny다.
  - 다른 작업 폴더에서 실행하는 경우
  - 인자를 하나라도 더하거나 빼거나 바꾼 경우(`pytest -q -x`, `pytest`, `pytest -q --basetemp=/`)
- 접두어 일치는 없다. 인자를 다르게 쓰고 싶으면 사용자가 그 명령 전체를 grant 줄에 적는다. 한 grant 줄에 `실행` 절을 여러 개 둘 수 있다.
- 같은 세션 안에서는 같은 (폴더, 명령) 조합을 다시 묻지 않는다(grant가 세션 동안 유효).
- 셸 제어 문자(`;` `&` `|` `<` `>` `` ` `` `$(` 줄바꿈)가 있는 명령은 grant로 실행할 수 없다.

### 3. 세션 격리

- 상태 파일 이름은 세션 ID 원문(바이트)의 해시로 만든다. `x_y`와 `x/y`, `Sess`와 `sess`는 서로 다른 세션이다.
- 세션 기록은 그 세션의 첫 UserPromptSubmit에서 만든다. 다음 경우 쓰기·실행은 deny다.
  - PreToolUse 시점에 그 세션의 기록이 없는 경우
  - 기록이 손상된 경우
  - 기록 안의 세션 ID가 요청의 세션 ID와 다른 경우
- glob 매칭은 선형 시간 알고리즘으로 한다. hook 판정이 내부 제한 시간(2초)을 넘으면 deny다(fail closed).

### 4. gate와 hook 일치

CLI·API의 gate(`harness100.policy.gate`)도 사용자 승인(grant에 해당하는 Approval)이 정확히 일치할 때만 allow를 낸다. 승인이 없으면 approval_required 또는 deny다.

### 그대로 유지

- grant 줄 형식(규칙 B: 메시지 전체가 grant 줄 하나)
- 수정 grant의 glob 문법
- 제한은 deny로만 좁힌다
- 권한 모드별 규칙
- 읽기·Skill은 deny하지 않는다

---

# (이하 v3.1-CC 명세)

## 원칙

- 라우터와 문장 해석은 "무엇을 할지"만 정한다. "무엇을 해도 되는지"는 Claude Code 권한 설정과 사용자가 명시한 grant가 정한다.
- hook의 결정은 세 가지다.
  - `allow`: grant와 정확히 일치할 때만. Claude Code가 다시 묻지 않는다.
  - `deny`: 사용자 제한("읽기만", "수정하지 마", "프롬프트만"…)이나 위험 규칙에 걸릴 때.
  - `defer`(결정 없음): 그 밖의 모든 경우. Claude Code의 권한 흐름(확인 창, 권한 규칙)에 맡긴다.
- 문장 해석으로는 `allow`를 만들 수 없다. 인식에 실패해도 권한이 넓어지지 않는다.

## grant 형식 (정확히 이 형식만 인정)

> **재검증 2회차 변경(사용자 결정, 2026-11-13).** 이 변경은 사용성 세트·세트 D 작성 뒤에 이뤄졌다.
> - 규칙 B: 사용자 **메시지 전체**(앞뒤 ASCII 공백·줄바꿈 제외)가 grant 줄 **하나**일 때만 grant다. 요청 문장과 같은 메시지에 있는 grant 줄은 인정하지 않는다. 인용·코드 블록·붙여 넣은 글 안의 grant 줄도 인정하지 않는다. grant는 별도 메시지로 먼저 보낸다.
> - 규칙 B: 머리말은 소문자 `승인: ` 또는 `grant: `(콜론 뒤 ASCII 공백 한 칸)다. 대문자, 전각 문자, NBSP 같은 특수 공백, 탭, 서식 문자(U+200B 등)가 하나라도 있으면 거부한다. 공백이 두 칸이어도 거부한다. 구분자는 ` · `, `; `, ` / `만 인정한다.
> - 규칙 B: glob은 200자 이하, `*`는 12개 이하이고 `***`는 쓸 수 없다. grant는 그것을 보낸 시점의 작업 폴더에 묶인다. 세션이 다른 폴더로 옮기면 그 grant는 적용되지 않는다. 파일 경로의 NTFS 스트림(`a.py::$DATA`)과 NUL 문자는 일치하지 않는다.
> - 규칙 A: 위험 행동(push·배포·삭제·네트워크·설치·commit)은 grant 접두가 그 행동을 명시할 때만 allow한다. 판정은 git 전역 옵션을 걷어 낸 명령으로 하고, `python -m pip`는 `pip`로 본다. 걷어 낼 옵션(`-C`, `--git-dir`, `-c` 등)이 있었던 위험 명령과 `git -c`가 있는 명령은 allow하지 않는다.
> - plan 모드의 쓰기와, 모드와 관계없이 작업 폴더 밖 경로에 쓰는 것은 deny한다.
>
> 아래 원래 문구 중 "한 줄", "앞쪽 공백 허용", "구분자 `·` `;` `/`" 부분은 위 규칙이 우선한다.

(원래 문구) 사용자 프롬프트의 **한 줄 전체**가 아래 형식이어야 한다. 줄 맨 앞(앞쪽 공백 허용)에서 시작해야 하며, 다음 경우는 grant가 아니다.
- 코드 블록(```) 안의 줄
- `>`로 시작하는 인용 줄
- 따옴표 안의 문장
- 문장 중간에 나온 "승인:"

```
승인: <절> [· <절>]... [· 기간 세션|작업]
grant: <clause> [; <clause>]... [; scope session|task]
```

절(clause):

| 한국어 | 영어 | 허용되는 도구 호출 |
| --- | --- | --- |
| `수정 <glob>[, <glob>...]` | `edit <glob>[, <glob>...]` | Write·Edit·MultiEdit·NotebookEdit 중 대상 파일이 glob에 맞는 것(새 파일 생성 포함) |
| `실행 <명령 접두>` | `run <command prefix>` | Bash·PowerShell 명령 중 토큰이 접두와 정확히 일치하며 시작하는 것. 단 명령에 셸 제어 문자(`;` `&&` `\|\|` `\|` `>` `<` `` ` `` `$(` `&` 줄바꿈)가 있으면 allow하지 않음 |

구분자는 `·`, `;`, `/` 중 하나다. 절 하나에 여러 glob을 쉼표로 나열할 수 있다.

명확화 (v3.1-cc 구현, 세트 작성 뒤 추가):
- `/`는 앞뒤에 공백이 있을 때만 구분자다. `src/**`의 `/`는 경로 문자다.
- 머리말 언어가 절의 언어를 정한다. `승인:`에는 `수정·실행·기간`(세션·작업)을 쓰고, `grant:`에는 `edit·run·scope`(session·task)를 쓴다. 섞으면 grant가 아니다.
- 명령 접두는 토큰 단위로 정확히 일치해야 한다. `실행 python -m pytest tests`는 `python -m pytest tests -q`를 덮지만 `python -m pytest tests/unit`은 덮지 않는다.
- glob 문자는 경로 문자(영숫자·한글·`. - _ / @ + =`)와 `* ?`만 허용한다.
- 위험 명령(push·배포·삭제·설치·네트워크·commit)은 접두 자체가 그 명령이어야 한다. `실행 git`은 `git status`를 덮지만 `git push`는 덮지 않는다. `실행 git push`는 `git push origin main`을 덮는다.

- glob은 프로젝트 루트(세션 작업 폴더) 기준 상대 경로다. `*`(한 단계), `**`(여러 단계), `?`를 쓸 수 있다. 다음 glob은 무효이며, 그 절은 버린다.
  - 절대 경로
  - 드라이브 문자
  - `..`
  - `~`
  - 프로젝트 밖을 가리키는 경로
- 명령 접두는 1개 이상의 토큰이다(예: `실행 pytest`, `실행 npm test`, `실행 python -m pytest tests`).
- 기간: 기본값은 `세션`(그 Claude Code 세션 동안)이다. `작업`이면 사용자가 `작업 종료`를 단독 줄로 보낼 때까지 유효하다.
- 취소: `승인 취소`(또는 `grant revoke`)를 단독 줄로 보내면 모든 grant를 지운다.
- 형식이 하나라도 틀린 줄은 grant가 아니다. 이 경우 Claude Code 권한 흐름에 맡긴다. 예:
  - "응 다 해도 돼", "승인했음", "approved, go ahead"
  - "승인: 전부", "승인: 알아서"
  - 접두가 없는 "승인: 실행"

예:
```
승인: 수정 src/**/*.py, tests/** · 실행 pytest
grant: edit docs/*.md; run npm test
승인: 실행 python -m pytest tests · 기간 작업
```

## 제한과 grant의 관계

- 제한은 deny로 좁히기만 한다. 인식된 제한은 그 세션에서 유지된다.
- grant 줄이 있는 메시지는 사용자의 새로운 명시적 결정이다. 그 이전 메시지의 제한 가운데 grant 범위와 겹치는 부분을 해제한다. 같은 메시지나 이후 메시지에 나온 제한은 다시 적용된다.
- 이후 메시지에 "읽기만 해줘" 같은 제한이 나오면, 그 제한이 grant보다 우선해 deny한다. 다시 쓰려면 grant 줄을 새로 보낸다.
- `제한 해제`를 단독 줄로 보내면 제한만 지운다. grant는 그대로 둔다.

## 권한 모드별 동작 (hook 입력 `permission_mode`)

| 모드 | grant 일치 | grant 밖 쓰기·실행 | 읽기·Skill |
| --- | --- | --- | --- |
| `default`, `manual` | allow | defer(Claude Code가 확인 창) / 제한에 걸리면 deny | defer |
| `plan` | allow | 쓰기: **deny**(계획 파일 포함, 재검증 2회차). 실행: defer / deny | defer |
| `acceptEdits` | allow | 쓰기: **deny**(확인 창이 뜨지 않으므로). 실행: defer / deny | defer |
| `auto`, `dontAsk`, `bypassPermissions` | allow | **deny** | defer |

- 읽기 도구(Read, Glob, Grep)와 Skill 도구, 스킬 폴더 파일 읽기는 부작용이 없으므로 제한 중에도 deny하지 않는다.
- 위험 명령(push·배포·삭제·설치·네트워크)은 grant 접두에 그 명령이 명시돼야 allow된다. 그 밖에는 defer(확인 창) 또는 deny(확인 창 없는 모드)다.
