import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))

from harness100.constraints import extract, strip_payload, wants_unlock  # noqa: E402
from harness100.router import route  # noqa: E402


class ConstraintExtraction(unittest.TestCase):
    CASES = {
        "프롬프트만 작성해줘": "prompt_only",
        "읽기만 해줘": "read_only",
        "읽기 전용으로 검수": "read_only",
        "원인 분석만 해줘": "analyze_only",
        "수정하지 마": "no_modify",
        "파일은 건드리지 말고 봐줘": "no_modify",
        "실행하지 마": "no_execute",
        "코드는 돌리지 말고": "no_execute",
        "배포하지 마": "no_deploy",
        "배포는 하지 마세요": "no_deploy",
        "사용자 확인 후 진행해": "confirm_first",
        "진행하기 전에 먼저 물어봐": "confirm_first",
        "삭제하지 마": "no_delete",
        "설치하지 말고": "no_install",
        "외부 전송 금지": "no_network",
        "커밋하지 마": "no_commit",
        "Do not modify any files": "no_modify",
        "don't run anything": "no_execute",
        "don't deploy": "no_deploy",
        "ask me before changing": "confirm_first",
        "read-only review please": "read_only",
    }

    def test_each_restriction_is_detected(self):
        for text, expected in self.CASES.items():
            with self.subTest(text=text):
                self.assertIn(expected, extract(text)[0])

    def test_plain_action_words_are_not_restrictions(self):
        for text in ("로그인 버그를 수정해줘", "테스트를 실행해줘", "앱을 배포해줘", "파일을 삭제해줘"):
            with self.subTest(text=text):
                self.assertEqual(extract(text)[0], set())

    def test_quoted_and_pasted_payload_is_data(self):
        self.assertNotIn("deploy", strip_payload("다음 문장을 번역해줘: Please deploy the app."))
        self.assertEqual(extract('"수정하지 마"라는 문장을 영어로 번역해줘')[0], set())

    def test_host_can_add_but_not_invent_constraints(self):
        self.assertIn("read_only", extract("구현해줘", extra=("read_only",))[0])
        with self.assertRaises(ValueError):
            extract("x", extra=("allow_everything",))

    def test_unlock_phrase(self):
        self.assertTrue(wants_unlock("이제 제한 해제"))
        self.assertFalse(wants_unlock("제한을 유지해"))


class Routing(unittest.TestCase):
    def test_simple_requests_need_no_modules_and_no_probe(self):
        with patch("harness100.router.inspect_project", side_effect=AssertionError("probe")):
            for text in ("안녕", "2+2는?", "테스트라는 단어의 뜻은?", "What is a git filter?",
                         "다음 문장을 번역해줘: Please deploy the app.", "이 글을 요약해줘: 배포 완료"):
                with self.subTest(text=text):
                    r = route(text, project="missing")
                    self.assertEqual(r["skills"], [])
                    self.assertFalse(r["activate_harness"])
                    self.assertEqual(r["policy"]["execution"], "answer_only")

    def test_prompt_only_variants_never_become_build(self):
        with patch("harness100.router.inspect_project", side_effect=AssertionError("probe")):
            for text in ("로그인 기능 구현 프롬프트만 작성해줘", "로그인 기능을 구현할 프롬프트 초안만 작성해줘",
                         "배포 자동화 프롬프트를 작성해줘", "프롬프트만. 구현은 하지 마", "Write a prompt for a login feature"):
                for intent in ("auto", "build", "recover"):
                    with self.subTest(text=text, intent=intent):
                        r = route(text, intent=intent, project="missing")
                        self.assertEqual(r["policy"]["execution"], "prompt_only")
                        self.assertEqual(r["capabilities"], [])
                        self.assertNotIn("build", r["skills"])

    def test_user_restriction_beats_host_intent_flag(self):
        r = route("읽기 전용으로 변경사항 검수", intent="build", test_result="failed")
        self.assertEqual(r["capabilities"], ["read"])
        self.assertEqual(r["policy"]["execution"], "read_only")

    def test_review_and_audit_are_read_only(self):
        for text in ("이 PR의 변경사항을 리뷰해줘", "현재 변경을 검수해줘", "review this diff"):
            with self.subTest(text=text):
                r = route(text)
                self.assertEqual(r["intent"], "audit")
                self.assertEqual(r["capabilities"], ["read"])

    def test_multi_intent_merges_modules_without_duplicates(self):
        r = route("설계한 다음 검색 기능을 구현해줘")
        self.assertTrue({"plan", "build", "verify"} <= set(r["skills"]))
        r = route("실패한 로그인 테스트를 고치고 보안 검토 후 100점 평가해줘", test_result="failed")
        self.assertEqual(len(r["skills"]), len(set(r["skills"])))
        self.assertTrue({"recovery", "security", "score"} <= set(r["skills"]))
        self.assertIn("한 번만", r["prompt"]["Instructions"]["integration"])

    def test_restrictions_remove_capabilities(self):
        self.assertNotIn("write", route("파일은 건드리지 말고 로그인 오류를 고쳐줘")["capabilities"])
        self.assertNotIn("execute", route("코드는 돌리지 말고 로그인 기능을 구현해줘")["capabilities"])
        self.assertIn("write", route("코드는 돌리지 말고 로그인 기능을 구현해줘")["capabilities"])
        self.assertNotIn("deploy", route("배포하지 마. 빌드 스크립트만 고쳐줘")["capabilities"])
        self.assertEqual(route("수정하지 마. 로그인 버그 원인만 분석해줘")["capabilities"], ["read"])

    def test_ambiguous_request_gets_no_capabilities(self):
        r = route("음 그거 좀 어떻게 해봐")
        self.assertEqual(r["capabilities"], [])

    def test_legacy_alias_respects_negation(self):
        self.assertEqual(route("기본스킬 v1.2로 설계해줘")["integration"], "prompt-builder-v1.2")
        self.assertEqual(route("기본스킬 v1.2는 쓰지 말고 v2.0으로 기능을 구현해줘")["integration"], "prompt-builder-v2")
        self.assertEqual(route("라이브러리 v1.2 기능 구현")["integration"], "prompt-builder-v2")

    def test_modes(self):
        self.assertEqual(route("새 서비스 아이디어 탐색")["mode"], "탐색")
        self.assertEqual(route("심층 모드로 원인 분석")["mode"], "심층")
        self.assertEqual(route("일반 모드로 로그인 구현")["mode"], "일반")

    def test_invalid_inputs(self):
        for kwargs in ({"request": ""}, {"request": "x", "mode": "bad"}, {"request": "x", "intent": "shell"}):
            with self.assertRaises(ValueError):
                route(**kwargs)

    def test_cli_route_json(self):
        proc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c",
                               "import sys,runpy; sys.path.insert(0, sys.argv[1]); sys.argv=['h','route','--request','읽기만 해줘. 구조 설명'];"
                               "runpy.run_module('harness100', run_name='__main__')", str(PKG)],
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(data["capabilities"], ["read"])


if __name__ == "__main__":
    unittest.main()
