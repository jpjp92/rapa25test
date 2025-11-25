### 테스트3
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

# 커스텀 CSS - 다크모드 대응
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
        color: #718096;
        font-size: 1.1rem;
        text-align: center;
        margin-top: -1.5rem;
        margin-bottom: 2rem;
    }
    
    /* 다크모드 대응 탭 스타일링 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        border-bottom: 2px solid rgba(128, 128, 128, 0.3);
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 24px;
        padding-right: 24px;
        background-color: transparent;
        border-radius: 12px 12px 0px 0px;
        font-weight: 600;
        color: inherit;
    }
    
    /* 선택된 탭 - 다크모드 대응 */
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }
    
    /* 선택되지 않은 탭 호버 */
    .stTabs [aria-selected="false"]:hover {
        background-color: rgba(128, 128, 128, 0.1);
    }
    
    /* 컨테이너 스타일 - 다크모드 대응 */
    div[data-testid="stContainer"] {
        padding: 1.5rem;
        border-radius: 12px;
    }
    
    /* 메트릭 카드 스타일 - 다크모드 대응 */
    div[data-testid="metric-container"] {
        background-color: rgba(128, 128, 128, 0.1);
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid rgba(128, 128, 128, 0.2);
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
    
    /* 이미지 컨테이너 높이 제한 */
    .image-container {
        max-height: 400px;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
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
   - **실내(1)**: 건물 내부, 방, 실내 공간
     - 카메라 위치가 실내 + 장면의 주요 공간도 실내인 경우

   - **실외(2)**: 야외, 자연, 거리, 건물 외부
     - 벽·천장 없이 개방된 야외 공간
     - 카메라 위치와 장면의 주요 공간이 모두 실외인 경우

   - **혼합(3)**: **한 화면에 실내 공간과 실외 공간이 동시에 보이는 모든 경우**
     - 카메라가 실내에서 실외를 보는 경우 (창문, 문을 통해 밖이 보임)
     - 카메라가 실외에서 실내를 보는 경우 (밖에서 건물 내부가 보임)
     - 반개방형 구조 (비닐하우스, 천막, 파고라 등 실내외 구분이 모호한 공간)
     - **판정 원칙**: 화면에 실내 요소와 실외 요소가 **모두** 관찰되면 무조건 혼합

   - **기타(4)**: 일러스트나 애니메이션은 무조건 기타로 분류

2. **EraCategory (시대 구분) - 반드시 아래 순서대로 판정**
   **판정 순서:**
   1. 먼저 이미지의 **모든 요소**(인물, 건축물, 소품)를 확인
   2. 전통 요소와 현대 요소가 **모두** 있으면 → 혼합(3)
   3. 전통 요소만 있으면 → 전통(1)
   4. 현대 요소만 있으면 → 현대(2)

   **분류 기준:**
   - **전통(1)**: **전통 요소만** 존재하는 경우
     - 전통 건축물(한옥, 성곽, 사찰), 전통 복장(한복, 갑옷), 전통 소품만 있는 경우

   - **현대(2)**: **현대 요소만** 존재하는 경우
     - 현대 건축물, 현대 복장(일상복, 정장), 현대 소품만 있는 경우

   - **혼합(3)**: **전통 요소와 현대 요소가 한 화면에 공존**
     - 전통 건축물 + 현대 소품,의상,물건
     - 전통 복장 + 현대 복장 
     - 현대 배경 + 전통 소품

   - **기타(4)**: SF/판타지, 특수 분장, 코스프레, 애니메이션 캐릭터, 비현실적 상황, 자연물만 있는 경우

   **중요 원칙:**
   - 화면에 보이는 **모든 현대 요소**는 판정에 반영
   - 크기가 작거나 배경에 있어도 **명확히 보이면** 판정 기준에 포함

### 한국전통색상 사용 규칙 (EraCategory=1인 경우)
**EraCategory가 전통(1)으로 판정된 경우, ColortoneExp 작성 시 아래 한국전통표준색을 사용하세요:**

#### 주요 전통색상 (카테고리별):

**흑백 계열:**
- 흑색 (#1d1e23), 백색 (#ffffff), 회색 (#a4aaa7), 설백색 (#dde7e7)

**적·홍 계열:**
- 적색 (#b82647), 홍색 (#f15b5b), 주홍색 (#c23352), 진홍색 (#bf2f7b)
- 연지색 (#be577b), 분홍색 (#e2a6b4), 갈색 (#966147)

**자 계열:**
- 자색 (#6d1b43), 자주색 (#89236a), 보라색 (#9c4998), 포도색 (#5d3462)

**청·벽·녹 계열:**
- 청색 (#0b6db7), 벽색 (#00b5e3), 옥색 (#9ed6c0), 비색 (#72c6a5)
- 청록색 (#009770), 녹색 (#417141), 연두색 (#c0d84d)

**황 계열:**
- 황색 (#f9d537), 송화색 (#f8e77f), 치자색 (#f6cf7a), 금색 (#ffb500)

**전통색상 사용 지침:**
1. 이미지의 주요 색상을 위 RGB 코드와 비교하여 가장 가까운 전통색상명 선택
2. "색상명 + 대상" 형식으로 작성 (예: "옥색 치마", "적색 댕기", "송화색 저고리")
3. 전통색상명을 사용하되, 너무 어색한 경우 기본 색상 표현도 가능
4. 전체적인 색감 조화는 전통색상을 우선 사용하여 표현

**예시:**
- "옥색 치마와 송화색 저고리가 조화를 이루는 전통적 색감이다."
- "짙은 자주색 한복과 금색 장식이 어우러진 고풍스러운 색감이다."
- "적색 댕기와 백색 저고리가 대비를 이루는 선명한 색감이다."


### 2단계: 설명문 작성 (annotation_info)

**전달하는 이미지를 생성하기 위한 INPUT 설명문을 아래 기준을 참고해서 만들어주세요.**

#### 총 5문장 작성:

1. **장면 설명 (SceneExp)**
   - **목적**: 이미지의 전체적인 맥락과 상황 전달. 색감은 제외
   - **포함 요소**: 장소의 종류, 전체적인 환경, 사람들의 행동/상황
   - **제외 요소**: 색상(ColortoneExp), 카메라 각도(CompositionExp), 개별 객체 세부사항(ObjectExp)
   - **작성 방식**: 구체적인 장소, 환경, 행동 중심으로 묘사 (추상적 분위기 표현 최소화)
   - **중복 주의**: 색감 설명과 동일한 수식어 사용 금지 (차분한, 밝은, 어두운, 활기찬, 따뜻한 등)
   - 종결 어미: **~장면이다.**

2. **색감 설명 (ColortoneExp)**
   - **목적**: 이미지의 색채적 특성만 전달
   - **포함 요소**: 주요 색상, 색의 조화, 명암, 톤, 채도
   - **작성 방식**: "색상 + 대상"을 2-3개 조합하여 전체 색감 묘사
     - 예: "옅은 베이지색 벽", "푸른빛이 도는 하늘", "어두운 의상"
   - **조화 표현**: "어우러진", "조화를 이루는", "대비를 이루며" 등 사용
   - **제외 요소**: 객체의 형태나 질감, 장면의 분위기, 카메라 구도
   - **중요**: EraCategory가 전통(1)인 경우, 위 "한국전통색상 사용 규칙"을 참고하여 전통색상명 사용
   - 종결 어미: **~색감이다.**

3. **구도 설명 (CompositionExp)**
   - **목적**: 카메라 촬영 방식과 화면 구성만 전달
   - **포함 요소**: 카메라 높이(눈높이/높은 시점/낮은 시점), 각도(정면/측면/위/아래), 화면 배치
   - **제외 요소**: 색상, 객체의 세부 묘사, 장면의 내용 (배경에 무엇이 있다는 등)
   - **작성 방식**: 거리와 구도를 한국적 표현으로 사용 
   - 종결 어미: **~구도이다.**

4. **객체1 설명 (ObjectExp1)**
   - **목적**: 이미지의 주요 객체 하나에 대한 물리적 특징 전달
   - **포함 요소**: 형태, 크기, 질감, 패턴, 자세, 동작, 의상/구조
   - **절대 금지**: 색상 표현 (빨간, 파란, 노란, 흰, 검은, 회색, 베이지, 밝은, 어두운 등)
   - **제외 요소**: 전체적 분위기(SceneExp), 카메라 구도
   - **동작 묘사 원칙**: 이미지에서 명확히 관찰되는 자세/동작만 기술 (추측 금지)
     - 허용: "서 있다", "앉아 있다", "입을 벌리고 있다", "팔을 들어 올리고 있다"
     - 금지: "사과를 수확하고 있다" (추측), "과일을 든 채" (불명확)
   - **객체가 사람인 경우 수 표현 규칙:**
     - 1-4명: 정확한 수 명시 (한 명, 두 명, 세 명, 네 명)
     - 5명 이상 또는 불명확: "여러 명", "다수의", "몇몇" 등 사용
   - 객체가 사물인 경우 표면적 느낌도 같이 설명
   - 종결 어미: **~다.**

5. **객체2 설명 (ObjectExp2)**
   - **목적**: 이미지의 또 다른 주요 객체에 대한 물리적 특징 전달
   - **포함 요소**: 형태, 크기, 질감, 패턴, 자세, 동작, 의상/구조
   - **절대 금지**: 색상 표현 (빨간, 파란, 노란, 흰, 검은, 회색, 베이지, 밝은, 어두운 등)
   - **제외 요소**: 전체적 분위기(SceneExp), 카메라 구도, 객체1과 중복되는 객체
   - **동작 묘사 원칙**: 이미지에서 명확히 관찰되는 자세/동작만 기술 (추측 금지)
     - 허용: "서 있다", "앉아 있다", "손을 뻗고 있다", "고개를 돌리고 있다"
     - 금지: "작업하고 있다" (모호함), "물건을 들고 있다" (불명확)
   - **객체가 사람인 경우 수 표현 규칙:**
     - 1-4명: 정확한 수 명시 (한 명, 두 명, 세 명, 네 명)
     - 5명 이상 또는 불명확: "여러 명", "다수의", "몇몇" 등 사용
   - 객체가 사물인 경우 표면적 느낌도 같이 설명
   - 종결 어미: **~다.**

#### 주의사항:

1. **객체 중복 금지**
   - 객체1과 객체2는 서로 다른 객체를 설명해야 함
   - 예: 객체1에서 "사람들"을 설명했으면, 객체2는 "건물" 등 다른 객체

2. **내용 중복 금지**
   - 5문장을 합쳐 한 문단으로 보고, 각 설명문에 포함되어야 할 내용을 중복 사용하지 말 것
   - 장면 설명에서 언급한 내용을 색감 설명에서 반복하지 말 것

3. **자막 및 방송 UI 요소 제외**
   - 자막, 방송 로고, 워터마크, 타임스탬프 등 방송/편집 요소는 설명하지 말 것
   - 화면에 표시된 텍스트 내용뿐만 아니라 UI 요소의 존재 자체도 언급하지 말 것
   - 제외 대상: 방송 로고, 프로그램명, 자막, 워터마크, 시간 표시 등
   - 올바른 예: "배경에는 나무 구조물과 옅은 베이지색 벽이 흐릿하게 보인다."
   - 잘못된 예: "화면 상단에는 방송 로고와 자막이 선명하게 나타난다."

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

**우선순위: 장면 > 객체1, 객체2 > 색감, 구도 순서로 구체화**

1. **장면 (SceneExp) - 우선 보완**
   - 부족: "해변과 건물이 보이는 장면이다." (5어절)
   - 충분: "넓은 해변이 곧게 펼쳐지고 그 뒤로 고층 건물들이 줄지어 서 있는 장면이다." (13어절)

2. **객체1, 객체2 - 다음 보완**
   - 부족: "사람들이 걷고 있다." (3어절)
   - 충분: "해변 곳곳에는 사람들이 여유롭게 걸으며 휴식을 즐기고 있다." (9어절)

3. **색감, 구도 - 간결하게 유지**
   - 색감: "밝은 모래빛과 짙푸른 바다가 어우러진 명료한 색감이다." (8어절)
   - 구도: "높은 시점에서 내려다보는 항공 구도이다." (6어절)

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
    "SceneExp": "[실제 장면 설명으로 교체 - 장소, 환경, 분위기]",
    "ColortoneExp": "[실제 색감 설명으로 교체 - 색상, 명암, 톤]",
    "CompositionExp": "[실제 구도 설명으로 교체 - 카메라 각도, 원근감]",
    "ObjectExp1": "[실제 객체1 설명으로 교체 - 형태, 질감, 동작 (색상 제외)]",
    "ObjectExp2": "[실제 객체2 설명으로 교체 - 형태, 질감, 동작 (색상 제외)]",
    "Explanation": "[위 5개 설명을 순서대로 합친 전체 설명문]"
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
st.markdown('<p class="sub-header">Gemini 2.5 Flash 모델로 배경 이미지를 분석하고 설명문을 생성합니다.</p>', unsafe_allow_html=True)

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

# 메인 탭 - 2개로 축소
tab1, tab2 = st.tabs(["🖼️ 이미지 분석", "💾 JSON 다운로드"])

with tab1:
    # 왼쪽: 입력 섹션, 오른쪽: 결과 섹션
    col_left, col_right = st.columns([5, 5], gap="large")
    
    with col_left:
        st.markdown("### 📝 입력")
        
        # 이미지 업로드 섹션
        # 이미지 업로드 섹션
        # with st.container(border=True):
        #     st.markdown("#### 📸 이미지 업로드")
            
        #     # 드래그앤드롭 스타일 추가
        #     st.markdown("""
        #     <style>
        #     [data-testid="stFileUploadDropzone"] {
        #         background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
        #         border: 2px dashed rgba(102, 126, 234, 0.4);
        #         border-radius: 12px;
        #         padding: 2rem;
        #         transition: all 0.3s ease;
        #     }
            
        #     [data-testid="stFileUploadDropzone"]:hover {
        #         background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
        #         border-color: rgba(102, 126, 234, 0.6);
        #         transform: scale(1.01);
        #     }
            
        #     [data-testid="stFileUploadDropzone"] p {
        #         color: #718096;
        #         font-weight: 500;
        #     }
        #     </style>
        #     """, unsafe_allow_html=True)
            
        #     # 업로드 전 안내 메시지 표시
        #     if not st.session_state.get('uploaded_image'):
        #         st.markdown("""
        #         <div style="text-align: center; padding: 1rem 0; color: #718096;">
        #             <p style="font-size: 2rem; margin-bottom: 0.5rem;">📸</p>
        #             <p style="font-size: 0.95rem;">이미지를 드래그하거나 클릭하여 업로드하세요</p>
        #             <p style="font-size: 0.85rem; color: #a0aec0; margin-top: 0.3rem;">
        #                 JPG, PNG, WEBP (최대 20MB)
        #             </p>
        #         </div>
        #         """, unsafe_allow_html=True)
            
        #     # 파일 업로더
        #     uploaded_file = st.file_uploader(
        #         "배경 이미지를 선택하세요",
        #         type=['jpg', 'jpeg', 'png', 'webp'],
        #         help="드래그앤드롭 또는 클릭하여 업로드",
        #         label_visibility="collapsed"  # 라벨 숨기기
        #     )
            
        #     # 이미지 업로드 처리
        #     if uploaded_file:
        #         try:
        #             # 이미지 저장 (임시 파일)
        #             temp_dir = Path("temp_images")
        #             temp_dir.mkdir(exist_ok=True)
                    
        #             temp_image_path = temp_dir / uploaded_file.name
        #             with open(temp_image_path, 'wb') as f:
        #                 f.write(uploaded_file.getbuffer())
                    
        #             # 이미지 메타데이터 추출
        #             image = Image.open(temp_image_path)
        #             image_metadata = {
        #                 'width': image.width,
        #                 'height': image.height,
        #                 'format': image.format,
        #                 'file_size': temp_image_path.stat().st_size
        #             }
                    
        #             # 세션 상태 저장
        #             st.session_state['uploaded_image'] = {
        #                 'path': str(temp_image_path),
        #                 'metadata': image_metadata,
        #                 'mime_type': f"image/{image.format.lower()}"
        #             }
                    
        #             # 업로드 성공 메시지
        #             st.success(f"✅ {uploaded_file.name} 업로드 완료")
                    
        #             # 이미지 미리보기 (높이 제한)
        #             st.markdown("""
        #             <style>
        #             .image-preview-container {
        #                 max-height: 300px;
        #                 overflow: hidden;
        #                 border-radius: 8px;
        #                 margin: 1rem 0;
        #             }
        #             </style>
        #             """, unsafe_allow_html=True)
                    
        #             st.markdown('<div class="image-preview-container">', unsafe_allow_html=True)
        #             st.image(image, caption=f"📷 {uploaded_file.name}", use_container_width=True)
        #             st.markdown('</div>', unsafe_allow_html=True)
                    
        #             # 이미지 정보 표시
        #             col1, col2, col3 = st.columns(3)
        #             with col1:
        #                 st.metric("📐 해상도", f"{image_metadata['width']}×{image_metadata['height']}")
        #             with col2:
        #                 file_size_mb = image_metadata['file_size'] / (1024 * 1024)
        #                 if file_size_mb < 1:
        #                     size_str = f"{image_metadata['file_size'] / 1024:.1f} KB"
        #                 else:
        #                     size_str = f"{file_size_mb:.1f} MB"
        #                 st.metric("💾 크기", size_str)
        #             with col3:
        #                 st.metric("📄 형식", image_metadata['format'])
                    
        #         except Exception as e:
        #             st.error(f"❌ 이미지 처리 오류: {str(e)}")
        #             # 오류 시 세션 상태 초기화
        #             if 'uploaded_image' in st.session_state:
        #                 del st.session_state['uploaded_image']

        
        with st.container(border=True):
            st.markdown("#### 📸 이미지 업로드")
            
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
                
                # 이미지 미리보기 - 높이 제한
                st.markdown('<div class="image-container">', unsafe_allow_html=True)
                st.image(image, caption="업로드된 이미지", use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                # 이미지 정보
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("해상도", f"{image_metadata['width']}×{image_metadata['height']}")
                with col_b:
                    st.metric("크기", f"{image_metadata['file_size']:,} bytes")
        
        # 프롬프트 편집 섹션
        with st.container(border=True):
            st.markdown("#### ⚙️ 프롬프트 설정")
            
            # 안내 메시지
            with st.expander("ℹ️ 프롬프트 가이드", expanded=False):
                st.info("""
                **자동 대체 플레이스홀더:**
                - `{metadata_section}` → 이미지 메타데이터
                - `{categories_text}` → 카테고리 정보
                
                이 플레이스홀더는 삭제하지 마세요!
                """)
            
            # 기본 프롬프트 로드
            default_prompt = extract_user_editable_prompt()
            
            user_prompt = st.text_area(
                "프롬프트 편집",
                value=default_prompt,
                height=300,
                help="프롬프트 내 플레이스홀더는 자동 생성됩니다"
            )
            
            # 플레이스홀더 검증
            placeholder_valid = "{metadata_section}" in user_prompt and "{categories_text}" in user_prompt
            
            if not placeholder_valid:
                st.error("⚠️ 필수 플레이스홀더가 제거되었습니다!")
        
        # 분석 시작 버튼
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
                
                with st.spinner("🔄 이미지 분석 중... (10-30초 소요)"):
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
                        st.success("✅ 분석 완료!")
                        st.rerun()  # 결과를 즉시 표시하기 위해 리런
                        
                    except Exception as e:
                        st.session_state['analysis_status'] = 'waiting'
                        st.error(f"❌ 분석 오류: {str(e)}")
                        
                        with st.expander("🔍 상세 오류"):
                            import traceback
                            st.code(traceback.format_exc())

# col_right의 분석 결과 부분만 수정
with col_right:
    st.markdown("### 📊 분석 결과")
    
    if st.session_state.get('analysis_result'):
        result = st.session_state['analysis_result']
        
        # 통합 설명문
        with st.container(border=True):
            st.markdown("#### 📄 통합 설명문")
            if 'annotation_info' in result and 'Explanation' in result['annotation_info']:
                st.markdown(f"**{result['annotation_info']['Explanation']}**")
        
        # 카테고리 & 음절 수 체크
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("##### 🏷️ 카테고리")
                if 'category_info' in result:
                    cat_info = result['category_info']
                    
                    loc_labels = {1: "실내", 2: "실외", 3: "혼합", 4: "기타"}
                    era_labels = {1: "전통", 2: "현대", 3: "혼합", 4: "기타"}
                    
                    loc_value = cat_info.get('LocationCategory', 0)
                    era_value = cat_info.get('EraCategory', 0)
                    
                    st.write(f"**장소**: {loc_labels.get(loc_value, 'N/A')} ({loc_value})")
                    st.write(f"**시대**: {era_labels.get(era_value, 'N/A')} ({era_value})")
                    st.write("")  # 공백 추가
                    st.caption("카테고리 분류 완료")
        
        with col2:
            with st.container(border=True):
                st.markdown("##### 📊 음절 수 체크")
                if 'annotation_info' in result:
                    ann_info = result['annotation_info']
                    
                    # 총 음절 수 계산 (띄어쓰기 포함 모든 문자)
                    total_syllables = sum([
                        len(ann_info.get(key, '')) 
                        for key in ['SceneExp', 'ColortoneExp', 'CompositionExp', 'ObjectExp1', 'ObjectExp2']
                    ])
                    
                    # 50음절 기준 충족 여부
                    status = "✅ 충족" if total_syllables >= 50 else f"❌ 미달 (-{50-total_syllables})"
                    
                    st.write(f"**총 음절**: {total_syllables}음절")
                    st.write(f"**상태**: {status}")
                    st.write("")  # 공백 추가
                    st.caption("최소 50음절 필요")
        
        # 상세 설명문
        with st.container(border=True):
            st.markdown("#### ✍️ 상세 설명문")
            
            if 'annotation_info' in result:
                ann_info = result['annotation_info']
                
                # 각 설명문과 음절 수를 함께 표시
                with st.expander(f"🎬 장면 설명 ({len(ann_info.get('SceneExp', ''))}음절)", expanded=True):
                    st.write(ann_info.get('SceneExp', 'N/A'))
                
                with st.expander(f"🎨 색감 설명 ({len(ann_info.get('ColortoneExp', ''))}음절)", expanded=True):
                    st.write(ann_info.get('ColortoneExp', 'N/A'))
                
                with st.expander(f"📐 구도 설명 ({len(ann_info.get('CompositionExp', ''))}음절)", expanded=True):
                    st.write(ann_info.get('CompositionExp', 'N/A'))
                
                with st.expander(f"👤 객체1 설명 ({len(ann_info.get('ObjectExp1', ''))}음절)", expanded=True):
                    st.write(ann_info.get('ObjectExp1', 'N/A'))
                
                with st.expander(f"🏛️ 객체2 설명 ({len(ann_info.get('ObjectExp2', ''))}음절)", expanded=True):
                    st.write(ann_info.get('ObjectExp2', 'N/A'))
        
# col_right의 분석 결과 부분만 수정

        
# with col_right:
#     st.markdown("### 📊 분석 결과")
    
#     if st.session_state.get('analysis_result'):
#         result = st.session_state['analysis_result']
        
#         # 통합 설명문
#         with st.container(border=True):
#             st.markdown("#### 📄 통합 설명문")
#             if 'annotation_info' in result and 'Explanation' in result['annotation_info']:
#                 st.markdown(f"**{result['annotation_info']['Explanation']}**")
        
#         # 카테고리 & 어절 수 체크
#         col1, col2 = st.columns(2)
#         with col1:
#             with st.container(border=True):
#                 st.markdown("##### 🏷️ 카테고리")
#                 if 'category_info' in result:
#                     cat_info = result['category_info']
                    
#                     loc_labels = {1: "실내", 2: "실외", 3: "혼합", 4: "기타"}
#                     era_labels = {1: "전통", 2: "현대", 3: "혼합", 4: "기타"}
                    
#                     loc_value = cat_info.get('LocationCategory', 0)
#                     era_value = cat_info.get('EraCategory', 0)
                    
#                     st.write(f"**장소**: {loc_labels.get(loc_value, 'N/A')} ({loc_value})")
#                     st.write(f"**시대**: {era_labels.get(era_value, 'N/A')} ({era_value})")
#                     st.write("")  # 공백 추가
#                     st.caption("카테고리 분류 완료")
        
#         with col2:
#             with st.container(border=True):
#                 st.markdown("##### 📊 어절 수 체크")
#                 if 'annotation_info' in result:
#                     ann_info = result['annotation_info']
                    
#                     # 총 어절 수 계산
#                     total_words = sum([
#                         len(ann_info.get(key, '').split()) 
#                         for key in ['SceneExp', 'ColortoneExp', 'CompositionExp', 'ObjectExp1', 'ObjectExp2']
#                     ])
                    
#                     # 50어절 기준 충족 여부
#                     status = "✅ 충족" if total_words >= 50 else f"❌ 미달 (-{50-total_words})"
                    
#                     st.write(f"**총 어절**: {total_words}어절")
#                     st.write(f"**상태**: {status}")
#                     st.write("")  # 공백 추가
#                     st.caption("최소 50어절 필요")
       
        
        # # 상세 설명문
        # with st.container(border=True):
        #     st.markdown("#### ✍️ 상세 설명문")
            
        #     if 'annotation_info' in result:
        #         ann_info = result['annotation_info']
                
        #         # 각 설명문과 어절 수를 함께 표시
        #         with st.expander(f"🎬 장면 설명 ({len(ann_info.get('SceneExp', '').split())}어절)", expanded=True):
        #             st.write(ann_info.get('SceneExp', 'N/A'))
                
        #         with st.expander(f"🎨 색감 설명 ({len(ann_info.get('ColortoneExp', '').split())}어절)", expanded=True):
        #             st.write(ann_info.get('ColortoneExp', 'N/A'))
                
        #         with st.expander(f"📐 구도 설명 ({len(ann_info.get('CompositionExp', '').split())}어절)", expanded=True):
        #             st.write(ann_info.get('CompositionExp', 'N/A'))
                
        #         with st.expander(f"👤 객체1 설명 ({len(ann_info.get('ObjectExp1', '').split())}어절)", expanded=True):
        #             st.write(ann_info.get('ObjectExp1', 'N/A'))
                
        #         with st.expander(f"🏛️ 객체2 설명 ({len(ann_info.get('ObjectExp2', '').split())}어절)", expanded=True):
        #             st.write(ann_info.get('ObjectExp2', 'N/A'))
    else:
        # Empty state
        with st.container(border=True):
            st.info("📝 이미지를 업로드하고 분석을 시작하면 결과가 여기에 표시됩니다.")
            
            # 높이 맞추기
            for _ in range(10):
                st.write("")
    # with col_right:
    #     st.markdown("### 📊 분석 결과")
        
    #     if st.session_state.get('analysis_result'):
    #         result = st.session_state['analysis_result']
            
    #         # 통합 설명문
    #         with st.container(border=True):
    #             st.markdown("#### 📄 통합 설명문")
    #             if 'annotation_info' in result and 'Explanation' in result['annotation_info']:
    #                 st.markdown(f"**{result['annotation_info']['Explanation']}**")
            
    #         # 카테고리 & 메타데이터
    #         col1, col2 = st.columns(2)
            
    #         with col1:
    #             with st.container(border=True):
    #                 st.markdown("##### 🏷️ 카테고리")
    #                 if 'category_info' in result:
    #                     cat_info = result['category_info']
                        
    #                     loc_labels = {1: "실내", 2: "실외", 3: "혼합"}
    #                     era_labels = {1: "전통", 2: "현대", 3: "혼합", 4: "기타"}
                        
    #                     st.write(f"**장소**: {loc_labels.get(cat_info.get('LocationCategory', 0), 'N/A')}")
    #                     st.write(f"**시대**: {era_labels.get(cat_info.get('EraCategory', 0), 'N/A')}")
            
    #         with col2:
    #             with st.container(border=True):
    #                 st.markdown("##### 📋 메타데이터")
    #                 if 'meta' in result:
    #                     meta = result['meta']
    #                     st.write(f"**크기**: {meta.get('width', 'N/A')} × {meta.get('height', 'N/A')} px")
    #                     st.write(f"**형식**: {meta.get('format', 'N/A')}")
            
    #         # 상세 설명문
    #         with st.container(border=True):
    #             st.markdown("#### ✍️ 상세 설명문")
                
    #             if 'annotation_info' in result:
    #                 ann_info = result['annotation_info']
                    
    #                 with st.expander("🎬 장면 설명", expanded=True):
    #                     st.write(ann_info.get('SceneExp', 'N/A'))
                    
    #                 with st.expander("🎨 색감 설명", expanded=True):
    #                     st.write(ann_info.get('ColortoneExp', 'N/A'))
                    
    #                 with st.expander("📐 구도 설명", expanded=True):
    #                     st.write(ann_info.get('CompositionExp', 'N/A'))
                    
    #                 with st.expander("👤 객체1 설명", expanded=True):
    #                     st.write(ann_info.get('ObjectExp1', 'N/A'))
                    
    #                 with st.expander("🏛️ 객체2 설명", expanded=True):
    #                     st.write(ann_info.get('ObjectExp2', 'N/A'))
    #     else:
    #         # Empty state
    #         with st.container(border=True):
    #             st.info("📝 이미지를 업로드하고 분석을 시작하면 결과가 여기에 표시됩니다.")
                
    #             # 높이 맞추기
    #             for _ in range(10):
    #                 st.write("")

with tab2:
    st.markdown("### 💾 JSON 데이터 관리")
    
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
            st.markdown("#### 📋 JSON 데이터 미리보기")
            
            # JSON 표시
            st.json(result, expanded=True)
        
        # 복사 가능한 텍스트
        with st.container(border=True):
            st.markdown("#### 📝 복사 가능한 JSON")
            
            # 어절 수 계산
            if 'annotation_info' in result:
                ann = result['annotation_info']
                total_words = sum([
                    len(ann.get(key, '').split()) 
                    for key in ['SceneExp', 'ColortoneExp', 'CompositionExp', 'ObjectExp1', 'ObjectExp2']
                ])
                st.info(f"📊 총 어절 수: {total_words}개")
            
            # 코드 블록으로 표시
            st.code(json_str, language="json")
    else:
        # Empty state
        with st.container(border=True):
            st.info("📝 분석을 완료하면 JSON 데이터를 다운로드할 수 있습니다.")
            
            # 샘플 JSON 표시
            with st.expander("💡 JSON 출력 예시"):
                sample_json = {
                    "meta": {
                        "width": 1920,
                        "height": 1080,
                        "format": "JPG"
                    },
                    "category_info": {
                        "LocationCategory": 2,
                        "EraCategory": 2
                    },
                    "annotation_info": {
                        "SceneExp": "예시 장면 설명",
                        "ColortoneExp": "예시 색감 설명",
                        "CompositionExp": "예시 구도 설명",
                        "ObjectExp1": "예시 객체1 설명",
                        "ObjectExp2": "예시 객체2 설명",
                        "Explanation": "통합 설명문"
                    }
                }
                st.json(sample_json)
