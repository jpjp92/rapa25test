"""
Gemini 이미지 분석 모듈
Google Gemini API를 사용하여 이미지 분석 (카테고리, 설명문 생성)
"""

import google.generativeai as genai
import base64
import json
import time
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime
from .categories import CATEGORY_DATA
from .gemini_prompt import get_image_analysis_prompt


class GeminiImageAnalyzer:
    """Gemini를 사용한 이미지 분석 클래스"""

    def __init__(self, api_key: Optional[str] = None):
        """
        GeminiImageAnalyzer 초기화

        Args:
            api_key: Google Gemini API 키 (선택사항)
        """
        self.api_key = api_key
        self.model = None

        # API 키가 제공되면 즉시 초기화
        if api_key:
            self._configure_api(api_key)

    def _configure_api(self, api_key: str):
        """
        API 설정 및 모델 초기화

        Args:
            api_key: Google Gemini API 키
        """
        genai.configure(api_key=api_key)

        # Safety Settings: 모든 카테고리를 BLOCK_NONE으로 완화
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]

        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={
                "temperature": 0,
                "top_p": 1,
                "top_k": 1,
                "max_output_tokens": 65536,  # Gemini 2.5 Flash 최대값 (이전: 8192)
                "response_mime_type": "application/json",
            },
            safety_settings=safety_settings
        )

    def file_to_base64(self, file_path: str) -> str:
        """
        파일을 Base64로 변환

        Args:
            file_path: 파일 경로

        Returns:
            Base64 인코딩된 문자열
        """
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    @staticmethod
    def get_default_prompt(image_metadata: Optional[Dict] = None) -> str:
        """
        기본 이미지 분석 프롬프트 생성

        Args:
            image_metadata: 이미지 메타데이터

        Returns:
            프롬프트 문자열
        """
        return get_image_analysis_prompt(image_metadata)

    async def analyze_image(
        self,
        file_path: str,
        mime_type: str,
        image_metadata: Optional[Dict] = None,
        api_key: Optional[str] = None
    ) -> Dict:
        """
        이미지 분석 실행

        Args:
            file_path: 이미지 파일 경로
            mime_type: MIME 타입 (예: "image/jpeg")
            image_metadata: 이미지 메타데이터 (선택사항)
            api_key: Gemini API 키 (선택사항)

        Returns:
            분석 결과 딕셔너리
        """
        try:
            # API 키 설정
            effective_api_key = api_key or self.api_key

            if not effective_api_key:
                raise ValueError("API 키가 제공되지 않았습니다.")

            # API 키가 변경되었거나 모델이 없으면 재설정
            if api_key and (api_key != self.api_key or not self.model):
                self._configure_api(api_key)
            elif not self.model:
                self._configure_api(effective_api_key)

            print(f"🖼️  이미지 분석 시작: {file_path}")

            # 프롬프트 생성
            prompt = self.get_default_prompt(image_metadata)

            # 파일을 Base64로 변환
            print("📤 이미지 파일 Base64 인코딩 중...")
            import asyncio
            base64_data = await asyncio.to_thread(self.file_to_base64, file_path)
            print(f"✅ Base64 인코딩 완료 (크기: {len(base64_data)} bytes)")

            # API 요청
            # 재시도 로직 추가: 500 에러 발생 시 최대 3번 재시도
            print("📤 Gemini API 요청 시작")
            print(f"⏰ 요청 시간: {datetime.now().strftime('%H:%M:%S')}")

            max_retries = 3
            retry_delay = 5  # 초
            api_timeout = 120  # API 요청 타임아웃 (초) - 2분
            response = None
            last_error = None

            for attempt in range(max_retries):
                try:
                    request_start_time = time.time()

                    # 타임아웃 설정: 2분 이상 걸리면 TimeoutError 발생
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.model.generate_content,
                            [
                                {
                                    "inline_data": {
                                        "data": base64_data,
                                        "mime_type": mime_type
                                    }
                                },
                                {"text": prompt}
                            ]
                        ),
                        timeout=api_timeout
                    )

                    request_duration = time.time() - request_start_time

                    # 성공하면 루프 탈출
                    if attempt > 0:
                        print(f"✅ 재시도 성공! (시도 {attempt + 1}/{max_retries})")
                    break

                except asyncio.TimeoutError:
                    last_error = asyncio.TimeoutError(f"API 요청 타임아웃 ({api_timeout}초 초과)")

                    if attempt < max_retries - 1:
                        print(f"⏱️  API 요청 타임아웃 ({api_timeout}초 초과)")
                        print(f"🔄 {retry_delay}초 후 재시도... (시도 {attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                    else:
                        print(f"❌ 최대 재시도 횟수 도달 ({max_retries}번)")
                        raise last_error

                except Exception as e:
                    last_error = e
                    error_msg = str(e)

                    # 500 에러 또는 internal error인 경우만 재시도
                    is_retryable = ("500" in error_msg or
                                   "internal error" in error_msg.lower() or
                                   "Internal error" in error_msg)

                    if is_retryable and attempt < max_retries - 1:
                        print(f"⚠️  Gemini API 에러 발생: {error_msg}")
                        print(f"🔄 {retry_delay}초 후 재시도... (시도 {attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                    else:
                        # 마지막 시도이거나 재시도 불가능한 에러
                        if attempt == max_retries - 1:
                            print(f"❌ 최대 재시도 횟수 도달 ({max_retries}번)")
                        raise

            # 모든 재시도 실패 시
            if response is None:
                if last_error:
                    raise last_error
                else:
                    raise Exception("Gemini API 요청 실패: 응답을 받지 못했습니다")

            # response.candidates가 비어있는 경우 처리 (안전 필터 차단 등)
            if not response.candidates or len(response.candidates) == 0:
                error_msg = "Gemini API가 빈 응답을 반환했습니다 (안전 필터 또는 콘텐츠 정책 위반 가능성)"
                print(f"⚠️  {error_msg}")
                
                # prompt_feedback 확인
                if hasattr(response, 'prompt_feedback'):
                    feedback = response.prompt_feedback
                    if hasattr(feedback, 'block_reason'):
                        block_reason_map = {
                            1: "BLOCK_REASON_UNSPECIFIED",
                            2: "SAFETY",
                            3: "OTHER"
                        }
                        block_reason = block_reason_map.get(feedback.block_reason, f"UNKNOWN({feedback.block_reason})")
                        print(f"🚫 차단 이유: {block_reason}")
                    
                    if hasattr(feedback, 'safety_ratings') and feedback.safety_ratings:
                        print("🛡️ 안전 필터 평가 (프롬프트):")
                        for rating in feedback.safety_ratings:
                            print(f"   - {rating.category}: {rating.probability}")
                
                raise Exception(error_msg)

            # finish_reason 확인
            if response.candidates:
                candidate = response.candidates[0]
                finish_reason = candidate.finish_reason

                finish_reason_map = {
                    1: "STOP (정상 완료)",
                    2: "MAX_TOKENS (최대 토큰 도달)",
                    3: "SAFETY (안전 필터 발동)",
                    4: "RECITATION (인용 감지)",
                    5: "OTHER (기타 이유)",
                    8: "BLOCKLIST (차단 목록)"
                }

                finish_reason_text = finish_reason_map.get(finish_reason, f"UNKNOWN ({finish_reason})")

                if finish_reason != 1:
                    error_msg = f"Gemini API 응답 실패: finish_reason={finish_reason} ({finish_reason_text})"
                    print(f"❌ {error_msg}")

                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        print("🛡️ 안전 필터 평가:")
                        for rating in candidate.safety_ratings:
                            print(f"   - {rating.category}: {rating.probability}")

                    raise Exception(error_msg)

            # 토큰 사용량 및 비용 계산
            usage_metadata = response.usage_metadata
            if usage_metadata:
                input_tokens = usage_metadata.prompt_token_count or 0
                output_tokens = usage_metadata.candidates_token_count or 0
                total_tokens = usage_metadata.total_token_count or 0

                # Gemini 2.0 Flash 가격
                INPUT_PRICE_PER_1M = 0.0
                OUTPUT_PRICE_PER_1M = 0.0

                input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M
                output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
                total_cost = input_cost + output_cost

                print("📥 Gemini API 응답 완료")
                print(f"⏱️  응답 시간: {request_duration:.2f}초")
                print(f"🔍 응답 길이: {len(response.text)}자")
                print("\n💰 토큰 사용량:")
                print(f"  📤 Input tokens: {input_tokens:,}")
                print(f"  📥 Output tokens: {output_tokens:,}")
                print(f"  📊 Total tokens: {total_tokens:,}")
            else:
                print("📥 Gemini API 응답 완료")
                print(f"⏱️  응답 시간: {request_duration:.2f}초")
                print(f"🔍 응답 길이: {len(response.text)}자")

            # 응답 파싱
            result = self._parse_response(response.text, image_metadata)

            print("✅ 이미지 분석 완료")
            return result

        except Exception as e:
            print(f"❌ 이미지 분석 실패: {e}")
            raise Exception(f"이미지 분석에 실패했습니다: {str(e)}")

    def _parse_response(
        self,
        response_text: str,
        image_metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Gemini 응답 파싱

        Args:
            response_text: Gemini API 응답 텍스트
            image_metadata: 이미지 메타데이터

        Returns:
            파싱된 결과 딕셔너리
        """
        try:
            # 코드블록 제거
            cleaned_text = response_text.replace("```json", "").replace("```", "")

            # JSON 추출
            start_idx = cleaned_text.find("{")
            end_idx = cleaned_text.rfind("}")

            if start_idx == -1 or end_idx == -1:
                raise ValueError("JSON을 찾을 수 없습니다.")

            json_string = cleaned_text[start_idx:end_idx + 1]

            # 파싱
            analysis_result = json.loads(json_string)

            # category_info는 이제 딕셔너리 형태 (LocationCategory, EraCategory)
            # Gemini가 직접 class 번호를 반환하므로 추가 처리 불필요
            category_info = analysis_result.get("category_info", {})

            # 최종 결과 구성
            result = {
                "meta": analysis_result.get("meta", {}),
                "category_info": category_info,
                "annotation_info": analysis_result.get("annotation_info", {})
            }

            # start_time 소수점 2자리로 후처리 (있는 경우만)
            if "start_time" in result["meta"]:
                result["meta"]["start_time"] = round(result["meta"]["start_time"], 2)

            return result

        except json.JSONDecodeError as e:
            print(f"❌ JSON 파싱 실패: {e}")
            print(f"원본 응답: {response_text}")
            raise ValueError("API 응답을 파싱할 수 없습니다")


# 테스트용
if __name__ == "__main__":
    import asyncio
    import os

    async def main():
        # API 키
        api_key = os.getenv("GOOGLE_API_KEY")

        analyzer = GeminiImageAnalyzer(api_key=api_key)

        # 테스트 이미지 경로 (사용자가 제공)
        image_path = "test_image.jpg"

        if not os.path.exists(image_path):
            print(f"❌ 테스트 이미지를 찾을 수 없습니다: {image_path}")
            return

        # 메타데이터 추출
        from image_metadata import extract_image_metadata
        metadata = extract_image_metadata(image_path)

        result = await analyzer.analyze_image(
            file_path=image_path,
            mime_type="image/jpeg",
            image_metadata=metadata
        )

        print("\n" + "="*80)
        print("📊 분석 결과:")
        print("="*80)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    asyncio.run(main())
