"""
배경 이미지 분석기 - Streamlit 앱
Google Gemini를 사용하여 한국적 배경 이미지를 분석하고 설명문을 생성합니다.
"""

import streamlit as st
import json
import os
from pathlib import Path
from datetime import datetime
from PIL import Image
import asyncio
from dotenv import load_dotenv

# raw_image25 모듈 import
from lib.gemini_analyzer import GeminiImageAnalyzer
from lib.gemini_prompt import get_image_analysis_prompt
from lib.categories import CATEGORY_DATA, CATEGORY_LABELS

# 환경 변수 로드
load_dotenv()

# 페이지 설정
st.set_page_config(
    page_title="배경 이미지 분석기",
    page_icon="🖼️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 커스텀 CSS
st.markdown("""
<style>
    /* 메인 헤더 스타일 */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1.5rem 0;
        margin-bottom: 2rem;
    }
    
    /* 서브헤더 스타일 */
    .sub-header {
        color: #4a5568;
        font-size: 1.1rem;
        text-align: center;
        margin-top: -1.5rem;
        margin-bottom: 2rem;
    }
    
    /* 탭 스타일링 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        border-bottom: 2px solid #e2e8f0;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 24px;
        padding-right: 24px;
        background-color: white;
        border-radius: 12px 12px 0px 0px;
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    /* 컨테이너 스타일 */
    div[data-testid="stContainer"] {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    /* 메트릭 카드 스타일 */
    div[data-testid="metric-container"] {
        background-color: #f7fafc;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
    }
    
    /* 버튼 호버 효과 */
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        transition: all 0.3s ease;
    }
    
    /* Success/Error 메시지 스타일 */
    .stSuccess, .stError, .stWarning, .stInfo {
        border-radius: 8px;
        padding: 1rem;
    }
    
    /* 파일 업로더 스타일 */
    .stFileUploader > div {
        border-radius: 8px;
    }
    
    /* Expander 스타일 */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

# 세션 상태 초기화
if 'analysis_result' not in st.session_state:
    st.session_state['analysis_result'] = None
if 'uploaded_image' not in st.session_state:
    st.session_state['uploaded_image'] = None
if 'analysis_status' not in st.session_state:
    st.session_state['analysis_status'] = 'waiting'  # waiting, analyzing, completed


def extract_user_editable_prompt() -> str:
    """
    사용자가 편집 가능한 프롬프트 부분 추출
    (metadata_section, categories_text 제외)
    """
    # 기본 프롬프트 템플릿 (플레이스홀더 포함)
    base_prompt = """
이미지를 분석하여 다음 정보를 JSON으로 제공하세요:

{metadata_section}

## 분석 단계

### 1단계: 카테고리 분류 (category_info)

이미지를 보고 아래 카테고리에서 가장 적합한 label을 정확히 선택하세요:
{categories_text}

**카테고리 분류 규칙:**

1. **LocationCategory (장소 구분)**
   - 실내(1): 건물 내부, 방, 실내 공간
   - 실외(2): 야외, 자연, 거리, 건물 외부
   - 혼합(3): 실내와 실외가 함께 보이는 경우

2. **EraCategory (시대 구분)**
   - 전통(1): 한옥, 전통 의상, 전통 건축물, 옛날 분위기
   - 현대(2): 현대 건물, 현대 의상, 현대 도시, 최신 시설
   - 혼합(3): 전통과 현대가 섞여 있는 경우
   - 기타(4): 위 분류가 애매하거나 판단하기 어려운 경우


### 2단계: 설명문 작성 (annotation_info)

**전달하는 이미지를 생성하기 위한 INPUT 설명문을 아래 기준을 참고해서 만들어주세요.**

#### 총 5문장 작성:

1. **정경 설명 (SceneExp)**
   - 장소, 환경, 분위기를 묘사
   - 종결 어미: **~장면이다.**
   - 예시: "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다."

2. **색감 설명 (ColortoneExp)**
   - 이미지에서 느껴지는 색채의 조화, 명암, 톤을 서술
   - 종결 어미: **~색감이다.**
   - 예시: "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다."

3. **구도 설명 (CompositionExp)**
   - 카메라의 시점·각도·원근감·배치를 설명
   - 종결 어미: **~구도이다.**
   - 예시: "높은 시점에서 내려다보는 항공 구도이다."

4. **객체1 설명 (ObjectExp1)**
   - 이미지에서 중점적인 객체에 대한 설명 구체적인 생김새, 형태 묘사
   - **객체가 사람인 경우 수 표현 규칙:**
     - 1-4명: 정확한 수 명시 (한 명, 두 명, 세 명, 네 명)
     - 5명 이상 또는 불명확: "여러 명", "다수의", "몇몇" 등 사용
   - 객체가 사물인 경우 표면적 느낌도 같이 설명
   - 종결 어미: **~다.**
   - 예시:
"크고 둥근 북의 표면은 미색의 팽팽한 가죽 질감을 드러내고 있으며, 받침대에는 단청 문양이 화려하게 칠해져 있다."
"붉은색 관복을 입고 검은색 사모를 쓴 한 명의 인물이 흰 장갑을 낀 채 북채를 높이 들어 곧 북을 치려는 역동적인 동작을 취하고 있다."
"녹색으로 채색된 창호문은 전통 문양의 격자 창살이 섬세하게 짜여 있으며, 매끄러운 목재 표면과 복잡한 패턴을 동시에 드러낸다."

5. **객체2 설명 (ObjectExp2)**
   - 이미지에서 중점적인 또 다른 객체에 대한 설명 구체적인 생김새, 형태 묘사
   - **객체가 사람인 경우 수 표현 규칙:**
     - 1-4명: 정확한 수 명시 (한 명, 두 명, 세 명, 네 명)
     - 5명 이상 또는 불명확: "여러 명", "다수의", "몇몇" 등 사용
   - 객체가 사물인 경우 표면적 느낌도 같이 설명
   - 종결 어미: **~다.**
   - 예시:
"크고 둥근 북의 표면은 미색의 팽팽한 가죽 질감을 드러내고 있으며, 받침대에는 단청 문양이 화려하게 칠해져 있다."
"붉은색 관복을 입고 검은색 사모를 쓴 한 명의 인물이 흰 장갑을 낀 채 북채를 높이 들어 곧 북을 치려는 역동적인 동작을 취하고 있다."
"녹색으로 채색된 창호문은 전통 문양의 격자 창살이 섬세하게 짜여 있으며, 매끄러운 목재 표면과 복잡한 패턴을 동시에 드러낸다."

#### 주의사항:

1. **객체 중복 금지**
   - 객체1과 객체2는 서로 다른 객체를 설명해야 함
   - 예: 객체1에서 "사람들"을 설명했으면, 객체2는 "건물" 등 다른 객체

2. **내용 중복 금지**
   - 5문장을 합쳐 한 문단으로 보고, 각 설명문에 포함되어야 할 내용을 중복 사용하지 말 것
   - 정경 설명에서 언급한 내용을 색감 설명에서 반복하지 말 것

3. **자막 내용 제외**
   - 이미지에 자막이나 텍스트가 있어도 그 내용은 설명문에 포함하지 말 것

4. **간결하고 명료하게**
   - 문장은 수식어가 너무 많지 않고 간단 명료하게 작성
   - 객체 설명문 1개당 1개의 객체에 대해서만 설명

5. **사람 수 표현 규칙 (매우 중요!)**
   - **1-4명인 경우**: 이미지를 자세히 보고 정확한 수를 세어 명시
     - 올바른 예: "세 명의 손님들이 카운터에 앉아 있다" (실제 3명)
     - 잘못된 예: "두 명의 손님들이 앉아 있다" (실제 3명인데 2명으로 잘못 셈)
   - **5명 이상이거나 정확히 세기 어려운 경우**: "여러 명", "다수의", "몇몇" 등 사용
     - 올바른 예: "여러 명의 여성들이 요트 위에서 포즈를 취하고 있다" (5명 이상)
     - 잘못된 예: "여섯 명의 여성들이..." (실제로는 5명인데 6명으로 잘못 셈)
   - **배경에 있거나 부분적으로 가려진 사람은 세지 않음**

6. **총 50어절 이상 (필수!)**
   - 5개 설명문을 모두 합쳤을 때 총 어절 수가 50어절 이상이어야 함
   - 어절은 띄어쓰기로 구분되는 단위
   - 예: "저는 오늘 사과를 먹었습니다." → 4어절 (저는 | 오늘 | 사과를 | 먹었습니다.)

#### 어절 수 검증 규칙:

**어절 정의:**
- 어절은 띄어쓰기로 구분되는 단위입니다.

**필수 조건:**
- **5개 문장의 총 어절 수 ≥ 50어절**

**검증 절차:**
1. 5개 description을 모두 작성
2. 각 문장의 어절 수 계산 (띄어쓰기 기준)
3. 총 어절 수 합산
4. **총 어절 수 < 50** → 각 문장에 구체적인 세부 묘사 추가

**어절 부족 시 보완 방법:**

**우선순위: 정경 > 객체1, 객체2 > 색감, 구도 순서로 구체화**

1. **정경 (SceneExp) - 우선 보완**
   - 부족: "해변과 건물이 보이는 장면이다." (5어절)
   - 충분: "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다." (18어절)

2. **객체1, 객체2 - 다음 보완**
   - 부족: "사람들이 걷고 있다." (3어절)
   - 충분: "해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다." (9어절)

3. **색감, 구도 - 간결하게 유지**
   - 색감: "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다." (8어절)
   - 구도: "높은 시점에서 내려다보는 항공 구도이다." (6어절)

**좋은 예시 1: 해변 풍경 (총 어절 수 51개)**
1. SceneExp: "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다." (18어절)
2. ColortoneExp: "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다." (8어절)
3. CompositionExp: "높은 시점에서 내려다보는 항공 구도이다." (6어절)
4. ObjectExp1: "해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다." (9어절)
5. ObjectExp2: "유리 외벽이 반짝이는 고층 건물들이 빽빽하게 늘어서 있다." (10어절)

**총 어절 수: 51어절  (50어절 이상 충족)**

**좋은 예시 2: 레스토랑 장면 (사람 수 1-4명은 정확히 명시)**
1. SceneExp: "실내 레스토랑에서 한 명의 셰프가 큰 철판 위에서 요리하고 있으며, 손님들이 이를 지켜보는 활기찬 장면이다." (17어절)
2. ColortoneExp: "전반적으로 밝은 조명 아래 따뜻한 나무색과 시원한 푸른빛이 조화로운 색감이다." (12어절)
3. CompositionExp: "낮은 시점에서 셰프와 손님들을 올려다보는 구도이다." (8어절)
4. ObjectExp1: "흰색 조리복과 마스크를 착용한 한 명의 셰프가 철판 위에서 능숙하게 요리하고 있다." (13어절)
5. ObjectExp2: "세 명의 손님들이 카운터에 앉아 셰프의 요리 과정을 흥미롭게 지켜보고 있다." (12어절)

**총 어절 수: 62어절  (50어절 이상 충족, 1-4명은 정확한 수 명시)**

**좋은 예시 3: 요트 장면 (5명 이상은 "여러 명" 사용)**
1. SceneExp: "푸른 하늘과 바다를 배경으로 여러 명의 여성들이 요트 위에서 즐거운 시간을 보내는 활기찬 장면이다." (17어절)
2. ColortoneExp: "맑고 청량한 푸른색과 인물들의 다채로운 의상 색깔이 어우러져 밝고 생동감 있는 색감이다." (13어절)
3. CompositionExp: "요트의 앞부분에서 인물들을 중심으로 약간 낮은 시점에서 넓게 담아낸 구도이다." (13어절)
4. ObjectExp1: "여러 명의 여성들이 요트 위에 앉거나 서서 카메라를 향해 밝게 웃으며 포즈를 취하고 있다." (16어절)
5. ObjectExp2: "배경에는 푸른 바다 위로 길게 뻗은 다리가 보이며, 요트의 돛대가 하늘을 향해 높이 솟아 있다." (18어절)

**총 어절 수: 77어절  (50어절 이상 충족, 5명 이상은 "여러 명" 사용)**


## 최종 출력 전 필수 검증

**자동 계산 검증:**
1.  이미지 메타데이터가 정확히 입력되었는가?
   - width, height, format 확인

**논리적 검증:**
1.  category_info의 LocationCategory와 EraCategory가 정확히 선택되었는가?
   - 이미지 내용과 일치하는지 확인

2.  annotation_info의 5개 설명문이 모두 작성되었는가?
   - SceneExp, ColortoneExp, CompositionExp, ObjectExp1, ObjectExp2

3.  객체1과 객체2가 중복되지 않는가?

4.  총 어절 수가 50어절 이상인가?
   - 5개 문장의 description을 모두 합쳐 띄어쓰기 기준으로 어절 수 계산
   - 총 어절 수 < 50 → 각 문장에 구체적 세부 묘사 추가 후 다시 계산
   - 총 어절 수 ≥ 50 → 통과

5.  Explanation이 5개 문장을 순서대로 합친 것인가?
   - SceneExp + ColortoneExp + CompositionExp + ObjectExp1 + ObjectExp2

**위 검증을 통과하지 못하면 처음부터 다시 분석!**


## 출력 형식

**중요:**
1. 모든 메타데이터 값은 제공된 값 그대로 사용
2. 아래 예시는 샘플이며, 반드시 실제 분석 결과로 교체
3. category_info는 딕셔너리 형태로 LocationCategory와 EraCategory의 class 번호만 출력

{{
  "meta": {{
    "width": [자동 생성],
    "height": [자동 생성],
    "format": "[자동 생성]"
  }},
  "category_info": {{
    "LocationCategory": 2,
    "EraCategory": 2
  }},
  "annotation_info": {{
    "SceneExp": "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다.",
    "ColortoneExp": "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다.",
    "CompositionExp": "높은 시점에서 내려다보는 항공 구도이다.",
    "ObjectExp1": "해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다.",
    "ObjectExp2": "유리 외벽이 반짝이는 고층 건물들이 빽빽하게 늘어서 있다.",
    "Explanation": "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다. 밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다. 높은 시점에서 내려다보는 항공 구도이다. 해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다. 유리 외벽이 반짝이는 고층 건물들이 빽빽하게 늘어서 있다."
  }}
}}
"""
    return base_prompt.strip()


def build_full_prompt(user_prompt: str, image_metadata: dict) -> str:
    """
    사용자가 편집한 프롬프트 + 시스템 자동 생성 섹션을 결합
    """
    # 1. 메타데이터 섹션 생성
    metadata_section = f"""
## 이미지 메타데이터 (정확한 정보 - 반드시 사용)
**이 정보는 실제 이미지에서 추출한 정확한 값입니다. 추측하지 말고 아래 값을 그대로 사용하세요:**
- **이미지 해상도**: {image_metadata['width']} × {image_metadata['height']} 픽셀
- **이미지 포맷**: {image_metadata['format']}
- **파일 크기**: {image_metadata['file_size']} bytes

**중요: 위 값들은 절대 변경하거나 추측하지 마세요. JSON 출력 시 그대로 사용하세요.**
"""

    # 2. 카테고리 텍스트 생성
    categories_text = ""
    for key, items in CATEGORY_DATA.items():
        korean_name = CATEGORY_LABELS.get(key, key)
        labels = ", ".join([f"{item['label']}({item['class']})" for item in items])
        categories_text += f"- **{key}** ({korean_name}): {labels}\n"

    # 3. 플레이스홀더 교체
    full_prompt = user_prompt.replace("{metadata_section}", metadata_section.strip())
    full_prompt = full_prompt.replace("{categories_text}", categories_text.strip())

    return full_prompt


async def analyze_image_async(image_path: str, mime_type: str, image_metadata: dict, api_key: str, user_prompt: str):
    """
    이미지 분석 실행 (비동기)
    """
    # GeminiImageAnalyzer 인스턴스 생성
    analyzer = GeminiImageAnalyzer(api_key=api_key)

    # 완전한 프롬프트 생성 (사용자 편집 + 시스템 자동 생성)
    full_prompt = build_full_prompt(user_prompt, image_metadata)

    # 프롬프트를 analyzer의 기본 프롬프트로 덮어쓰기
    import google.generativeai as genai

    # API 설정
    genai.configure(api_key=api_key)

    # Safety Settings
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={
            "temperature": 0,
            "top_p": 1,
            "top_k": 1,
            "max_output_tokens": 65536,
            "response_mime_type": "application/json",
        },
        safety_settings=safety_settings
    )

    # 이미지 읽기
    image_data = Image.open(image_path)

    # API 호출
    response = await asyncio.to_thread(
        model.generate_content,
        [full_prompt, image_data]
    )

    # 응답 파싱
    result = json.loads(response.text)

    return result


# API 키 로드
api_key = os.getenv('GOOGLE_API_KEY_IMAGE', '')

# Streamlit Cloud에서는 secrets 사용
try:
    if 'GOOGLE_API_KEY_IMAGE' in st.secrets:
        api_key = st.secrets['GOOGLE_API_KEY_IMAGE']
except (FileNotFoundError, AttributeError):
    pass

# 헤더
st.markdown('<h1 class="main-header">배경 이미지 분석기</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Google Gemini로 한국적 배경 이미지를 분석하고 설명문을 생성합니다</p>', unsafe_allow_html=True)

# API 키 상태 표시
if not api_key:
    st.error("⚠️ API 키를 .env 파일에 설정하세요 (GOOGLE_API_KEY_IMAGE)")
    st.stop()

# 상태 메트릭 표시
col1, col2, col3, col4 = st.columns(4)

with col1:
    status_icon = "✅" if api_key else "❌"
    st.metric("API 연결", status_icon, delta="Ready" if api_key else "Not Ready")

with col2:
    img_status = "✅ 로드됨" if st.session_state.get('uploaded_image') else "⏳ 대기중"
    st.metric("이미지", img_status)

with col3:
    if st.session_state['analysis_status'] == 'analyzing':
        analysis_status = "🔄 분석중"
    elif st.session_state['analysis_status'] == 'completed':
        analysis_status = "✅ 완료"
    else:
        analysis_status = "⏳ 대기중"
    st.metric("분석 상태", analysis_status)

with col4:
    if st.session_state.get('analysis_result'):
        result_count = len(st.session_state['analysis_result'].get('annotation_info', {}))
        st.metric("결과", f"📊 {result_count}개 항목")
    else:
        st.metric("결과", "- 없음")

st.markdown("---")

# 메인 탭
tab1, tab2, tab3 = st.tabs(["📝 분석 설정", "📊 분석 결과", "💾 JSON 출력"])

with tab1:
    col1, col2 = st.columns([3, 2], gap="large")
    
    with col1:
        # 이미지 업로드 섹션
        with st.container(border=True):
            st.markdown("### 📸 이미지 업로드")
            
            uploaded_file = st.file_uploader(
                "배경 이미지를 선택하세요",
                type=['jpg', 'jpeg', 'png', 'webp'],
                help="JPG, PNG, WEBP 형식 지원 (최대 20MB)"
            )
            
            if uploaded_file:
                # 이미지 저장 (임시 파일)
                temp_dir = Path("temp_images")
                temp_dir.mkdir(exist_ok=True)
                
                temp_image_path = temp_dir / uploaded_file.name
                with open(temp_image_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                
                # 이미지 메타데이터 추출
                image = Image.open(temp_image_path)
                image_metadata = {
                    'width': image.width,
                    'height': image.height,
                    'format': image.format,
                    'file_size': temp_image_path.stat().st_size
                }
                
                st.session_state['uploaded_image'] = {
                    'path': str(temp_image_path),
                    'metadata': image_metadata,
                    'mime_type': f"image/{image.format.lower()}"
                }
                
                # 이미지 미리보기
                st.image(image, caption="업로드된 이미지", use_container_width=True)
    
    with col2:
        # 이미지 정보 패널
        with st.container(border=True):
            st.markdown("### 📊 이미지 정보")
            
            if st.session_state.get('uploaded_image'):
                metadata = st.session_state['uploaded_image']['metadata']
                
                # 메트릭으로 표시
                st.metric("해상도", f"{metadata['width']} × {metadata['height']} px")
                st.metric("형식", metadata['format'])
                st.metric("파일 크기", f"{metadata['file_size']:,} bytes")
                
                # 추가 정보
                st.info(f"""
                **파일명**: {uploaded_file.name}  
                **MIME 타입**: {st.session_state['uploaded_image']['mime_type']}
                """)
            else:
                st.info("이미지를 업로드하면 정보가 표시됩니다")
    
    # 프롬프트 편집 섹션
    with st.container(border=True):
        st.markdown("### ⚙️ 프롬프트 설정")
        
        # 안내 메시지
        with st.expander("ℹ️ 프롬프트 편집 가이드", expanded=False):
            st.warning("""
            **다음 플레이스홀더는 자동으로 대체됩니다:**
            - `{metadata_section}` → 이미지 메타데이터
            - `{categories_text}` → 카테고리 정보
            
            이 플레이스홀더는 삭제하지 마세요!
            """)
        
        # 기본 프롬프트 로드
        default_prompt = extract_user_editable_prompt()
        
        user_prompt = st.text_area(
            "프롬프트를 수정할 수 있습니다",
            value=default_prompt,
            height=400,
            help="프롬프트 내 {metadata_section}, {categories_text}는 자동 생성됩니다"
        )
        
        # 플레이스홀더 검증
        placeholder_valid = "{metadata_section}" in user_prompt and "{categories_text}" in user_prompt
        
        if not placeholder_valid:
            st.error("⚠️ 필수 플레이스홀더가 제거되었습니다! 복구하세요.")
    
    # 분석 시작 버튼
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        analyze_button = st.button(
            "🚀 **분석 시작**",
            type="primary",
            use_container_width=True,
            disabled=not (uploaded_file and api_key and placeholder_valid)
        )
        
        if analyze_button:
            if not uploaded_file:
                st.error("❌ 이미지를 먼저 업로드하세요")
            elif not placeholder_valid:
                st.error("❌ 필수 플레이스홀더를 복구하세요")
            else:
                st.session_state['analysis_status'] = 'analyzing'
                
                with st.spinner("🔄 이미지를 분석하고 있습니다... (약 10-30초 소요)"):
                    try:
                        # 비동기 분석 실행
                        result = asyncio.run(
                            analyze_image_async(
                                st.session_state['uploaded_image']['path'],
                                st.session_state['uploaded_image']['mime_type'],
                                st.session_state['uploaded_image']['metadata'],
                                api_key,
                                user_prompt
                            )
                        )
                        
                        st.session_state['analysis_result'] = result
                        st.session_state['analysis_status'] = 'completed'
                        st.success("✅ 분석이 완료되었습니다! '분석 결과' 탭을 확인하세요.")
                        st.balloons()
                        
                    except Exception as e:
                        st.session_state['analysis_status'] = 'waiting'
                        st.error(f"❌ 분석 중 오류가 발생했습니다: {str(e)}")
                        
                        with st.expander("🔍 상세 오류 정보"):
                            import traceback
                            st.code(traceback.format_exc())

with tab2:
    if st.session_state.get('analysis_result'):
        result = st.session_state['analysis_result']
        
        # 메인 설명문
        with st.container(border=True):
            st.markdown("### 📄 통합 설명문")
            if 'annotation_info' in result and 'Explanation' in result['annotation_info']:
                st.markdown(f"**{result['annotation_info']['Explanation']}**")
        
        # 2개 컬럼으로 정보 표시
        col1, col2 = st.columns(2)
        
        with col1:
            # 카테고리 정보
            with st.container(border=True):
                st.markdown("### 🏷️ 카테고리 분류")
                
                if 'category_info' in result:
                    category_info = result['category_info']
                    
                    # LocationCategory
                    loc_cat = category_info.get('LocationCategory', 'N/A')
                    loc_labels = {1: "실내", 2: "실외", 3: "혼합"}
                    loc_label = loc_labels.get(loc_cat, "알 수 없음")
                    
                    # EraCategory
                    era_cat = category_info.get('EraCategory', 'N/A')
                    era_labels = {1: "전통", 2: "현대", 3: "혼합", 4: "기타"}
                    era_label = era_labels.get(era_cat, "알 수 없음")
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("장소 구분", f"{loc_label}")
                    with col_b:
                        st.metric("시대 구분", f"{era_label}")
        
        with col2:
            # 메타데이터
            with st.container(border=True):
                st.markdown("### 📋 메타데이터")
                
                if 'meta' in result:
                    meta = result['meta']
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        st.metric("너비", f"{meta.get('width', 'N/A')} px")
                    with col_b:
                        st.metric("높이", f"{meta.get('height', 'N/A')} px")
                    with col_c:
                        st.metric("형식", meta.get('format', 'N/A'))
        
        # 상세 설명문
        with st.container(border=True):
            st.markdown("### ✍️ 상세 설명문")
            
            if 'annotation_info' in result:
                ann_info = result['annotation_info']
                
                # Expander로 각 설명 표시
                with st.expander("🎬 정경 설명 (SceneExp)", expanded=True):
                    st.write(ann_info.get('SceneExp', 'N/A'))
                
                with st.expander("🎨 색감 설명 (ColortoneExp)", expanded=True):
                    st.write(ann_info.get('ColortoneExp', 'N/A'))
                
                with st.expander("📐 구도 설명 (CompositionExp)", expanded=True):
                    st.write(ann_info.get('CompositionExp', 'N/A'))
                
                with st.expander("👤 객체1 설명 (ObjectExp1)", expanded=True):
                    st.write(ann_info.get('ObjectExp1', 'N/A'))
                
                with st.expander("🏛️ 객체2 설명 (ObjectExp2)", expanded=True):
                    st.write(ann_info.get('ObjectExp2', 'N/A'))
        
    else:
        # Empty state
        st.info("📝 아직 분석 결과가 없습니다. '분석 설정' 탭에서 이미지를 업로드하고 분석을 시작하세요.")

with tab3:
    if st.session_state.get('analysis_result'):
        result = st.session_state['analysis_result']
        
        # JSON 다운로드 버튼
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            json_str = json.dumps(result, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 **JSON 파일 다운로드**",
                data=json_str,
                file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
                type="primary"
            )
        
        # JSON 미리보기
        with st.container(border=True):
            st.markdown("### 📋 JSON 데이터 미리보기")
            
            # JSON을 예쁘게 표시
            st.json(result, expanded=True)
            
            # 복사 가능한 텍스트 영역
            with st.expander("📝 복사 가능한 JSON 텍스트"):
                st.code(json_str, language="json")
                
                # 어절 수 계산 (참고용)
                if 'annotation_info' in result:
                    ann = result['annotation_info']
                    total_words = sum([
                        len(ann.get(key, '').split()) 
                        for key in ['SceneExp', 'ColortoneExp', 'CompositionExp', 'ObjectExp1', 'ObjectExp2']
                    ])
                    st.info(f"📊 총 어절 수: {total_words}개")
    else:
        # Empty state
        st.info("📝 분석 결과가 없습니다. 먼저 이미지를 분석해주세요.")

# 푸터
# st.markdown("---")
# st.markdown(
#     """
#     <div style='text-align: center; color: #718096; font-size: 0.9rem;'>
#         📧 문의사항이 있으시면 관리자에게 연락해주세요
#     </div>
#     """,
#     unsafe_allow_html=True
# )



# """
# 배경 이미지 분석기 - Streamlit 앱
# Google Gemini를 사용하여 한국적 배경 이미지를 분석하고 설명문을 생성합니다.
# """

# import streamlit as st
# import json
# import os
# from pathlib import Path
# from datetime import datetime
# from PIL import Image
# import asyncio
# from dotenv import load_dotenv

# # raw_image25 모듈 import
# from lib.gemini_analyzer import GeminiImageAnalyzer
# from lib.gemini_prompt import get_image_analysis_prompt
# from lib.categories import CATEGORY_DATA, CATEGORY_LABELS

# # 환경 변수 로드
# load_dotenv()

# # 페이지 설정
# st.set_page_config(
#     page_title="배경 이미지 분석기",
#     page_icon="🖼️",
#     layout="wide"
# )

# # 세션 상태 초기화
# if 'analysis_result' not in st.session_state:
#     st.session_state['analysis_result'] = None
# if 'uploaded_image' not in st.session_state:
#     st.session_state['uploaded_image'] = None


# def extract_user_editable_prompt() -> str:
#     """
#     사용자가 편집 가능한 프롬프트 부분 추출
#     (metadata_section, categories_text 제외)
#     """
#     # 기본 프롬프트 템플릿 (플레이스홀더 포함)
#     base_prompt = """
# 이미지를 분석하여 다음 정보를 JSON으로 제공하세요:

# {metadata_section}

# ## 분석 단계

# ### 1단계: 카테고리 분류 (category_info)

# 이미지를 보고 아래 카테고리에서 가장 적합한 label을 정확히 선택하세요:
# {categories_text}

# **카테고리 분류 규칙:**

# 1. **LocationCategory (장소 구분)**
#    - 실내(1): 건물 내부, 방, 실내 공간
#    - 실외(2): 야외, 자연, 거리, 건물 외부
#    - 혼합(3): 실내와 실외가 함께 보이는 경우

# 2. **EraCategory (시대 구분)**
#    - 전통(1): 한옥, 전통 의상, 전통 건축물, 옛날 분위기
#    - 현대(2): 현대 건물, 현대 의상, 현대 도시, 최신 시설
#    - 혼합(3): 전통과 현대가 섞여 있는 경우
#    - 기타(4): 위 분류가 애매하거나 판단하기 어려운 경우


# ### 2단계: 설명문 작성 (annotation_info)

# **전달하는 이미지를 생성하기 위한 INPUT 설명문을 아래 기준을 참고해서 만들어주세요.**

# #### 총 5문장 작성:

# 1. **정경 설명 (SceneExp)**
#    - 장소, 환경, 분위기를 묘사
#    - 종결 어미: **~장면이다.**
#    - 예시: "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다."

# 2. **색감 설명 (ColortoneExp)**
#    - 이미지에서 느껴지는 색채의 조화, 명암, 톤을 서술
#    - 종결 어미: **~색감이다.**
#    - 예시: "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다."

# 3. **구도 설명 (CompositionExp)**
#    - 카메라의 시점·각도·원근감·배치를 설명
#    - 종결 어미: **~구도이다.**
#    - 예시: "높은 시점에서 내려다보는 항공 구도이다."

# 4. **객체1 설명 (ObjectExp1)**
#    - 이미지에서 중점적인 객체에 대한 설명 구체적인 생김새, 형태 묘사
#    - **객체가 사람인 경우 수 표현 규칙:**
#      - 1-4명: 정확한 수 명시 (한 명, 두 명, 세 명, 네 명)
#      - 5명 이상 또는 불명확: "여러 명", "다수의", "몇몇" 등 사용
#    - 객체가 사물인 경우 표면적 느낌도 같이 설명
#    - 종결 어미: **~다.**
#    - 예시:
# "크고 둥근 북의 표면은 미색의 팽팽한 가죽 질감을 드러내고 있으며, 받침대에는 단청 문양이 화려하게 칠해져 있다."
# "붉은색 관복을 입고 검은색 사모를 쓴 한 명의 인물이 흰 장갑을 낀 채 북채를 높이 들어 곧 북을 치려는 역동적인 동작을 취하고 있다."
# "녹색으로 채색된 창호문은 전통 문양의 격자 창살이 섬세하게 짜여 있으며, 매끄러운 목재 표면과 복잡한 패턴을 동시에 드러낸다."

# 5. **객체2 설명 (ObjectExp2)**
#    - 이미지에서 중점적인 또 다른 객체에 대한 설명 구체적인 생김새, 형태 묘사
#    - **객체가 사람인 경우 수 표현 규칙:**
#      - 1-4명: 정확한 수 명시 (한 명, 두 명, 세 명, 네 명)
#      - 5명 이상 또는 불명확: "여러 명", "다수의", "몇몇" 등 사용
#    - 객체가 사물인 경우 표면적 느낌도 같이 설명
#    - 종결 어미: **~다.**
#    - 예시:
# "크고 둥근 북의 표면은 미색의 팽팽한 가죽 질감을 드러내고 있으며, 받침대에는 단청 문양이 화려하게 칠해져 있다."
# "붉은색 관복을 입고 검은색 사모를 쓴 한 명의 인물이 흰 장갑을 낀 채 북채를 높이 들어 곧 북을 치려는 역동적인 동작을 취하고 있다."
# "녹색으로 채색된 창호문은 전통 문양의 격자 창살이 섬세하게 짜여 있으며, 매끄러운 목재 표면과 복잡한 패턴을 동시에 드러낸다."

# #### 주의사항:

# 1. **객체 중복 금지**
#    - 객체1과 객체2는 서로 다른 객체를 설명해야 함
#    - 예: 객체1에서 "사람들"을 설명했으면, 객체2는 "건물" 등 다른 객체

# 2. **내용 중복 금지**
#    - 5문장을 합쳐 한 문단으로 보고, 각 설명문에 포함되어야 할 내용을 중복 사용하지 말 것
#    - 정경 설명에서 언급한 내용을 색감 설명에서 반복하지 말 것

# 3. **자막 내용 제외**
#    - 이미지에 자막이나 텍스트가 있어도 그 내용은 설명문에 포함하지 말 것

# 4. **간결하고 명료하게**
#    - 문장은 수식어가 너무 많지 않고 간단 명료하게 작성
#    - 객체 설명문 1개당 1개의 객체에 대해서만 설명

# 5. **사람 수 표현 규칙 (매우 중요!)**
#    - **1-4명인 경우**: 이미지를 자세히 보고 정확한 수를 세어 명시
#      - 올바른 예: "세 명의 손님들이 카운터에 앉아 있다" (실제 3명)
#      - 잘못된 예: "두 명의 손님들이 앉아 있다" (실제 3명인데 2명으로 잘못 셈)
#    - **5명 이상이거나 정확히 세기 어려운 경우**: "여러 명", "다수의", "몇몇" 등 사용
#      - 올바른 예: "여러 명의 여성들이 요트 위에서 포즈를 취하고 있다" (5명 이상)
#      - 잘못된 예: "여섯 명의 여성들이..." (실제로는 5명인데 6명으로 잘못 셈)
#    - **배경에 있거나 부분적으로 가려진 사람은 세지 않음**

# 6. **총 50어절 이상 (필수!)**
#    - 5개 설명문을 모두 합쳤을 때 총 어절 수가 50어절 이상이어야 함
#    - 어절은 띄어쓰기로 구분되는 단위
#    - 예: "저는 오늘 사과를 먹었습니다." → 4어절 (저는 | 오늘 | 사과를 | 먹었습니다.)

# #### 어절 수 검증 규칙:

# **어절 정의:**
# - 어절은 띄어쓰기로 구분되는 단위입니다.

# **필수 조건:**
# - **5개 문장의 총 어절 수 ≥ 50어절**

# **검증 절차:**
# 1. 5개 description을 모두 작성
# 2. 각 문장의 어절 수 계산 (띄어쓰기 기준)
# 3. 총 어절 수 합산
# 4. **총 어절 수 < 50** → 각 문장에 구체적인 세부 묘사 추가

# **어절 부족 시 보완 방법:**

# **우선순위: 정경 > 객체1, 객체2 > 색감, 구도 순서로 구체화**

# 1. **정경 (SceneExp) - 우선 보완**
#    - 부족: "해변과 건물이 보이는 장면이다." (5어절)
#    - 충분: "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다." (18어절)

# 2. **객체1, 객체2 - 다음 보완**
#    - 부족: "사람들이 걷고 있다." (3어절)
#    - 충분: "해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다." (9어절)

# 3. **색감, 구도 - 간결하게 유지**
#    - 색감: "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다." (8어절)
#    - 구도: "높은 시점에서 내려다보는 항공 구도이다." (6어절)

# **좋은 예시 1: 해변 풍경 (총 어절 수 51개)**
# 1. SceneExp: "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다." (18어절)
# 2. ColortoneExp: "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다." (8어절)
# 3. CompositionExp: "높은 시점에서 내려다보는 항공 구도이다." (6어절)
# 4. ObjectExp1: "해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다." (9어절)
# 5. ObjectExp2: "유리 외벽이 반짝이는 고층 건물들이 빽빽하게 늘어서 있다." (10어절)

# **총 어절 수: 51어절  (50어절 이상 충족)**

# **좋은 예시 2: 레스토랑 장면 (사람 수 1-4명은 정확히 명시)**
# 1. SceneExp: "실내 레스토랑에서 한 명의 셰프가 큰 철판 위에서 요리하고 있으며, 손님들이 이를 지켜보는 활기찬 장면이다." (17어절)
# 2. ColortoneExp: "전반적으로 밝은 조명 아래 따뜻한 나무색과 시원한 푸른빛이 조화로운 색감이다." (12어절)
# 3. CompositionExp: "낮은 시점에서 셰프와 손님들을 올려다보는 구도이다." (8어절)
# 4. ObjectExp1: "흰색 조리복과 마스크를 착용한 한 명의 셰프가 철판 위에서 능숙하게 요리하고 있다." (13어절)
# 5. ObjectExp2: "세 명의 손님들이 카운터에 앉아 셰프의 요리 과정을 흥미롭게 지켜보고 있다." (12어절)

# **총 어절 수: 62어절  (50어절 이상 충족, 1-4명은 정확한 수 명시)**

# **좋은 예시 3: 요트 장면 (5명 이상은 "여러 명" 사용)**
# 1. SceneExp: "푸른 하늘과 바다를 배경으로 여러 명의 여성들이 요트 위에서 즐거운 시간을 보내는 활기찬 장면이다." (17어절)
# 2. ColortoneExp: "맑고 청량한 푸른색과 인물들의 다채로운 의상 색깔이 어우러져 밝고 생동감 있는 색감이다." (13어절)
# 3. CompositionExp: "요트의 앞부분에서 인물들을 중심으로 약간 낮은 시점에서 넓게 담아낸 구도이다." (13어절)
# 4. ObjectExp1: "여러 명의 여성들이 요트 위에 앉거나 서서 카메라를 향해 밝게 웃으며 포즈를 취하고 있다." (16어절)
# 5. ObjectExp2: "배경에는 푸른 바다 위로 길게 뻗은 다리가 보이며, 요트의 돛대가 하늘을 향해 높이 솟아 있다." (18어절)

# **총 어절 수: 77어절  (50어절 이상 충족, 5명 이상은 "여러 명" 사용)**


# ## 최종 출력 전 필수 검증

# **자동 계산 검증:**
# 1.  이미지 메타데이터가 정확히 입력되었는가?
#    - width, height, format 확인

# **논리적 검증:**
# 1.  category_info의 LocationCategory와 EraCategory가 정확히 선택되었는가?
#    - 이미지 내용과 일치하는지 확인

# 2.  annotation_info의 5개 설명문이 모두 작성되었는가?
#    - SceneExp, ColortoneExp, CompositionExp, ObjectExp1, ObjectExp2

# 3.  객체1과 객체2가 중복되지 않는가?

# 4.  총 어절 수가 50어절 이상인가?
#    - 5개 문장의 description을 모두 합쳐 띄어쓰기 기준으로 어절 수 계산
#    - 총 어절 수 < 50 → 각 문장에 구체적 세부 묘사 추가 후 다시 계산
#    - 총 어절 수 ≥ 50 → 통과

# 5.  Explanation이 5개 문장을 순서대로 합친 것인가?
#    - SceneExp + ColortoneExp + CompositionExp + ObjectExp1 + ObjectExp2

# **위 검증을 통과하지 못하면 처음부터 다시 분석!**


# ## 출력 형식

# **중요:**
# 1. 모든 메타데이터 값은 제공된 값 그대로 사용
# 2. 아래 예시는 샘플이며, 반드시 실제 분석 결과로 교체
# 3. category_info는 딕셔너리 형태로 LocationCategory와 EraCategory의 class 번호만 출력

# {{
#   "meta": {{
#     "width": [자동 생성],
#     "height": [자동 생성],
#     "format": "[자동 생성]"
#   }},
#   "category_info": {{
#     "LocationCategory": 2,
#     "EraCategory": 2
#   }},
#   "annotation_info": {{
#     "SceneExp": "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다.",
#     "ColortoneExp": "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다.",
#     "CompositionExp": "높은 시점에서 내려다보는 항공 구도이다.",
#     "ObjectExp1": "해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다.",
#     "ObjectExp2": "유리 외벽이 반짝이는 고층 건물들이 빽빽하게 늘어서 있다.",
#     "Explanation": "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 도시 해안 풍경이 밝고 여유로운 장면이다. 밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다. 높은 시점에서 내려다보는 항공 구도이다. 해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다. 유리 외벽이 반짝이는 고층 건물들이 빽빽하게 늘어서 있다."
#   }}
# }}
# """
#     return base_prompt.strip()


# def build_full_prompt(user_prompt: str, image_metadata: dict) -> str:
#     """
#     사용자가 편집한 프롬프트 + 시스템 자동 생성 섹션을 결합

#     Args:
#         user_prompt: 사용자가 편집한 프롬프트
#         image_metadata: 이미지 메타데이터

#     Returns:
#         완전한 프롬프트 문자열
#     """
#     # 1. 메타데이터 섹션 생성
#     metadata_section = f"""
# ## 이미지 메타데이터 (정확한 정보 - 반드시 사용)
# **이 정보는 실제 이미지에서 추출한 정확한 값입니다. 추측하지 말고 아래 값을 그대로 사용하세요:**
# - **이미지 해상도**: {image_metadata['width']} × {image_metadata['height']} 픽셀
# - **이미지 포맷**: {image_metadata['format']}
# - **파일 크기**: {image_metadata['file_size']} bytes

# **중요: 위 값들은 절대 변경하거나 추측하지 마세요. JSON 출력 시 그대로 사용하세요.**
# """

#     # 2. 카테고리 텍스트 생성
#     categories_text = ""
#     for key, items in CATEGORY_DATA.items():
#         korean_name = CATEGORY_LABELS.get(key, key)
#         labels = ", ".join([f"{item['label']}({item['class']})" for item in items])
#         categories_text += f"- **{key}** ({korean_name}): {labels}\n"

#     # 3. 플레이스홀더 교체
#     full_prompt = user_prompt.replace("{metadata_section}", metadata_section.strip())
#     full_prompt = full_prompt.replace("{categories_text}", categories_text.strip())

#     return full_prompt


# async def analyze_image_async(image_path: str, mime_type: str, image_metadata: dict, api_key: str, user_prompt: str):
#     """
#     이미지 분석 실행 (비동기)

#     Args:
#         image_path: 이미지 파일 경로
#         mime_type: MIME 타입
#         image_metadata: 이미지 메타데이터
#         api_key: Gemini API 키
#         user_prompt: 사용자가 편집한 프롬프트

#     Returns:
#         분석 결과 딕셔너리
#     """
#     # GeminiImageAnalyzer 인스턴스 생성
#     analyzer = GeminiImageAnalyzer(api_key=api_key)

#     # 완전한 프롬프트 생성 (사용자 편집 + 시스템 자동 생성)
#     full_prompt = build_full_prompt(user_prompt, image_metadata)

#     # 프롬프트를 analyzer의 기본 프롬프트로 덮어쓰기
#     # (gemini_analyzer.py의 analyze_image는 get_default_prompt를 호출하므로, 이를 우회)
#     # 대신 직접 API 호출
#     import google.generativeai as genai

#     # API 설정
#     genai.configure(api_key=api_key)

#     # Safety Settings
#     safety_settings = [
#         {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
#         {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
#         {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
#         {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
#     ]

#     model = genai.GenerativeModel(
#         model_name="gemini-2.5-flash",
#         generation_config={
#             "temperature": 0,
#             "top_p": 1,
#             "top_k": 1,
#             "max_output_tokens": 65536,
#             "response_mime_type": "application/json",
#         },
#         safety_settings=safety_settings
#     )

#     # 이미지 읽기
#     image_data = Image.open(image_path)

#     # API 호출
#     response = await asyncio.to_thread(
#         model.generate_content,
#         [full_prompt, image_data]
#     )

#     # 응답 파싱
#     result = json.loads(response.text)

#     return result


# # 메인 앱
# st.title("🖼️ 배경 이미지 분석기")
# st.markdown("한국적 배경 이미지를 분석하고 설명문을 생성합니다.")

# # 사이드바 - 설정
# with st.sidebar:
#     st.header("⚙️ 설정")

#     # API 키 자동 로드 (.env 또는 Streamlit Cloud secrets)
#     api_key = os.getenv('GOOGLE_API_KEY_IMAGE', '')

#     # Streamlit Cloud에서는 secrets 사용 (try-except로 안전하게 처리)
#     try:
#         if 'GOOGLE_API_KEY_IMAGE' in st.secrets:
#             api_key = st.secrets['GOOGLE_API_KEY_IMAGE']
#     except (FileNotFoundError, AttributeError):
#         # 로컬 환경에서 secrets.toml 없음 - .env 사용
#         pass

#     # API 키 수동 입력 필드 (필요 시 주석 해제)
#     # api_key = st.text_input(
#     #     "Gemini API 키",
#     #     value=api_key,
#     #     type="password",
#     #     help="Google Gemini API 키를 입력하세요"
#     # )

#     if api_key:
#         st.success("✅ API 키 로드 완료")
#     else:
#         st.error("❌ API 키를 .env 파일에 설정하세요")

#     st.divider()
#     st.markdown("### 📖 사용 방법")
#     st.markdown("""
#     1. 이미지를 업로드하세요
#     2. 프롬프트를 수정하세요 (선택사항)
#     3. '분석 시작' 버튼을 클릭하세요
#     """)

#     st.divider()
#     # st.markdown("### ℹ️ 정보")
#     # st.markdown("**모델**: gemini-2.5-flash")
#     # st.markdown("**출력**: JSON (category_info, annotation_info)")

# # 메인 컨텐츠 - 2개 컬럼
# col1, col2 = st.columns([1, 1])

# with col1:
#     st.header("📝 입력")

#     # 1. 이미지 업로드
#     st.subheader("1. 이미지 업로드")
#     uploaded_file = st.file_uploader(
#         "배경 이미지를 업로드하세요",
#         type=['jpg', 'jpeg', 'png', 'webp'],
#         help="JPG, PNG, WEBP 형식 지원"
#     )

#     if uploaded_file:
#         # 이미지 저장 (임시 파일)
#         temp_dir = Path("temp_images")
#         temp_dir.mkdir(exist_ok=True)

#         temp_image_path = temp_dir / uploaded_file.name
#         with open(temp_image_path, 'wb') as f:
#             f.write(uploaded_file.getbuffer())

#         # 이미지 메타데이터 추출
#         image = Image.open(temp_image_path)
#         image_metadata = {
#             'width': image.width,
#             'height': image.height,
#             'format': image.format,
#             'file_size': temp_image_path.stat().st_size
#         }

#         st.session_state['uploaded_image'] = {
#             'path': str(temp_image_path),
#             'metadata': image_metadata,
#             'mime_type': f"image/{image.format.lower()}"
#         }

#         # 메타데이터 표시
#         st.info(f"📊 {image.width} × {image.height} px | {image.format} | {image_metadata['file_size']:,} bytes")

#     # 2. 프롬프트 편집
#     st.subheader("2. 프롬프트 편집")

#     # 시스템 고정 섹션 안내
#     st.warning("""
#     ⚠️ **다음 섹션은 자동 생성되므로 수정할 수 없습니다:**
#     - `{metadata_section}` - 이미지 메타데이터
#     - `{categories_text}` - 카테고리 정보

#     분석 시 자동으로 실제 값으로 대체됩니다.
#     """)

#     # 기본 프롬프트 로드
#     default_prompt = extract_user_editable_prompt()

#     user_prompt = st.text_area(
#         "프롬프트를 수정할 수 있습니다",
#         value=default_prompt,
#         height=400,
#         help="프롬프트 내에 {metadata_section}, {categories_text}는 자동 생성됩니다"
#     )

#     # 플레이스홀더 검증
#     if "{metadata_section}" not in user_prompt or "{categories_text}" not in user_prompt:
#         st.error("⚠️ 필수 플레이스홀더 `{metadata_section}`, `{categories_text}`가 제거되었습니다!")

#     # 3. 분석 버튼
#     st.divider()
#     if st.button("🚀 분석 시작", type="primary", use_container_width=True, disabled=not (uploaded_file and api_key)):
#         if not api_key:
#             st.error("❌ API 키를 입력하세요")
#         elif not uploaded_file:
#             st.error("❌ 이미지를 업로드하세요")
#         elif "{metadata_section}" not in user_prompt or "{categories_text}" not in user_prompt:
#             st.error("❌ 필수 플레이스홀더가 누락되었습니다")
#         else:
#             with st.spinner("🔄 이미지 분석 중..."):
#                 try:
#                     # 비동기 분석 실행
#                     result = asyncio.run(
#                         analyze_image_async(
#                             st.session_state['uploaded_image']['path'],
#                             st.session_state['uploaded_image']['mime_type'],
#                             st.session_state['uploaded_image']['metadata'],
#                             api_key,
#                             user_prompt
#                         )
#                     )

#                     st.session_state['analysis_result'] = result
#                     st.success("✅ 분석 완료!")

#                 except Exception as e:
#                     st.error(f"❌ 분석 중 오류 발생: {str(e)}")
#                     import traceback
#                     st.code(traceback.format_exc())

# with col2:
#     st.header("📤 출력")

#     # 업로드된 이미지 미리보기
#     if st.session_state.get('uploaded_image'):
#         st.subheader("업로드된 이미지")
#         st.image(st.session_state['uploaded_image']['path'], use_container_width=True)

#     # 분석 결과 표시
#     if st.session_state.get('analysis_result'):
#         result = st.session_state['analysis_result']

#         st.divider()

#         # 1. 설명문 (Explanation)
#         st.subheader("📄 설명문 (Explanation)")
#         if 'annotation_info' in result and 'Explanation' in result['annotation_info']:
#             st.write(result['annotation_info']['Explanation'])

#         # 2. Category Info
#         with st.expander("🏷️ 카테고리 정보 (category_info)", expanded=False):
#             if 'category_info' in result:
#                 category_info = result['category_info']

#                 # LocationCategory
#                 loc_cat = category_info.get('LocationCategory', 'N/A')
#                 loc_label = "알 수 없음"
#                 if loc_cat == 1:
#                     loc_label = "실내"
#                 elif loc_cat == 2:
#                     loc_label = "실외"
#                 elif loc_cat == 3:
#                     loc_label = "혼합"

#                 st.markdown(f"**LocationCategory**: {loc_label} ({loc_cat})")

#                 # EraCategory
#                 era_cat = category_info.get('EraCategory', 'N/A')
#                 era_label = "알 수 없음"
#                 if era_cat == 1:
#                     era_label = "전통"
#                 elif era_cat == 2:
#                     era_label = "현대"
#                 elif era_cat == 3:
#                     era_label = "혼합"
#                 elif era_cat == 4:
#                     era_label = "기타"

#                 st.markdown(f"**EraCategory**: {era_label} ({era_cat})")

#         # 3. Annotation Info
#         with st.expander("✍️ 어노테이션 정보 (annotation_info)", expanded=True):
#             if 'annotation_info' in result:
#                 ann_info = result['annotation_info']

#                 st.markdown("**1. 정경 설명 (SceneExp)**")
#                 st.write(ann_info.get('SceneExp', 'N/A'))

#                 st.markdown("**2. 색감 설명 (ColortoneExp)**")
#                 st.write(ann_info.get('ColortoneExp', 'N/A'))

#                 st.markdown("**3. 구도 설명 (CompositionExp)**")
#                 st.write(ann_info.get('CompositionExp', 'N/A'))

#                 st.markdown("**4. 객체1 설명 (ObjectExp1)**")
#                 st.write(ann_info.get('ObjectExp1', 'N/A'))

#                 st.markdown("**5. 객체2 설명 (ObjectExp2)**")
#                 st.write(ann_info.get('ObjectExp2', 'N/A'))

#         # 4. JSON 다운로드
#         st.divider()
#         json_str = json.dumps(result, ensure_ascii=False, indent=2)
#         st.download_button(
#             label="📥 JSON 다운로드",
#             data=json_str,
#             file_name=f"analysis_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
#             mime="application/json",
#             use_container_width=True
#         )

#         # 5. JSON 미리보기
#         with st.expander("📋 JSON 미리보기"):
#             st.json(result)

#     else:
#         st.info(" 왼쪽에서 이미지를 업로드하고 '분석 시작' 버튼을 클릭하세요")
