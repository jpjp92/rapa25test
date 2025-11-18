"""Streamlit 배포용 공용 설정 로더."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
from typing import Any, Dict, Optional

try:
    import streamlit as st  # type: ignore
except ImportError:  # pragma: no cover
    st = None  # Streamlit 환경이 아닐 때를 대비


def _read_secret(name: str) -> Optional[str]:
    """streamlit secrets 또는 환경변수에서 값을 읽는다."""
    if st is not None:
        try:
            secrets = st.secrets  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            secrets = {}
        if name in secrets:
            return str(secrets[name])
        # streamlit secrets 내부에서 sections에 접근
        for section in ("general", "api", "gemini"):
            try:
                section_data = secrets.get(section)  # type: ignore[call-arg]
            except Exception:
                section_data = None
            if section_data and name in section_data:
                return str(section_data[name])
    return os.getenv(name)


@dataclass(frozen=True)
class Settings:
    """Streamlit 앱 전역 설정."""

    gemini_api_key: str
    gemini_model: str = "gemini-1.5-flash"
    max_output_tokens: int = 1024
    temperature: float = 0.4
    top_p: float = 0.95
    top_k: int = 64
    safety_settings: Dict[str, Any] = field(default_factory=dict)

    def generation_config(self) -> Dict[str, Any]:
        """google-generativeai에 전달할 generation_config."""
        return {
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """환경변수/secret에서 설정을 읽어 Settings 인스턴스를 반환."""
    api_key = _read_secret("GEMINI_API_KEY") or _read_secret("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY 환경변수(또는 Streamlit secrets)가 설정되어 있지 않습니다."
        )

    model = _read_secret("GEMINI_MODEL") or "gemini-1.5-flash"
    max_output_tokens = int(_read_secret("GEMINI_MAX_OUTPUT_TOKENS") or 1024)
    temperature = float(_read_secret("GEMINI_TEMPERATURE") or 0.4)
    top_p = float(_read_secret("GEMINI_TOP_P") or 0.95)
    top_k = int(_read_secret("GEMINI_TOP_K") or 64)

    return Settings(
        gemini_api_key=api_key,
        gemini_model=model,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
    )
