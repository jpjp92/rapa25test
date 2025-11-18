"""
카테고리 정의 - 한국적 배경 및 객체 생성 데이터

사용 가능한 카테고리:
    - LocationCategory: 실내/실외/혼합 구분
    - EraCategory: 전통/현대/혼합/기타 시대 구분
"""

# 카테고리 데이터 정의
CATEGORY_DATA = {
    "LocationCategory": [
        {"class": 1, "label": "실내"},
        {"class": 2, "label": "실외"},
        {"class": 3, "label": "혼합"}
    ],
    "EraCategory": [
        {"class": 1, "label": "전통"},
        {"class": 2, "label": "현대"},
        {"class": 3, "label": "혼합"},
        {"class": 4, "label": "기타"}
    ]
}

# 카테고리 한글 이름
CATEGORY_LABELS = {
    "LocationCategory": "장소 구분",
    "EraCategory": "시대 구분"
}


def get_category_by_label(category_name: str, label: str) -> dict:
    """
    라벨로 카테고리 정보 조회

    Args:
        category_name: 카테고리 이름 (예: "LocationCategory")
        label: 라벨 (예: "실외")

    Returns:
        {"class": 2, "label": "실외"}
    """
    categories = CATEGORY_DATA.get(category_name, [])
    for category in categories:
        if category["label"] == label:
            return category
    return None


def get_category_by_class(category_name: str, class_num: int) -> dict:
    """
    클래스 번호로 카테고리 정보 조회

    Args:
        category_name: 카테고리 이름 (예: "LocationCategory")
        class_num: 클래스 번호 (예: 2)

    Returns:
        {"class": 2, "label": "실외"}
    """
    categories = CATEGORY_DATA.get(category_name, [])
    for category in categories:
        if category["class"] == class_num:
            return category
    return None


if __name__ == "__main__":
    # 테스트
    print("=== 카테고리 데이터 ===")
    for category_name, items in CATEGORY_DATA.items():
        korean_name = CATEGORY_LABELS.get(category_name, category_name)
        print(f"\n{category_name} ({korean_name}):")
        for item in items:
            print(f"  - class {item['class']}: {item['label']}")

    # 조회 테스트
    print("\n=== 조회 테스트 ===")
    result = get_category_by_label("LocationCategory", "실외")
    print(f"LocationCategory '실외': {result}")

    result = get_category_by_class("EraCategory", 1)
    print(f"EraCategory class 1: {result}")
