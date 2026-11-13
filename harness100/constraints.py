"""Extract explicit user restrictions from the user's own request text.

Only the request typed by the user is a source of constraints. Project files, tool output and
quoted/pasted payloads are data. Constraints are monotonic: callers may add more, never remove.
"""

import re
import unicodedata

CONSTRAINTS = ("prompt_only", "read_only", "analyze_only", "no_modify", "no_execute", "no_deploy",
               "no_delete", "no_install", "no_network", "no_commit", "confirm_first")

# Korean negation after a verb stem: 하지 마 / 지 말고 / 지 않고 / 금지 / 없이 / 마세요
NEG = r"(?:[가-힣]{0,4}\s*)?(?:지\s*마|지\s*말|지\s*않|하지\s*마|말아|금지|없이|마세요|안\s*돼|불가)"
EN_NEG = r"(?:do\s*n[o']?t|don't|never|no|without)\s+"

PATTERNS = {
    "prompt_only": [
        r"프롬프트[^.!?\n]{0,30}?만\s*(?:작성|써|만들|생성|짜|줘|해)",
        r"프롬프트만",
        r"프롬프트\s*(?:초안|문안)?\s*(?:을|를)?\s*(?:작성|써|만들|생성|짜)",
        r"prompt[- ]only", r"only\s+(?:write\s+)?(?:a|the)?\s*prompt", r"(?:write|draft)\s+(?:a|the)?\s*prompt",
    ],
    "read_only": [r"읽기\s*전용", r"읽기만", r"보기만", r"조회만", r"확인만", r"검수만", r"리뷰만", r"검토만",
                  r"read[- ]only", r"only\s+read", r"just\s+read"],
    "analyze_only": [r"분석만", r"조사만", r"진단만", r"원인만", r"(?:analy[sz]e|investigate)\s+only", r"only\s+analy[sz]e"],
    "no_modify": [r"(?:수정|변경|편집|고치|건드리|손대|손\s*대|쓰기|덮어쓰)" + NEG, r"수정\s*금지",
                  EN_NEG + r"(?:modify|modifying|change|changing|edit|editing|touch|touching|write|writing)\b"],
    "no_execute": [r"(?:실행|돌리|구동|빌드)" + NEG, r"실행\s*없이",
                   EN_NEG + r"(?:run|running|execute|executing)\b", r"no\s+execution"],
    "no_deploy": [r"(?:배포|푸시|push|릴리스|릴리즈|게시|publish)" + NEG, EN_NEG + r"(?:deploy|push|publish|release)\b"],
    "no_delete": [r"(?:삭제|지우|제거)" + NEG, EN_NEG + r"(?:delete|remove|rm)\b"],
    "no_install": [r"(?:설치)" + NEG, EN_NEG + r"(?:install|installing)\b"],
    "no_network": [r"(?:외부|네트워크|인터넷|웹|온라인)\s*(?:접근|접속|전송|요청|검색|연결)?" + NEG,
                   r"오프라인으로", EN_NEG + r"(?:network|internet|external)\b", r"\boffline\b"],
    "no_commit": [r"(?:커밋|commit)" + NEG, EN_NEG + r"commit\b"],
    "confirm_first": [r"(?:사용자\s*)?(?:확인|승인|허락|컨펌|동의)\s*(?:을|를)?\s*(?:받고|받은\s*(?:후|뒤|다음)|후에?|뒤에?|다음에)",
                      r"(?:진행|실행|적용|수정)\s*(?:하기\s*)?전에?\s*(?:꼭\s*|먼저\s*|반드시\s*)?(?:확인|물어|승인)",
                      r"먼저\s*물어", r"ask\s+(?:me\s+)?(?:before|first)", r"confirm\s+(?:with\s+me\s+)?(?:before|first)",
                      r"wait\s+for\s+(?:my\s+)?approval"],
}

UNLOCK = re.compile(r"(?:제한\s*해제|harness[- ]unlock|/harness-unlock)", re.IGNORECASE)

QUOTES = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’|「[^」\n]*」|『[^』\n]*』|'[^'\n]{4,}'", re.S)
PAYLOAD_LEAD = re.compile(r"(다음|아래|이|위)\s*(문장|글|텍스트|내용|문단|메시지|이메일|코드|문구)?[^:\n]{0,40}?"
                          r"(번역|요약|교정|설명|해석|translate|summari[sz]e|proofread)[^:\n]{0,20}:|"
                          r"(translate|summari[sz]e|proofread)[^:\n]{0,40}:", re.IGNORECASE)


def normalize(text):
    return unicodedata.normalize("NFKC", text or "")


def strip_payload(request):
    """Remove quoted or pasted data so that words inside it never become constraints or intents."""
    text = normalize(request)
    text = QUOTES.sub(" ", text)
    match = PAYLOAD_LEAD.search(text)
    if match:
        text = text[:match.end()]
    return text


def extract(request, extra=()):
    """Return (constraints:set, spans:list, cleaned_text:str). `extra` lets a host add constraints."""
    cleaned = strip_payload(request)
    found, spans = set(), []
    for name, patterns in PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, cleaned, re.IGNORECASE):
                found.add(name)
                spans.append((match.start(), match.end(), name))
    for name in extra:
        if name not in CONSTRAINTS:
            raise ValueError(f"unknown constraint: {name}")
        found.add(name)
    # Implications: restriction words narrow each other, never widen.
    if "prompt_only" in found:
        found |= {"no_modify", "no_execute", "no_deploy", "no_delete", "no_install", "no_network", "no_commit"}
    if found & {"read_only", "analyze_only"}:
        found |= {"no_modify", "no_execute", "no_deploy", "no_delete", "no_install", "no_network", "no_commit"}
    if "no_modify" in found:
        found |= {"no_delete", "no_commit"}
    return found, spans, cleaned


def without_negated(cleaned, spans):
    """Text for intent detection with restriction phrases blanked (\"배포하지 마\" is not a deploy request)."""
    chars = list(cleaned)
    for start, end, name in spans:
        if name in ("prompt_only", "confirm_first"):
            continue
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


def wants_unlock(request):
    return bool(UNLOCK.search(normalize(request)))
