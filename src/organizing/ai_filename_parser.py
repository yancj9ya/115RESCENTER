from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

MediaType = Literal["movie", "tv"]

DEFAULT_AI_FILENAME_PROMPT = """你是一个媒体文件名解析器。分析给定的文件名并将媒体信息提取为JSON格式。

规则：
1. 始终返回有效的JSON，不要包含额外文本
2. 如果对任何字段不确定，使用null而不是留空
3. 对于电视节目，从如S01E02、第1季、第1集、第1话、Season 1等模式中识别季数/集数
4. 检测发布信息，如BluRay、WEB-DL、HDTV等
5. 从标题中删除常见术语，如x264、AAC、HEVC
6. 修正标题中的拼写错误并确保准确性：
   - 更正常见的拼写错误（例如，'Marix'应为'Matrix'）
   - 修正以匹配官方标题（例如，'Star Wors'应为'Star Wars'）
   - 保持正确的大小写
   - 对于知名电影和电视节目，根据官方标题验证并更正任何变体
   - 处理流行系列中的常见拼写错误（例如，'Jurasic Park'改为'Jurassic Park'）
   - 将地区性拼写差异更正为原始标题（例如，'The Persute of Happyness'改为'The Pursuit of Happyness'）
   - 修正数字续集（例如，'Fast and Furios 5'改为'Fast and Furious 5'）
   - 保留官方标题中有意的风格化拼写（例如，'Se7en'）
7. 对于可以验证的电影和电视节目：
   - 将给定标题与官方标题进行比较
   - 修正任何拼写错误或笔误
   - 在输出中使用正确的官方标题
8. 当遇到中文字符和数字连在一起时，请将它们分开。例如，"异世界失格01正式版全片简中"应改为"异世界失格 01 正式版全片简中"
9. 如果识别出集数，类型必须是tv
10. 对于看起来是故意混淆的中文标题，尝试还原原始标题。例如：
    - "白夜石皮日尧"应还原为"白夜破晓"
    - "复仇者联门"应还原为"复仇者联盟"
    - "你de名字"应还原为"你的名字"
    - 寻找字符被分割或替换为相似字符的模式
    - 还原时考虑上下文和常见的媒体标题
    - 仅在确信原始标题时进行还原
11. 如果是英文标题，则在网络搜索出中文标题，进行title的替换
12. 对于年份，使用确定的标题在TMDB中进行搜索，然后修改年份

要求的JSON结构：
{
    "type": "movie|tv|null",
    "title": "不含年份/季数的干净标题，如果搜索出中文结果，则替换中文的干净结果",
    "original_title": "如果不同则为原始语言的标题，如果搜索出中文结果，则采用中文",
    "year": "YYYY|null",
    "season": number|null,
    "episode": number|null,
    "resolution": "2160p|1080p|720p|480p|null",
    "source": "BluRay|WEB-DL|HDTV|DVD|null",
    "release_group": "发布组名称|null",
    "audio_codec": "DTS|AAC|AC3|null",
    "video_codec": "x264|x265|AVC|HEVC|null"
}

输入示例："The.Matrix.1999.2160p.UHD.BluRay.x265-RARBG.mkv"
输出示例：{
    "type": "movie",
    "title": "The Matrix",
    "original_title": null,
    "year": "1999",
    "season": null,
    "episode": null,
    "resolution": "2160p",
    "source": "BluRay",
    "release_group": "RARBG",
    "audio_codec": null,
    "video_codec": "x265"
}
"""


@dataclass(frozen=True)
class AiFilenameParserConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout_seconds: float = 30.0
    title_similarity_threshold: float = 0.55
    prompt: str = DEFAULT_AI_FILENAME_PROMPT


@dataclass(frozen=True)
class AiFilenameParseResult:
    type: MediaType | None
    title: str
    original_title: str | None = None
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    resolution: str | None = None
    source: str | None = None
    release_group: str | None = None
    audio_codec: str | None = None
    video_codec: str | None = None


class AiFilenameParser:
    def __init__(self, client: Callable[[str], str], *, prompt: str = DEFAULT_AI_FILENAME_PROMPT) -> None:
        self._client = client
        self._prompt = prompt.strip()

    def parse(self, filename: str) -> AiFilenameParseResult | None:
        cleaned_filename = str(filename).strip()
        if not cleaned_filename:
            return None
        try:
            raw_response = self._client(self._build_prompt(cleaned_filename))
            payload = _load_json_object(raw_response)
            return _parse_result(payload)
        except Exception as exc:
            logger.warning(f"AI 文件名解析失败: {cleaned_filename} - {exc}")
            return None

    def _build_prompt(self, filename: str) -> str:
        return f"{self._prompt}\n\n请解析此文件名：{filename}"


class OpenAICompatibleFilenameClient:
    def __init__(self, config: AiFilenameParserConfig) -> None:
        if not config.api_key.strip():
            raise ValueError("AI api_key is required")
        if not config.base_url.strip():
            raise ValueError("AI base_url is required")
        if not config.model.strip():
            raise ValueError("AI model is required")
        self._config = config

    def __call__(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            self._config.base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"])


def build_ai_filename_parser(config: AiFilenameParserConfig | None) -> AiFilenameParser | None:
    if config is None or not config.enabled:
        return None
    if config.provider != "openai_compatible":
        raise ValueError(f"unsupported AI provider: {config.provider}")
    return AiFilenameParser(OpenAICompatibleFilenameClient(config), prompt=config.prompt)


def _load_json_object(text: str) -> dict[str, Any]:
    raw = str(text).strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < start:
            raise ValueError("AI response does not contain a JSON object")
        raw = raw[start : end + 1]
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("AI response JSON must be an object")
    return payload


def _parse_result(payload: dict[str, Any]) -> AiFilenameParseResult | None:
    title = _string_or_none(payload.get("title"))
    if title is None:
        return None
    media_type = _media_type_or_none(payload.get("type"))
    season = _positive_int_or_none(payload.get("season"), "season")
    episode = _positive_int_or_none(payload.get("episode"), "episode")
    if episode is not None:
        media_type = "tv"
    return AiFilenameParseResult(
        type=media_type,
        title=title,
        original_title=_string_or_none(payload.get("original_title")),
        year=_year_or_none(payload.get("year")),
        season=season,
        episode=episode,
        resolution=_string_or_none(payload.get("resolution")),
        source=_string_or_none(payload.get("source")),
        release_group=_string_or_none(payload.get("release_group")),
        audio_codec=_string_or_none(payload.get("audio_codec")),
        video_codec=_string_or_none(payload.get("video_codec")),
    )


def _media_type_or_none(value: Any) -> MediaType | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"movie", "tv"}:
        return normalized  # type: ignore[return-value]
    raise ValueError(f"invalid media type: {value!r}")


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _year_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
        return None
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid year: {value!r}") from exc
    if year < 1800 or year > 2100:
        raise ValueError(f"invalid year: {year}")
    return year


def _positive_int_or_none(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc
    if number <= 0:
        raise ValueError(f"invalid {field_name}: {number}")
    return number
