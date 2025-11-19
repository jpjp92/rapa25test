"""
이미지 메타데이터 추출
PIL을 사용하여 이미지의 width, height, format 추출
"""

import os
from PIL import Image
from pathlib import Path
from typing import Dict


def extract_image_metadata(image_path: str) -> Dict:
    """
    이미지 메타데이터 추출

    Args:
        image_path: 이미지 파일 경로

    Returns:
        {
            'width': 1920,
            'height': 1080,
            'format': 'JPEG',
            'file_size': 2048576
        }

    Raises:
        FileNotFoundError: 이미지 파일이 없는 경우
        ValueError: 이미지를 열 수 없는 경우
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

    try:
        # 이미지 열기
        with Image.open(image_path) as img:
            width, height = img.size
            image_format = img.format or "UNKNOWN"

            # 포맷을 소문자로 통일
            if image_format == "JPEG":
                image_format = "jpg"  # JPEG는 jpg로 변환
            elif image_format != "UNKNOWN":
                image_format = image_format.lower()  # 나머지는 소문자

        # 파일 크기 가져오기
        file_size = os.path.getsize(image_path)

        metadata = {
            'width': width,
            'height': height,
            'format': image_format,
            'file_size': file_size
        }

        return metadata

    except Exception as e:
        raise ValueError(f"이미지 메타데이터를 추출할 수 없습니다: {str(e)}")


def is_valid_image(image_path: str) -> bool:
    """
    유효한 이미지 파일인지 확인

    Args:
        image_path: 이미지 파일 경로

    Returns:
        True if valid image, False otherwise
    """
    try:
        with Image.open(image_path) as img:
            img.verify()
        return True
    except Exception:
        return False


def get_image_dimensions(image_path: str) -> tuple:
    """
    이미지 크기 반환 (width, height)

    Args:
        image_path: 이미지 파일 경로

    Returns:
        (width, height) tuple
    """
    with Image.open(image_path) as img:
        return img.size


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("사용법: python image_metadata.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]

    try:
        print(f"📊 이미지 메타데이터 추출: {image_path}\n")

        metadata = extract_image_metadata(image_path)

        print(f"✅ 메타데이터:")
        print(f"  - 해상도: {metadata['width']} × {metadata['height']}")
        print(f"  - 포맷: {metadata['format']}")
        print(f"  - 파일 크기: {metadata['file_size']:,} bytes ({metadata['file_size'] / 1024 / 1024:.2f} MB)")

        # 유효성 검사
        is_valid = is_valid_image(image_path)
        print(f"  - 유효성: {'✅ 유효' if is_valid else '❌ 무효'}")

    except Exception as e:
        print(f"❌ 에러: {e}")
        sys.exit(1)
