"""Extract user restrictions with general rules (v3.0.2).

Design (no sentence lists):
1. normalize: NFKC, drop Unicode Cf (zero-width, soft hyphen, bidi marks), casefold, unify whitespace.
2. split instruction vs data: quoted text, code fences, and anything after ':', newline or '>' that follows a
   review/analyze/summarize/translate/explain verb is data. Data never adds actions (it can only add restrictions).
3. restrictions are read from the whole text (narrowing is always safe); positive actions only from the
   instruction text with negated scopes blanked out.
4. negation scope: Korean negation tokens (마/말고/않/금지/안 돼/없이 ...) cover the preceding words back to the
   last clause connective; English prefix markers (don't/never/no/without/avoid ...) cover the following words,
   postfix markers (untouched/unchanged/nothing/alone/as is) the preceding words, within the clause.
5. a negated scope with an action word forbids that capability; with only an object word (files, code) it
   forbids all modification; with nothing recognisable it becomes "confirm_first" (approval for everything).
6. approval language (승인/허락/OK/confirm + 전에/후에/하면 그때/before/until/first) -> confirm_first; negations
   inside such a clause mean "not before approval", i.e. confirm_first rather than a permanent ban.
"""

import re
import unicodedata

CONSTRAINTS = ("prompt_only", "read_only", "analyze_only", "no_modify", "no_create", "no_execute", "no_deploy",
               "no_delete", "no_install", "no_network", "no_commit", "confirm_first")
CAP_TO_CONSTRAINT = {"write": "no_modify", "create": "no_create", "execute": "no_execute", "deploy": "no_deploy",
                     "delete": "no_delete", "install": "no_install", "network": "no_network", "commit": "no_commit"}
MUTATING = {"write", "execute", "deploy", "delete", "install", "network", "commit"}

# ---- lexicon: (capability, Korean stems matched on space-free text, English regex on spaced text) ----
LEX = {
    "write": (r"수정|변경|바꾸|바꿔|바꿀|바뀌|편집|고치|고쳐|고칠|고침|고처|쓰기|쓰지|써|작성|만들|만드|생성|추가|덮어|리팩|"
              r"구현|개발|손보|손봐|업데이트|갱신|패치|적용|반영|저장|옮기|옮겨|이동|정리|이름바|리네임|올리|올려|내려|켜|꺼|활성|비활성",
              r"\b(?:modif\w*|chang\w*|edit\w*|writ\w*|creat\w*|add\w*|fix\w*|refactor\w*|renam\w*|updat\w*|patch\w*|"
              r"implement\w*|build\w*|alter\w*|rewrit\w*|overwrit\w*|sav(?:e|ing)|mov(?:e|ing)|apply\w*|code changes?|"
              r"enabl\w*|disabl\w*|toggl\w*|bump\w*|turn\s+(?:on|off))\b"),
    "execute": (r"실행|돌리|돌려|돌릴|구동|빌드|컴파일|띄우|띄워|테스트돌|작동시",
                r"\b(?:run|runs|running|execut\w*|exec|compil\w*|launch\w*|build\w*|tests?|testing|pytest|npm test)\b"),
    "deploy": (r"배포|푸시|릴리스|릴리즈|게시|출시|올리|올려|올릴",
               r"\b(?:deploy\w*|push\w*|publish\w*|releas\w*|ship\w*|go live)\b"),
    "delete": (r"삭제|지우|지워|지울|제거|날리|날려|드롭",
               r"\b(?:delet\w*|remov\w*|rm|drop\w*|wip\w*|eras\w*|purg\w*)\b"),
    "install": (r"설치", r"\b(?:install\w*|pip|npm i)\b"),
    "network": (r"외부|네트워크|인터넷|전송|업로드|다운로드|보내|송신",
                r"\b(?:network\w*|internet|upload\w*|download\w*|send\w*|fetch\w*|external\w*|online|curl)\b"),
    "commit": (r"커밋", r"\bcommit\w*\b"),
}
BROAD_KO = r"아무것|아무거|아무\s*것|건드리|건드려|건들|손대|손을대|손댈|손\s*대"
BROAD_EN = r"\b(?:anything|everything|touch\w*|untouched|unchanged|hands\s*off|alone|as[- ]is|any changes?)\b"
OBJECT = r"파일|코드|소스|저장소|레포|리포|프로젝트|폴더|디비|db|데이터|\b(?:files?|code|source|repo\w*|project|folder|database|db|data)\b"
HARMLESS_NEG = r"걱정|신경|무리|서두르|서둘|겁먹|미안|헷갈|긴장|\bworr\w*|\brush\w*|\bpanic\w*|\bsorry\b|\bproblem\b|\bsure\b|\bdoubt\b"

# Any inflection of 말다 (마, 마라, 마요, 마세요, 마시고, 마십시오, 말고, 말아, 말것, 말자 ...) or 않다, or 금지/불가/없이.
KO_NEG_TOKEN = re.compile(r"^(?:마|마라|마요|마셈|마세|마세요|마시|마시고|마시오|마십|마십시오|마시죠|말|말고|말구|말아|말아줘|말아요|말아라|"
                          r"말것|말자|말길|금지|금지야|금지임|금지입니다|금지요|불가|안돼|안돼요|안됩니다|안되|안됨|안된다|"
                          r"않고|않게|않도록|않아도|않기|않을|않는|않으|하지마|하지말고|없이|x|×|❌|no|노노|"
                          r"필요없어|필요없음|필요없다|필요없습니다|필요없어요|안해도|안해도돼|안해도됨|안해도되)\W*$")
KO_NEG_GLUED = re.compile(r"(?:지마|지마세|지마시|지마십|지말|지않|하지마|금지|없이|안돼|안됨|안됩|못하게|"
                          r"필요없|필요가없|필요는없|안해도|안하셔도|않아도)[가-힣]{0,3}\W*$")
# Clause connectives end a Korean negation scope (… 고치되 / 해도 되는데 / 작성하지만 …).
CONNECTIVE = re.compile(r"(?:고|며|서|면|는데|지만|니까|므로|후|뒤|다음|하고|그리고|되|으나|면서|해도|어도|아도)[,]?$")
EN_PREFIX = re.compile(r"\b(?:don'?t|do\s+not|does\s+not|doesn'?t|never|no(?!-)|without|avoid|stop|refrain\s+from|must\s+not|mustn'?t|"
                       r"should\s+not|shouldn'?t|can'?t|cannot|won'?t|hands\s+off|not|forbid\w*|prohibit\w*|ban|bann\w*|"
                       r"disallow\w*|not\s+allowed\s+to|no\s+permission\s+to|under\s+no\s+circumstances|refuse\s+to)\b")
EN_POSTFIX = re.compile(r"\b(?:untouched|unchanged|nothing|alone|as[- ]is|none|intact|as\s+(?:they|it)\s+(?:are|is)|exactly\s+as|"
                        r"not\s+(?:needed|necessary|required)|unnecessary)\b")
# ---- structural helpers added in round 2 ----
# "Use" + a tool noun negated ("터미널은 쓰지 마", "don't use the shell") forbids that tool's capability, not writing.
TOOL_NOUN = {"execute": r"터미널|쉘|셸|콘솔|명령어|명령줄|커맨드|\b(?:terminal|shell|console|command[- ]?line|cli|cmd|bash|powershell)\b",
             "network": r"인터넷|브라우저|네트워크|\b(?:internet|browser|network|web)\b",
             "commit": r"깃|\bgit\b", "install": r"패키지\s*매니저|\b(?:npm|pip|package\s+manager)\b"}
USE_VERB = r"쓰|써|사용|이용|\b(?:use|using|open|access)\b"
# An apply-type verb aimed at a deploy target ("production 반영") is a deploy, not a file edit.
DEPLOY_TARGET = r"production|프로덕션|운영|라이브|실서버|본서버|\b(?:prod|live|main|master)\b"
APPLY_VERB = r"반영|적용|올리|올려|\b(?:apply\w*|push\w*|merg\w*)\b"
# Creation of new files only ("새 파일은 만들지 말고", "no file creation").
CREATE_ONLY = (r"(?:새|신규|새로운)\s*(?:파일|모듈|폴더)|파일\s*(?:을|은|를)?\s*(?:새로\s*)?(?:만들|생성|추가)|"
               r"\bnew\s+files?\b|\bfile\s+creation\b|\bcreat\w*\s+(?:any\s+|new\s+)?files?\b|\bcreate\s+new\b")
MODIFY_WORD = r"수정|고치|고쳐|편집|\b(?:edit\w*|modif\w*|chang\w*|fix\w*)\b"
# Words that make an object specific ("구현 코드", "the lockfile") vs. general ("코드", "files", "anything").
TOUCH_WORD = r"touch\w*|untouched|unchanged|intact|hands\s*off|as[- ]is|alone|건드|건들|손\s*대|손을|그대로"
GENERAL_OBJECT = (r"^(?:파일|코드|소스|저장소|레포|리포|프로젝트|폴더|아무것|아무거|아무|전부|모든|다|뭐|무엇|것|거|"
                  r"files?|code|source|repo\w*|project|folder|anything|everything|any|all|it|them|stuff)$")
FILLER = (r"^(?:the|a|an|my|our|your|this|that|these|those|please|just|leave|keep|don'?t|do|not|never|and|but|"
          r"is|are|be|to|of|in|on|at|of|이|그|저|좀|제발|절대|일단|지금은|일체|하나도)$")
# "X만 써줘": the head noun before 만 and a writing/asking verb right after it.
WRITE_REQ = r"^(?:써|쓰|작성|적어|적|만들어|정리해|뽑아|부탁|줘|주세요|필요|있으면|드려|해줘|남겨|보내줘)"
CODE_HEAD = (r"(?:코드|함수|테스트|스크립트|파일|클래스|모듈|메서드|컴포넌트|쿼리|설정|패치|마이그레이션|readme|changelog|"
             r"config|code|function|tests?|script|file|class|module|method|component|query|patch|migration|\.\w{1,4})$")
TEXT_FORM_EN = (r"\b(?:text|wording|writing|prose)[- ]only\b|\bonly\s+(?:as\s+|in\s+)?(?:text|words|writing|prose)\b|"
                r"\bin\s+(?:text|writing|words)\s+(?:form\s+)?only\b|\bas\s+(?:plain\s+)?text\b|"
                r"\b(?:just|only)\s+(?:write|draft|type|jot|put\s+together|give\s+me)\s+(?:up\s+|out\s+|down\s+)?"
                r"(?:a\s+|an\s+|the\s+|some\s+|my\s+)?(?!code\b|tests?\b|scripts?\b|functions?\b|the\s+code)\w+|"
                r"\b(?:just|only)\s+(?:need|want)\s+(?:a|an|the)\s+(?!code\b|tests?\b|scripts?\b|fix\b)\w+|"
                r"\ball\s+i\s+need\s+is\s+(?:a|an|the)\s+(?!code\b|tests?\b|scripts?\b|fix\b)\w+|"
                r"\bonly\s+(?:the\s+)?(?:text|description|doc\w*|outline|summary|plan|draft|message|notes?|spec\w*|ticket|"
                r"brief|proposal|write-?up|checklist|wording|copy)\b")
# Hand-off of the work to someone else (a recipient or another actor).
# Work handed to a recipient ("후임자에게 줄 거야", "hand it to our DBA"): marks a deliverable for someone else.
HANDOFF_TO = (r"(?:에게|한테|께)\s*(?:\S+\s*)?(?:줄|전달|넘길|넘겨|보낼|드릴|맡길|시킬|줘야|공유)|전달할|전달용|넘길|인수인계|"
              r"\b(?:hand|pass|give|send|forward)\w*\s+(?:it\s+|this\s+|them\s+)?(?:off\s+|over\s+|on\s+|along\s+)?to\b|"
              r"\bfor\s+(?:the|my|our|a)\s+\w+(?:\s+\w+)?\s+to\s+(?:implement|build|code|fix|work\s+on|use)")
# Work done by another actor or by the user later ("구현은 제가 따로 시킬게요", "the backend team will implement it").
HANDOFF_BY = (r"(?:내가|제가)\s*(?:따로|직접|나중에|알아서)\s*\S*\s*(?:할|시킬|맡길|진행|돌릴|구현)|"
              r"(?:팀|팀원|걔|걔네|그쪽|개발자|담당자|후임|후임자|동료|외주|업체|엔지니어|qa)(?:들)?(?:이|가|에서|쪽에서)\s*(?:\S+\s*){0,3}?"
              r"(?:할|해|돌려|돌릴|구현|개발|만들|처리|작업|진행|맡)|"
              r"\b(?:the|our|my|a|their)\s+(?:\w+\s+){0,2}(?:team|devs?|developers?|engineers?|contractors?|colleagues?|dba|qa|"
              r"intern|someone)\s+(?:will|is\s+going\s+to|can|should|are\s+going\s+to)\s+(?:\w+\s+)?"
              r"(?:implement|build|code|do|handle|run|fix|write|take)")
IMPLEMENT_EN = r"\b(?:implement\w*|build\w*|develop\w*|coding|to\s+code|write\s+(?:the\s+|any\s+)?code|code\s+changes?)\b"
IMPLEMENT_KO_TOKEN = re.compile(r"^(?:직접)?(?:구현|개발|코딩|만들|만드|짜)")
IMPLEMENT_KO_TOPIC = re.compile(r"(?:구현|개발|코딩|작업)(?:은|는|도|을|를|까지)?$")
# Conditional approval (English): an approval word within a few words of a timing/condition word.
APPROVAL_TOK = (r"approv\w*|ok|okay|go-?ahead|green\s*light|sign\s*-?\s*offs?|signs?\s+off|confirm\w*|say\s*-?\s*so|yes|"
                r"thumbs\s*up|permission|consent|blessing")
COND_TOK = r"after|until|till|before|once|unless|when|whenever|first"
UNTIL_THEN = r"\b(?:until|till)\s+then\b|\bbefore\s+that\b|\bin\s+the\s+meantime\b|그때까지|그\s*전까지|그전까지|그\s*전에는|그전에는"
# Trailing judgment question about the preceding text (paste followed by the user's real request).
JUDGE_NOUN = (r"피싱|스팸|사기|스캠|진짜|가짜|믿어도|믿을|신뢰|악성|의심|사회\s*공학|인젝션|social\s*engineering|phishing|spam|"
              r"scam|fraud|legit\w*|genuine|suspicious|malicious|fake|trustworth\w*|trust\s+(?:it|this)|injection|manipulat\w*")
JUDGE_VERB = r"분류|판별|판단|분석|평가|구분|\b(?:classif\w*|categori[sz]\w*|analy[sz]\w*|assess\w*|evaluat\w*|judg\w*)\b"
QUESTION_FORM = r"\?|인지|는지|은지|건지|런지|여부|\b(?:whether|if\s+(?:it|this|that)|tell\s+me\s+if|is\s+(?:it|this|that))\b"
BACKREF = (r"위|윗|앞의|이게|이거|이건|이런|이\s*(?:문장|메일|메시지|글|텍스트|내용|문구|본문|요청)|그게|그거|그런|"
           r"\b(?:this|that|these|those|it|above)\b")
BACKREF_TEXT = (r"위|윗|앞의|이\s*(?:문장|메일|메시지|글|텍스트|내용|문구|본문)|"
                r"\b(?:above|th(?:is|at|ese|ose)\s+(?:text|e-?mail|message|sentence|paragraph|note|wording|lines?)|that\s+was)\b")
# Words that look like negation inside identifiers ("no-console") are not negation; their scope is unclear,
# so they lower writes/runs to approval-required instead of granting or denying.
EN_HYPHEN_NO = re.compile(r"\bno-[a-z]")
# Typo tolerance for key English words (Damerau-Levenshtein distance <= 1, words of length >= 5).
TYPO_KEYS = ("prompt", "confirm", "before", "approve", "approval", "permission", "delete", "deploy", "modify",
             "change", "execute", "anything", "nothing", "touch", "until", "commit", "remove", "instructions")
# Text deliverables other than "prompt": the result is text for someone else, not an implementation.
TEXT_DELIVERABLE = (r"프롬프트|프[롬럼]\s*[프푸]?\s*트|지시문|지침문|지시사항|요청서|요구사항서|브리프|"
                    r"\b(?:prompts?|instruction\s+text|instructions?\s+for|brief|system\s+message)\b")
# Implementation delegated to someone else ("구현은 다른 도구가", "someone else will do the coding").
DELEGATE = (r"(?:구현|코딩|개발|작업|실행|만드는\s*건|만들기)\S*\s*(?:은|는)?.{0,20}?(?:다른\s*(?:도구|사람|에이전트|툴|팀|ai)|"
            r"내가\s*(?:할게|할께|할거|할\s*거|직접|하겠)|직접\s*할게)|(?:다른\s*(?:도구|사람|에이전트|ai)|someone\s+else|another\s+(?:tool|agent|person|ai|team)|"
            r"other\s+(?:tools?|agents?|people|team))\s*.{0,25}?(?:구현|코딩|개발|할|cod|implement|build|do\s+the|handle)|"
            r"\bi(?:'ll|\s+will)\s+(?:do|handle|write|run)\s+the\s+(?:coding|implementation|code|build)")
IMPLEMENT_VERB = r"만들|만드|구현|개발|짜|코딩|\b(?:build\w*|implement\w*|develop\w*|cod(?:e|ing))\b"
# Weak modify verbs: the target is unclear ("올려줘" may mean bump a version or upload). Never granted
# outright: they become build + confirm_first (approval-required).
WEAK_MODIFY = r"올려|올리|내려|낮춰|켜줘|켜\s*줘|꺼줘|꺼\s*줘|켜기|끄기|활성화|비활성화|고처|\b(?:enable|disable|toggle|bump|turn\s+(?:on|off))\b"
EN_CLAUSE = re.compile(r"[.!?;,\n]|\b(?:but|and|then|instead|however|while)\b")

APPROVAL_KO = r"승인|허락|허가|확인|오케이|ok|컨펌|동의|결재|사인|오케|confirm|yes|예스"
CONDITION_KO = (r"전에|전까지|이전|받고|받은후|받은뒤|받은다음|받으면|하면그때|면그때|해주면|떨어지면|나면|나서|후에|뒤에|다음에|까지|"
                r"있어야|없으면|맡고|맡은|얻고|얻은|때만|때에만|경우에만|있을때")
ASK_KO = r"물어보|물어봐|물어본|묻고|무러|여쭤|여쭈|상의|허락을구|확인받|승인받|컨펌받|허락맡|허락받|오케이받|ok받"
APPROVAL_EN = r"\b(?:approv\w*|permission|ok|okay|go-?ahead|sign-?off|green\s*light|confirm\w*|say\s+so|yes|thumbs\s*up|say-?so)\b"
CONDITION_EN = r"\b(?:before|until|till|first|after\s+i|once\s+i|when\s+i|unless|without\s+my|only\s+(?:if|when|after)|when\s+to)\b"
ASK_EN = (r"\bask\s+(?:me\s+)?(?:first|before)|\bcheck\s+with\s+me\b|\brun\s+it\s+by\s+me\b|\bwait\s+for\s+(?:my\s+)?\w+|"
          r"\bi(?:'ll|\s+will)\s+(?:tell|let)\s+you\s+(?:know\s+)?when\b|\bwait\s+(?:until|till)\s+i\b|"
          r"\bget\s+(?:a\s+|my\s+)?(?:yes|ok|okay|go-?ahead|approval|sign-?off|confirmation)\b")

READ_ONLY_KO = (r"(?:읽기|읽|보기|조회|확인|검수|리뷰|검토|분석|진단|조사|설명|살펴보기|살펴|구경|파악|점검)(?:만|하기만|해보기만|해주기만)|"
                r"읽기전용|읽기권한|열람권한|보기권한")
READ_ONLY_EN = (r"\bread[- ]?only\b|\bread\s+(?:access|permission)s?\b|\b(?:only|just)\s+(?:read|look|review|analy\w*|inspect|check|explain|examine|audit|diagnos\w*)|"
                r"\b(?:read|look|review|analy\w*|inspect|examine|audit)\w*\s+only\b|\blook\s*,?\s*(?:but|don'?t)")
PROMPT_WORD = r"프롬프트|\bprompts?\b"
PROMPT_VERB = r"작성|써|쓰|만들|만드|짜|초안|생성|줘|주세요|달라|\b(?:draft\w*|writ\w*|give|need|want|creat\w*|mak\w*|generat\w*|craft\w*|prepar\w*|compos\w*)\b"
LEAD = (r"검토|분석|요약|번역|설명|해석|읽어|리뷰|살펴|평가|진단|파악|점검|봐줘|봐주|확인해|정리|분류|의도|태깅|라벨|"
        r"무슨\s*일|뭐가\s*문제|왜|원인|"
        r"\b(?:review|analy[sz]e|summari[sz]e|translate|explain|interpret|look\s+at|check|read|inspect|evaluate|assess|"
        r"proofread|comment\s+on|examine|classify|categori[sz]e|label|tag|what\s+went\s+wrong|what\s+happened|why)\b")
# A first line that points at content ("아래 로그", "this email", "here") makes the rest of the message data.
DEICTIC = (r"아래|다음|위의?|여기|이\s*(?:로그|메일|글|텍스트|내용|이슈|티켓|diff|코드|출력|대화|문서|에러|오류|스택|메시지)|"
           r"\b(?:below|following|here|this\s+(?:log|text|e-?mail|message|issue|ticket|output|trace|diff|snippet|code|"
           r"transcript|error|stack|chat|conversation|document))\b")
# "...은 다음과 같습니다." / "as follows" with no delimiter: everything after it is data.
AS_FOLLOWS = r"다음과\s*같(?:습니다|다|아요|음|은데)|아래와\s*같(?:습니다|다|아요|음)|\bas\s+follows\b|\bis\s+below\b"
WEAK_BUILD = r"정리|정돈|\b(?:organi[sz]e|tidy)\w*"

UNLOCK_EXACT = {"제한 해제", "제한해제", "/harness-unlock", "harness unlock", "harness-unlock"}
QUOTES = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’|「[^」\n]*」|『[^』\n]*』|'[^'\n]{2,}'", re.S)


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.replace("\r\n", "\n").replace("\r", "\n").casefold()
    text = re.sub(r"[ \t 　]+", " ", text)
    return _collapse_spaced_hangul(text.strip())


def _collapse_spaced_hangul(text):
    """'배 포 는 하 지 마' (letters spaced out) -> '배포는 하지마': join syllables, then re-split after particles
    and connectives so negation scopes still end at clause boundaries."""
    hangul = re.findall(r"(?<!\S)[가-힣]+(?=[.,!?]?(?:\s|$))", text)
    singles = [t for t in hangul if len(t) == 1]
    if len(singles) < 6 or len(singles) < 0.6 * len(hangul):
        return text
    joined = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", text)
    joined = re.sub(r"(지만|는데|말고|하고|하되|고치되|되고|면서|은|는|을|를|도)(?=[가-힣]{2,})", r"\1 ", joined)
    return joined


def compact(text):
    return re.sub(r"\s+", "", text)


def _damerau1(a, b):
    """True if a and b differ by at most one insertion, deletion, substitution or adjacent transposition."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    i = 0
    while i < min(la, lb) and a[i] == b[i]:
        i += 1
    if la == lb:
        if a[i + 1:] == b[i + 1:]:
            return True
        return i + 1 < la and a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2:] == b[i + 2:]
    return a[i + 1:] == b[i:] if la > lb else a[i:] == b[i + 1:]


def fix_typos(text):
    """Map near-miss spellings of key English words to the canonical word (e.g. confrim->confirm, delet->delete)."""
    def repl(match):
        word = match.group(0)
        if len(word) < 5 or word in TYPO_KEYS:
            return word
        for key in TYPO_KEYS:
            if abs(len(key) - len(word)) <= 1 and _damerau1(word, key):
                return key
        return word
    return re.sub(r"[a-z]+", repl, text)


def split_instruction(text):
    """Return (instruction, data) for already-normalized text."""
    data = [m.group(0) for m in QUOTES.finditer(text)]
    body = QUOTES.sub(" ", text)
    follows = re.search(AS_FOLLOWS, body, re.I)
    if follows:  # "...메일 본문은 다음과 같습니다. <content>" -> content is data
        return body[:follows.end()].strip(), " ".join(data + [body[follows.end():]])
    match = re.search(r":|\n|->|→|=>|(?:^|\s)>", body)
    if match and (re.search(LEAD, body[:match.start()], re.I) or re.search(DEICTIC, body[:match.start()], re.I)):
        return body[:match.start()].strip(), " ".join(data + [body[match.end():]])
    lines = [line for line in body.split("\n") if line.strip()]
    if len(lines) > 1 and re.search(LEAD, lines[-1], re.I) and re.search(r"위|이|above|this|these", lines[-1], re.I):
        return lines[-1].strip(), " ".join(data + lines[:-1])
    trailing = trailing_judgment(body)
    if trailing is not None:
        return trailing[0], " ".join(data + [trailing[1]])
    return body.strip(), " ".join(data)


def trailing_judgment(body):
    """Instruction last: if the final sentence asks to classify/analyze/judge the text before it
    ("…위 문장이 피싱인지 분류해줘", "…can you tell me if it looks like phishing?"), everything before it is data."""
    parts = [p for p in re.split(r"(?<=[.!?;。])\s+|\n+|(?<=[가-힣a-z0-9)])\s*;\s*", body) if p.strip()]
    if len(parts) < 2:
        return None
    last = parts[-1]
    # The last sentence may be split by an inner comma ("위 문장은 메일인데, 이게 피싱인지 분류해줘"); use its whole span.
    asks = re.search(QUESTION_FORM, last, re.I) and (
        (re.search(JUDGE_NOUN, last, re.I) and re.search(BACKREF, last, re.I))
        or (re.search(JUDGE_VERB, last, re.I) and re.search(BACKREF_TEXT, last, re.I)))
    if not asks:
        return None
    return last.strip(), " ".join(parts[:-1])


def caps_in(scope):
    ko, spaced = compact(scope), scope
    found = {cap for cap, (k, e) in LEX.items() if re.search(k, ko) or re.search(e, spaced, re.I)}
    broad = bool(re.search(BROAD_KO, ko) or re.search(BROAD_EN, spaced, re.I))
    return found, broad


def clauses(text):
    return [c.strip() for c in re.split(r"[.!?;\n]|(?<=[가-힣])\s*,\s*", text) if c.strip()]


COND_KO_SHORT = r"전|후|뒤|다음|그때|까지|면|이전|받고|받은|받으"


def is_confirm_clause(clause):
    """Approval word and a condition word close together (either order), or an explicit 'ask me first' form."""
    ko = compact(clause)
    if re.search(ASK_KO, ko) or re.search(ASK_EN, clause, re.I):
        return True
    if re.search(rf"(?:{APPROVAL_KO}).{{0,8}}?(?:{COND_KO_SHORT})|(?:전에|전까지|이전에).{{0,10}}?(?:{APPROVAL_KO})", ko):
        return True
    if re.search(APPROVAL_KO, ko) and re.search(CONDITION_KO, ko):
        return True
    if re.search(r"(?:하면|되면|면|거든)그때|내가.{0,12}(?:하면|면|거든|때까지)|그다음에야|허락하면|결정하면", ko):
        return True  # conditional on the user's own later action
    approval_en = APPROVAL_EN[:-3] + r"|ask\s+me|check\s+with\s+me|consult\s+me|ping\s+me|i\s+say)\b"
    if re.search(approval_en, clause, re.I) and re.search(CONDITION_EN, clause, re.I):
        return True
    # Proximity: approval word within four words of a timing word, either order ("only … after my OK").
    near = (rf"\b(?:{COND_TOK})\b(?:\W+[\w'-]+){{0,4}}?\W+(?:{APPROVAL_TOK})\b|"
            rf"\b(?:{APPROVAL_TOK})\b(?:\W+[\w'-]+){{0,4}}?\W+(?:{COND_TOK})\b")
    return bool(re.search(near, clause, re.I))


def sentences(text):
    return [s.strip() for s in re.split(r"[.!?;\n]", text) if s.strip()]


def korean_negations(clause):
    """Yield (scope_text, (start_token, end_token)) for each Korean negation in a clause."""
    if not re.search(r"[가-힣]", clause):
        return
    tokens = clause.split()
    last_stop = -1
    skip = -1
    for i, tok in enumerate(tokens):
        if i == skip:
            continue
        standalone = bool(KO_NEG_TOKEN.match(tok))
        glued = not standalone and bool(KO_NEG_GLUED.search(tok))
        if tok.startswith("그대로") and (i == len(tokens) - 1 or re.match(r"^(?:두|둬|놔|놓|유지|남겨|둔|둘|있)", tokens[i + 1])
                                       or re.match(r"^그대로(?:두|둬|놔|유지)", tok)):
            standalone = True  # "X는 그대로 두고/그대로." = leave X unchanged (postfix negation of the object)
            if i + 1 < len(tokens) and not re.match(r"^그대로(?:두|둬|놔|유지)", tok):
                skip = i + 1
        if re.match(r"^필요(?:는|가|도)?$", tok) and i + 1 < len(tokens) and tokens[i + 1].startswith("없"):
            standalone, skip = True, i + 1  # "구현은 필요 없어": the preceding words are not wanted
        if tok == "안" and i + 1 < len(tokens):
            if re.match(r"^(?:돼|되|됩|됨|된|돼요)", tokens[i + 1]):
                standalone, skip = True, i + 1  # "X는 안 돼/안 됩니다": negates the preceding words
            elif re.match(r"^(?:해도|하셔도|해두|하도|해도돼|해도되)", tokens[i + 1]):
                standalone, skip = True, i + 1  # "구현은 안 해도 돼": negates the preceding words
            else:
                yield tokens[i + 1], tok  # "안 바꿔": negates the following verb
                continue
        if not (standalone or glued):
            continue
        end = i if glued else i - 1
        j = end
        while j > last_stop:
            if j < end and CONNECTIVE.search(tokens[j]) and not re.search(r"지$", tokens[j]):
                break
            j -= 1
        scope_tokens = tokens[j + 1:end + 1]
        last_stop = i
        if glued:
            scope_tokens[-1:] = [KO_NEG_GLUED.sub("", scope_tokens[-1])] if scope_tokens else []
        yield " ".join(scope_tokens), " ".join(tokens[i:i + 2])


def english_negations(clause):
    parts = [p for p in EN_CLAUSE.split(clause) if p and p.strip()]
    for part in parts:
        for m in EN_PREFIX.finditer(part):
            marker = m.group(0)
            scope = part[m.end():]
            if marker.startswith("hands"):
                scope = "hands off " + scope
            if marker == "not" and not caps_in(scope)[0] and not caps_in(scope)[1]:
                continue
            yield scope, marker
        for m in EN_POSTFIX.finditer(part):
            yield part[:m.start()] + " " + m.group(0), m.group(0)


def implement_in(scope):
    """Implementation verb in verb position ('앱은 만들지', '구현은 필요', "don't implement"), not a noun modifier
    ('구현 코드는 건드리지') and not the noun 'code' ('change the code')."""
    if re.search(IMPLEMENT_EN, scope, re.I):
        return True
    tokens = scope.split()
    return any(IMPLEMENT_KO_TOKEN.match(t) and (k >= len(tokens) - 2 or IMPLEMENT_KO_TOPIC.search(t))
               for k, t in enumerate(tokens))


def object_is_specific(scope):
    """'구현 코드', 'the lockfile', 'public api' are specific; '코드', 'files', 'anything' are general."""
    kept = " ".join(t for t in scope.split() if not re.search(TOUCH_WORD, t, re.I))
    words = re.findall(r"[a-z0-9_.\-/]+|[가-힣]+", kept)
    words = [re.sub(r"(?:은|는|이|가|을|를|도|만|에|의|랑|과|와)$", "", w) for w in words]
    words = [w for w in words if w and not re.match(FILLER, w)
             and not re.match(r"^(?:하지|하|지|마|말고|않|두|둬|놔|유지|남겨)$", w)]
    return bool(words) and not all(re.match(GENERAL_OBJECT, w) for w in words)


def tool_caps(scope):
    found = {cap for cap, pattern in TOOL_NOUN.items() if re.search(pattern, scope, re.I)}
    if "commit" in found:
        found.add("deploy")
    return found if found and re.search(USE_VERB, scope, re.I) else set()


def permission_denials(text, ko_all):
    """'수정권한 없음', 'no write access', 'you don't have deploy permission' -> forbid that capability."""
    forbid, unclear = set(), False
    words = [m.group(1) for m in re.finditer(
        r"([가-힣a-z]{0,8}?)권한(?:이|은|는|도)?(?:없|x|불가|제외|빼|안줘|안줄|안줌|미부여|아님)", ko_all)]
    for m in re.finditer(
            r"\bno\s+([a-z]+)\s+(?:access|permissions?|rights|privileges)\b|"
            r"\b(?:don'?t|do\s+not|doesn'?t|does\s+not)\s+have\s+(?:any\s+)?([a-z]+)\s+(?:access|permissions?|rights)\b|"
            r"\bwithout\s+([a-z]+)\s+(?:access|permissions?)\b|"
            r"\b([a-z]+)\s+(?:access|permissions?)\s*(?::|is|=)\s*(?:none|no|denied|off|disabled)\b", text, re.I):
        words.append(next(g for g in m.groups() if g is not None))
    for word in words:
        if re.search(r"읽기|열람|조회|\bread", word):
            continue
        caps, broad = caps_in(word)
        if caps:
            forbid |= caps
        elif not word or broad or re.search(r"쓰기|\bany\b", word):
            forbid |= MUTATING
        else:
            unclear = True
    return forbid, unclear


def text_only_form(text, ko_all):
    """'<noun>만 써줘', '텍스트로만', 'just write up the …', 'text only'. The noun is ignored unless it is code.
    Returns (form, implicit) where implicit means "nothing else is needed" ('…만 필요해')."""
    tokens = text.split()
    for k, tok in enumerate(tokens):
        word = re.sub(r"[^\w가-힣.]+$", "", tok)
        if not word.endswith("만") or len(word) < 2 or re.match(r"^(?:만약|만큼|만들)", word):
            continue
        head = re.sub(r"(?:로|으로)$", "", word[:-1])
        if re.search(CODE_HEAD, head, re.I):
            continue
        following = " ".join(tokens[k + 1:k + 3])
        if re.match(WRITE_REQ, following):
            return True, bool(re.match(r"^(?:필요|있으면)", following))
    if re.search(r"(?:텍스트|글|문서|말|문자|문장|문구)(?:로|으로)만", ko_all):
        return True, False
    if re.search(TEXT_FORM_EN, text, re.I):
        return True, bool(re.search(r"\b(?:just|only)\s+need\b|\ball\s+i\s+need\b", text, re.I))
    return False, False


def analyze(request, extra=()):
    text = fix_typos(normalize(request))
    instruction, data = split_instruction(text)
    forbidden, flags, notes = set(), set(), []
    blank = instruction
    impl_negated = False
    until_then = bool(re.search(UNTIL_THEN, text, re.I)) and bool(
        re.search(APPROVAL_KO, compact(text)) or re.search(rf"\b(?:{APPROVAL_TOK})\b", text, re.I))
    confirm_sentences = [s for s in sentences(text) if is_confirm_clause(s)]
    for clause in clauses(text):
        confirm = until_then or is_confirm_clause(clause) or any(clause in s for s in confirm_sentences)
        if confirm:
            flags.add("confirm_first")
        scopes = list(korean_negations(clause)) + list(english_negations(clause))
        for scope, marker in scopes:
            if re.search(HARMLESS_NEG, scope, re.I) and not caps_in(scope)[0]:
                continue
            caps, broad = caps_in(scope)
            tools = tool_caps(scope)
            if tools:
                caps = tools  # "터미널은 쓰지 마": the tool's capability, not "writing"
            if re.search(DEPLOY_TARGET, scope, re.I) and re.search(APPLY_VERB, compact(scope) + " " + scope, re.I):
                caps = (caps - {"write"}) | {"deploy"}  # "production 반영은 금지"
            if implement_in(scope) or ("write" in caps and not tools):
                impl_negated = True
            if scope.strip() and scope in blank:
                blank = blank.replace(scope, " ")
            if confirm:
                continue  # "do nothing before approval" means approval, not a permanent ban
            touch = re.search(TOUCH_WORD, scope + " " + str(marker), re.I)
            broad_object = re.search(r"anything|everything|any\s+changes?|아무", scope, re.I)
            if touch and not broad_object and object_is_specific(scope):
                # "Don't touch the lockfile" / "public API는 그대로": a specific object that cannot be mapped to
                # paths. Approval for every change keeps it gated without blocking the rest of the request.
                flags.add("confirm_first")
                notes.append(f"특정 대상 보존 요청: 변경·실행은 승인 필요 ({scope.strip()[:30]})")
                continue
            if caps:  # a specific verb wins over a broad object ("don't push anything" forbids push)
                if caps == {"write"} and re.search(CREATE_ONLY, scope, re.I) and not re.search(MODIFY_WORD, scope, re.I):
                    forbidden.add("create")  # "새 파일은 만들지 말고 …추가해줘": only new files are forbidden
                    continue
                forbidden |= caps
                if "write" in caps:
                    forbidden |= {"delete", "commit"}
                if implement_in(scope):
                    forbidden |= {"write", "execute"}  # "앱은 만들지 말고" also rules out building/running it
                if touch:
                    forbidden |= MUTATING
            elif broad:
                forbidden |= MUTATING
            elif re.search(OBJECT, scope, re.I):
                forbidden |= {"write", "delete", "commit"}
            elif scope.strip():
                flags.add("confirm_first")
                notes.append(f"범위를 판단할 수 없는 부정 표현: 모든 변경·실행에 승인 필요 ({scope.strip()[:30]})")
    ko_all, ko_ins = compact(text), compact(instruction)
    if re.search(READ_ONLY_KO, ko_all) or re.search(READ_ONLY_EN, text, re.I):
        flags.add("read_only")
    if EN_HYPHEN_NO.search(text):
        flags.add("confirm_first")
        notes.append("식별자 속 'no-'는 부정이 아니지만 범위가 불명확: 변경·실행은 승인 필요")
    perm_forbid, perm_unclear = permission_denials(text, ko_all)
    if perm_forbid:
        forbidden |= perm_forbid
        if "write" in perm_forbid:
            forbidden |= {"delete", "commit"}
            impl_negated = True
        notes.append(f"권한 없음 표현: {sorted(perm_forbid)} 차단")
    if perm_unclear:
        flags.add("confirm_first")
    delegated = bool(re.search(DELEGATE, text, re.I))
    if delegated:
        forbidden |= {"write", "execute", "deploy", "delete", "install", "commit"}
        notes.append("구현을 다른 주체에 위임함: 변경·실행 없이 텍스트 결과만")
    # Someone else (or the user, later) does part of the work: forbid exactly the actions named in that clause.
    for clause in clauses(text):
        if re.search(HANDOFF_BY, clause, re.I):
            delegated_caps = set(caps_in(clause)[0])
            if implement_in(clause) or re.search(r"구현|개발|코딩", clause):
                delegated_caps |= {"write", "execute"}
                impl_negated = True
            forbidden |= delegated_caps
            delegated = True
            notes.append(f"다른 주체·나중의 사용자에게 맡긴 작업: {sorted(delegated_caps) or '범위 없음'} 차단")
            if clause in blank:
                blank = blank.replace(clause, " ")
    handed_off = delegated or bool(re.search(HANDOFF_TO, text, re.I))
    # Text deliverable (prompt, instruction text, brief ...) asked for "only", or together with a writing verb,
    # or with the implementation delegated -> prompt_only. Checked on spaced and space-free text.
    deliverable_clause = any(re.search(TEXT_DELIVERABLE, c, re.I) and re.search(PROMPT_VERB, c, re.I)
                             for c in clauses(instruction))
    deliverable_ko = re.search(r"(?:프롬프트|프[롬럼][프푸]?트|지시문|지침문|요청서|브리프)(?:초안|문|문장|텍스트)?(?:[^.!?]{0,20})만", ko_all)
    only_en = re.search(r"\b(?:only|just|all\s+i\s+need)\b[^.!?\n]{0,30}" + r"(?:" + TEXT_DELIVERABLE + r")|"
                        r"(?:" + TEXT_DELIVERABLE + r")[^.!?\n]{0,12}\bonly\b|\bprompt[- ]only\b", text, re.I)
    if deliverable_clause or deliverable_ko or only_en or (delegated and re.search(TEXT_DELIVERABLE, text, re.I)):
        flags.add("prompt_only")
    if delegated and re.search(r"(?:문장|문구|글|텍스트|문안)만|\b(?:wording|text)\s+only\b", ko_all + " " + text):
        flags.add("prompt_only")
    # Round 2 (structural): a text-only form plus a negated implementation or a hand-off -> prompt_only,
    # whatever the deliverable is called.
    form, implicit = text_only_form(text, ko_all)
    if form and (impl_negated or implicit or handed_off):
        flags.add("prompt_only")
        notes.append("텍스트 산출물만 요청 + 구현 부정·위임: 텍스트 전용(prompt_only)")
    constraints = set(flags) | {CAP_TO_CONSTRAINT[c] for c in forbidden}
    for name in extra:
        if name not in CONSTRAINTS:
            raise ValueError(f"unknown constraint: {name}")
        constraints.add(name)
    if "analyze_only" in constraints:
        constraints.add("read_only")
    if constraints & {"prompt_only", "read_only"}:
        constraints |= set(CAP_TO_CONSTRAINT.values())
    if "no_modify" in constraints:
        constraints |= {"no_create", "no_delete", "no_commit"}
    return {"constraints": constraints, "normalized": text, "instruction": instruction, "data": data,
            "positive": blank, "notes": notes, "compact_instruction": ko_ins}


def extract(request, extra=()):
    """Backward-compatible: (constraints, spans, instruction_text)."""
    result = analyze(request, extra)
    return result["constraints"], [], result["instruction"]


def strip_payload(request):
    return split_instruction(normalize(request))[0]


def without_negated(cleaned, spans):  # kept for API compatibility
    return cleaned


def wants_unlock(request):
    """Only a message that is exactly the unlock phrase counts (quotes, questions, sentences are ignored)."""
    text = normalize(request).strip(" .!。")
    return text in UNLOCK_EXACT
