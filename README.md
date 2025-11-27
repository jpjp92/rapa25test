# 🖼️ 배경 이미지 분석기

Google Gemini 2.5 Flash를 활용하여 한국적 배경 이미지를 분석하고 구조화된 설명문을 생성하는 Streamlit 웹 애플리케이션입니다.

## 주요 기능

- **이미지 분석**: Gemini 2.5 Flash 모델을 사용한 이미지 분석
- **카테고리 분류**: 장소(실내/실외/혼합) 및 시대(전통/현대/혼합) 자동 분류
- **설명문 생성**: 장면, 색감, 구도, 객체 설명문 자동 생성
- **한국전통색상 지원**: 전통 시대 이미지에 한국전통표준색 적용
- **JSON 출력**: 분석 결과를 구조화된 JSON 형식으로 다운로드

## 설치 방법

### 1. 저장소 클론

```bash
git clone <repository-url>
cd <project-directory>
```

### 2. 가상환경 생성 및 활성화

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 Google API 키를 설정합니다:

```env
GOOGLE_API_KEY_IMAGE=your_google_api_key_here
```

## 실행 방법

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

## 프로젝트 구조

```
project/
├── app.py                    # 메인 Streamlit 애플리케이션
├── lib/
│   ├── gemini_analyzer.py    # Gemini API 분석기 클래스
│   ├── gemini_prompt.py      # 프롬프트 생성 함수
│   └── categories.py         # 카테고리 정의
├── temp_images/              # 임시 이미지 저장 디렉토리
├── .env                      # 환경 변수 (API 키)
├── requirements.txt          # Python 의존성
└── README.md
```

## 사용 방법

1. **이미지 업로드**: JPG, PNG, WEBP 형식의 이미지를 업로드합니다
2. **프롬프트 설정**: 필요시 분석 프롬프트를 편집합니다
3. **분석 시작**: "분석 시작" 버튼을 클릭합니다
4. **결과 확인**: 분석 결과를 확인하고 JSON으로 다운로드합니다

## 출력 형식

```json
{
  "meta": {
    "width": 1920,
    "height": 1080,
    "format": "JPEG"
  },
  "category_info": {
    "LocationCategory": 2,
    "EraCategory": 2
  },
  "annotation_info": {
    "SceneExp": "장면 설명...",
    "ColortoneExp": "색감 설명...",
    "CompositionExp": "구도 설명...",
    "ObjectExp1": "객체1 설명...",
    "ObjectExp2": "객체2 설명...",
    "Explanation": "통합 설명문..."
  }
}
```

## 카테고리 정의

### LocationCategory (장소 구분)
| 값 | 라벨 | 설명 |
|---|------|------|
| 1 | 실내 | 건물 내부, 방, 실내 공간 |
| 2 | 실외 | 야외, 자연, 거리, 건물 외부 |
| 3 | 혼합 | 실내와 실외가 동시에 보이는 경우 |
| 4 | 기타 | 일러스트, 애니메이션 등 |

### EraCategory (시대 구분)
| 값 | 라벨 | 설명 |
|---|------|------|
| 1 | 전통 | 전통 요소만 존재 |
| 2 | 현대 | 현대 요소만 존재 |
| 3 | 혼합 | 전통과 현대 요소 공존 |
| 4 | 기타 | SF/판타지, 자연물만 있는 경우 |

## 의존성

- streamlit
- google-generativeai
- Pillow
- python-dotenv

## 라이선스

MIT License
