"""Streamlit 앱에서 사용하는 기본 프롬프트 래퍼."""

from typing import Optional, Dict

from raw_image25.lib.gemini_prompt import get_image_analysis_prompt


def build_default_prompt(image_metadata: Optional[Dict] = None) -> str:
    """raw_image25의 Gemini 프롬프트를 그대로 활용."""
    return get_image_analysis_prompt(image_metadata=image_metadata)


DEFAULT_IMAGE_PROMPT = build_default_prompt()

__all__ = ["DEFAULT_IMAGE_PROMPT", "build_default_prompt"]
