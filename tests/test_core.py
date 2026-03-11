"""
핵심 순수 함수 단위 테스트 — 외부 API 호출 없음.
실행: python3 -m unittest discover tests/
"""
import os
import sys
import unittest
from unittest.mock import patch
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 환경변수 최소 설정 후 import (validate_environment 우회)
os.environ.setdefault('GEMINI_API_KEY', 'test')
os.environ.setdefault('GMAIL_APP_PASSWORD', 'test')
os.environ.setdefault('NAVER_CLIENT_ID', 'test')
os.environ.setdefault('NAVER_CLIENT_SECRET', 'test')

import newsletter_bot as nb


class TestExtractJsonFromText(unittest.TestCase):
    def test_plain_json(self):
        result = nb.extract_json_from_text('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_json_with_surrounding_text(self):
        result = nb.extract_json_from_text('some text {"key": 1} more text')
        self.assertEqual(result, {"key": 1})

    def test_nested_braces(self):
        result = nb.extract_json_from_text('{"a": {"b": "c"}}')
        self.assertEqual(result, {"a": {"b": "c"}})

    def test_no_json(self):
        result = nb.extract_json_from_text("no braces here")
        self.assertIsNone(result)

    def test_json_array(self):
        result = nb.extract_json_from_text('[{"x": 1}, {"x": 2}]')
        self.assertEqual(result, [{"x": 1}, {"x": 2}])


class TestIsNearDuplicate(unittest.TestCase):
    def test_identical_titles(self):
        self.assertTrue(nb.is_near_duplicate("오뚜기 신제품 출시", ["오뚜기 신제품 출시"]))

    def test_no_overlap(self):
        self.assertFalse(nb.is_near_duplicate("전혀 다른 제목", ["오뚜기 신제품 출시"]))

    def test_below_threshold(self):
        # 단어 겹침 < 40% → 중복 아님
        self.assertFalse(nb.is_near_duplicate("오뚜기 매출 증가", ["삼양 신제품 출시 행사"]))

    def test_empty_title(self):
        self.assertFalse(nb.is_near_duplicate("", ["오뚜기 신제품 출시"]))

    def test_empty_existing(self):
        self.assertFalse(nb.is_near_duplicate("오뚜기 신제품", []))


class TestComputeRelevanceScore(unittest.TestCase):
    def _article(self, title, desc=""):
        return {"title": title, "desc": desc}

    def test_high_relevance_panel_c(self):
        article = self._article("오뚜기 라면 신제품 출시 실적 발표")
        score = nb.compute_relevance_score(article, "PANEL_C")
        self.assertGreater(score, 0.4)

    def test_zero_score_unrelated(self):
        article = self._article("스포츠 경기 결과 야구")
        score = nb.compute_relevance_score(article, "PANEL_C")
        self.assertEqual(score, 0.0)

    def test_score_bounded(self):
        article = self._article("오뚜기 라면 농심 삼양 CJ 풀무원 수출 ESG 채용 실적")
        score = nb.compute_relevance_score(article, "PANEL_C")
        self.assertLessEqual(score, 1.0)

    def test_unknown_panel_returns_default(self):
        article = self._article("any title")
        score = nb.compute_relevance_score(article, "UNKNOWN_PANEL")
        self.assertEqual(score, 0.5)


class TestQualityGate(unittest.TestCase):
    def _panel(self, n):
        return [{"headline": f"item{i}"} for i in range(n)]

    def test_two_real_panels_full(self):
        panel_results = {
            "PANEL_A": self._panel(2),
            "PANEL_B": self._panel(2),
            "PANEL_C": [],
        }
        panel_is_fallback = {"PANEL_A": False, "PANEL_B": False, "PANEL_C": True}
        should_send, edition, warnings = nb.quality_gate(panel_results, panel_is_fallback, None)
        self.assertTrue(should_send)
        self.assertEqual(edition, "full")

    def test_one_real_panel_full_with_warning(self):
        panel_results = {
            "PANEL_A": self._panel(2),
            "PANEL_B": [],
            "PANEL_C": [],
        }
        panel_is_fallback = {"PANEL_A": False, "PANEL_B": True, "PANEL_C": True}
        should_send, edition, warnings = nb.quality_gate(panel_results, panel_is_fallback, None)
        self.assertTrue(should_send)
        self.assertEqual(edition, "full")
        self.assertTrue(len(warnings) > 0)

    def test_zero_real_panels_with_fallback_light(self):
        panel_results = {
            "PANEL_A": self._panel(1),
            "PANEL_B": [],
            "PANEL_C": [],
        }
        panel_is_fallback = {"PANEL_A": True, "PANEL_B": True, "PANEL_C": True}
        should_send, edition, warnings = nb.quality_gate(panel_results, panel_is_fallback, None)
        self.assertTrue(should_send)
        self.assertEqual(edition, "light")

    def test_zero_content_skip(self):
        panel_results = {"PANEL_A": [], "PANEL_B": [], "PANEL_C": []}
        panel_is_fallback = {"PANEL_A": True, "PANEL_B": True, "PANEL_C": True}
        should_send, edition, warnings = nb.quality_gate(panel_results, panel_is_fallback, None)
        self.assertFalse(should_send)
        self.assertEqual(edition, "skip")


class TestValidateEnvironment(unittest.TestCase):
    def test_newsletter_all_present(self):
        with patch.dict(os.environ, {
            'GMAIL_APP_PASSWORD': 'pw',
            'GEMINI_API_KEY': 'key',
            'NAVER_CLIENT_ID': 'id',
            'NAVER_CLIENT_SECRET': 'secret',
        }):
            nb.validate_environment('newsletter')  # should not raise

    def test_newsletter_missing_raises(self):
        env = {
            'GMAIL_APP_PASSWORD': 'pw',
            'GEMINI_API_KEY': 'key',
            'NAVER_CLIENT_ID': '',
            'NAVER_CLIENT_SECRET': '',
        }
        with patch.dict(os.environ, env, clear=False):
            # NAVER keys unset
            with patch.dict(os.environ, {'NAVER_CLIENT_ID': '', 'NAVER_CLIENT_SECRET': ''}):
                os.environ.pop('NAVER_CLIENT_ID', None)
                os.environ.pop('NAVER_CLIENT_SECRET', None)
                with self.assertRaises(EnvironmentError):
                    nb.validate_environment('newsletter')

    def test_weekend_only_needs_app_password(self):
        with patch.dict(os.environ, {'GMAIL_APP_PASSWORD': 'pw'}, clear=False):
            nb.validate_environment('weekend')  # should not raise


class TestDedupAcrossPanels(unittest.TestCase):
    def _art(self, title):
        return {"title": title, "desc": "", "link": "http://example.com"}

    def test_ab_dedup_removes_near_duplicate(self):
        panel_a = [self._art("오뚜기 라면 수출 급증 발표")]
        panel_b = [self._art("오뚜기 라면 수출 급증 발표")]  # identical
        panel_c = []
        _, deduped_b, _ = nb.dedup_across_panels(panel_a, panel_b, panel_c)
        self.assertEqual(len(deduped_b), 0)

    def test_no_overlap_keeps_all(self):
        panel_a = [self._art("글로벌 원자재 가격 상승")]
        panel_b = [self._art("고용노동부 최저임금 발표")]
        panel_c = [self._art("오뚜기 신제품 출시")]
        a, b, c = nb.dedup_across_panels(panel_a, panel_b, panel_c)
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertEqual(len(c), 1)

    def test_priority_a_over_c(self):
        panel_a = [self._art("오뚜기 라면 글로벌 수출")]
        panel_b = []
        panel_c = [self._art("오뚜기 라면 글로벌 수출")]  # duplicate of A
        _, _, deduped_c = nb.dedup_across_panels(panel_a, panel_b, panel_c)
        self.assertEqual(len(deduped_c), 0)


class TestCallGemini(unittest.TestCase):
    def test_gemini_success(self):
        """Gemini API 정상 응답 테스트."""
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"signal_strength": "High", "fact": "Test fact"}'
                    }]
                }
            }]
        }
        mock_res = unittest.mock.MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = mock_response

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_res
            result, error = nb.call_gemini(
                "test-api-key",
                "test prompt",
                max_retries=3
            )
            self.assertIsNotNone(result)
            self.assertIsNone(error)
            self.assertIn("signal_strength", result)

    def test_gemini_retry_on_timeout(self):
        """Gemini API 타임아웃 재시도 로직 테스트."""
        mock_response = {
            "candidates": [{
                "content": {"parts": [{"text": '{"signal_strength": "Medium"}'}]}
            }]
        }
        mock_res = unittest.mock.MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = mock_response

        with patch('requests.post') as mock_post:
            # 첫 2번 타임아웃, 3번째 성공
            mock_post.side_effect = [
                unittest.mock.Mock(side_effect=requests.exceptions.Timeout()),
                unittest.mock.Mock(side_effect=requests.exceptions.Timeout()),
                mock_res
            ]
            result, error = nb.call_gemini(
                "test-api-key",
                "test prompt",
                max_retries=3
            )
            # 3번째 시도에서 성공해야 함
            self.assertEqual(mock_post.call_count, 3)


class TestFetchNews(unittest.TestCase):
    def test_fetch_news_returns_list(self):
        """Naver API 응답이 리스트를 반환하는지 테스트."""
        with patch('requests.get') as mock_get:
            # Naver API 모의 응답
            mock_response = {
                "items": [
                    {
                        "title": "오뚜기 신제품 출시",
                        "link": "https://example.com/1",
                        "originallink": "https://original.com/1",
                        "description": "신제품 설명",
                        "pubDate": "Wed, 12 Mar 2026 10:00:00 +0900"
                    }
                ]
            }
            mock_res = unittest.mock.MagicMock()
            mock_res.json.return_value = mock_response
            mock_res.status_code = 200
            mock_get.return_value = mock_res

            result = nb.fetch_news("PANEL_C", nb.PROFILE["PANEL_C"])
            self.assertIsInstance(result, list)


class TestAnalyzePanelFallback(unittest.TestCase):
    def test_analyze_panel_success(self):
        """analyze_panel 정상 작동 테스트."""
        mock_response = {
            "candidates": [{
                "content": {"parts": [{"text": '{"signal_strength": "High"}'}]}
            }]
        }
        articles = [
            {
                "title": "테스트 기사",
                "desc": "테스트 설명",
                "link": "https://example.com"
            }
        ]
        mock_res = unittest.mock.MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = mock_response

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_res
            result, error = nb.analyze_panel(
                "test-api-key",
                articles,
                "PANEL_A"
            )
            # 정상 작동하면 결과가 반환되어야 함
            self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
