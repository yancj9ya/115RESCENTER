from __future__ import annotations

import unittest

from src.organizing.ai_filename_parser import AiFilenameParser


class AiFilenameParserTest(unittest.TestCase):
    def test_parses_valid_json_result(self) -> None:
        prompts: list[str] = []

        def client(prompt: str) -> str:
            prompts.append(prompt)
            return """
            {
                "type": "tv",
                "title": "主角",
                "original_title": null,
                "year": "2026",
                "season": 1,
                "episode": 38,
                "resolution": "2160p",
                "source": "WEB-DL",
                "release_group": "XH",
                "audio_codec": "AAC",
                "video_codec": "HEVC"
            }
            """

        result = AiFilenameParser(client).parse("主角.2026.S01E38.2160p.WEB-DL.H.265-XH.mkv")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("请解析此文件名：主角.2026.S01E38.2160p.WEB-DL.H.265-XH.mkv", prompts[0])
        self.assertEqual(result.type, "tv")
        self.assertEqual(result.title, "主角")
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.season, 1)
        self.assertEqual(result.episode, 38)
        self.assertEqual(result.resolution, "2160p")
        self.assertEqual(result.source, "WEB-DL")
        self.assertEqual(result.release_group, "XH")
        self.assertEqual(result.audio_codec, "AAC")
        self.assertEqual(result.video_codec, "HEVC")

    def test_parses_json_code_block_and_forces_tv_when_episode_exists(self) -> None:
        parser = AiFilenameParser(
            lambda _prompt: """```json
{"type":"movie","title":"三体","year":2024,"season":1,"episode":"2"}
```"""
        )

        result = parser.parse("三体.S01E02.mkv")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.type, "tv")
        self.assertEqual(result.episode, 2)

    def test_returns_none_for_missing_title_bad_json_or_invalid_fields(self) -> None:
        self.assertIsNone(AiFilenameParser(lambda _prompt: "not-json").parse("a.mkv"))
        self.assertIsNone(AiFilenameParser(lambda _prompt: '{"title":""}').parse("a.mkv"))
        self.assertIsNone(AiFilenameParser(lambda _prompt: '{"title":"A","year":9999}').parse("a.mkv"))
        self.assertIsNone(AiFilenameParser(lambda _prompt: '{"title":"A","season":0}').parse("a.mkv"))

    def test_returns_none_when_client_raises(self) -> None:
        def client(_prompt: str) -> str:
            raise RuntimeError("network unavailable")

        self.assertIsNone(AiFilenameParser(client).parse("a.mkv"))


if __name__ == "__main__":
    unittest.main()
