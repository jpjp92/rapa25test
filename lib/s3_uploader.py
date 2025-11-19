"""
AWS S3 업로더 (raw_image용)
이미지 파일을 S3에 멀티파트 업로드

주요 기능:
    - 멀티파트 업로드 (8MB 이상)
    - 진행률 표시
    - 재시도 로직 (3회)
    - 업로드 성공 후 로컬 파일 삭제 (선택)

S3 경로 구조:
    s3://nanow/rapa25/data/raw_image/{s3_key}/{s3_key}.jpg
"""

import boto3
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from botocore.exceptions import ClientError
from botocore.config import Config
from boto3.s3.transfer import TransferConfig


class S3Uploader:
    """AWS S3 업로더 (멀티파트 업로드 지원)"""

    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = "ap-northeast-2"
    ):
        """
        S3Uploader 초기화

        Args:
            bucket_name: S3 버킷 이름
            aws_access_key_id: AWS Access Key (선택사항)
            aws_secret_access_key: AWS Secret Key (선택사항)
            region_name: AWS 리전 (기본: ap-northeast-2)
        """
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.base_path = "rapa25/data/raw_image"

        # boto3 Config 설정 (멀티파트 업로드 최적화)
        config = Config(
            max_pool_connections=50,  # 동시 연결 수 증가
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )

        # boto3 클라이언트 초기화
        if aws_access_key_id and aws_secret_access_key:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name,
                config=config
            )
        else:
            # 환경변수 또는 IAM 역할 사용
            self.s3_client = boto3.client('s3', region_name=region_name, config=config)

        # TransferConfig 설정 (멀티파트 업로드 최적화)
        self.transfer_config = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,  # 8MB 이상 멀티파트
            max_concurrency=10,  # 동시 업로드 스레드 수
            multipart_chunksize=8 * 1024 * 1024,  # 청크 크기 8MB
            use_threads=True
        )

        print(f"✅ S3 클라이언트 초기화: s3://{bucket_name}/{self.base_path}")

    def _create_progress_callback(self, file_size: int):
        """
        업로드 진행률 콜백 생성

        Args:
            file_size: 파일 크기 (bytes)

        Returns:
            진행률 콜백 함수
        """
        class ProgressCallback:
            def __init__(self, size):
                self._size = size
                self._uploaded = 0
                self._last_printed = 0

            def __call__(self, bytes_amount):
                self._uploaded += bytes_amount
                percentage = (self._uploaded / self._size) * 100

                # 10% 단위로만 출력
                if int(percentage / 10) > int(self._last_printed / 10):
                    print(f'   진행률: {percentage:.0f}% ({self._uploaded / (1024*1024):.1f}/{self._size / (1024*1024):.1f} MB)')
                    self._last_printed = percentage

        return ProgressCallback(file_size)

    def upload_image(
        self,
        local_path: str,
        s3_key: str,
        filename: str,
        max_retries: int = 3,
        cleanup_after_upload: bool = False
    ) -> Dict:
        """
        이미지를 S3에 업로드 (멀티파트 + 재시도 + 진행률 표시)

        Args:
            local_path: 로컬 파일 경로
            s3_key: S3 저장 경로 식별자 (UUID v7)
            filename: 원본 파일명
            max_retries: 최대 재시도 횟수 (기본: 3)
            cleanup_after_upload: 업로드 성공 후 로컬 파일 삭제 여부 (기본: False)

        Returns:
            {
                "success": True,
                "s3_path": "s3://nanow/rapa25/data/raw_image/{s3_key}/{uuid}.jpg",
                "bucket": "nanow",
                "key": "rapa25/data/raw_image/{s3_key}/{uuid}.jpg",
                "file_size": 1024000,
                "upload_timestamp": "2025-01-19T12:34:56"
            }
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {local_path}")

        # 파일 확장자 추출
        file_extension = Path(filename).suffix or '.jpg'

        # S3 키 생성: rapa25/data/raw_image/{s3_key}/{s3_key}{extension}
        s3_object_key = f"{self.base_path}/{s3_key}/{s3_key}{file_extension}"

        # 파일 크기
        file_size = os.path.getsize(local_path)
        file_size_mb = file_size / (1024 * 1024)

        # 재시도 로직
        for attempt in range(max_retries):
            try:
                print(f"📤 업로드 중 ({attempt + 1}/{max_retries}): {Path(local_path).name} ({file_size_mb:.1f} MB)")
                print(f"   → s3://{self.bucket_name}/{s3_object_key}")

                # 멀티파트 업로드 (진행률 표시 포함)
                self.s3_client.upload_file(
                    local_path,
                    self.bucket_name,
                    s3_object_key,
                    ExtraArgs={'ContentType': self._get_content_type(file_extension)},
                    Config=self.transfer_config,
                    Callback=self._create_progress_callback(file_size)
                )

                # S3 경로 생성
                s3_path = f"s3://{self.bucket_name}/{s3_object_key}"

                upload_info = {
                    "success": True,
                    "s3_path": s3_path,
                    "bucket": self.bucket_name,
                    "key": s3_object_key,
                    "file_size": file_size,
                    "upload_timestamp": datetime.now().isoformat()
                }

                print(f"✅ 업로드 성공")

                # 업로드 성공 후 로컬 파일 삭제
                if cleanup_after_upload:
                    try:
                        Path(local_path).unlink()
                        print(f"🗑️  로컬 파일 삭제: {local_path}")
                    except Exception as e:
                        print(f"⚠️  파일 삭제 실패: {e}")

                return upload_info

            except ClientError as e:
                error_code = e.response['Error']['Code']
                print(f"❌ 업로드 실패: {error_code}")

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 지수 백오프
                    print(f"⏳ {wait_time}초 후 재시도...")
                    import time
                    time.sleep(wait_time)
                else:
                    print(f"❌ 최대 재시도 횟수 초과")
                    raise

            except Exception as e:
                print(f"❌ 예상치 못한 오류: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⏳ {wait_time}초 후 재시도...")
                    import time
                    time.sleep(wait_time)
                else:
                    raise

        return {
            "success": False,
            "s3_path": None,
            "bucket": self.bucket_name,
            "key": s3_object_key,
            "file_size": file_size,
            "upload_timestamp": datetime.now().isoformat()
        }

    def _get_content_type(self, file_extension: str) -> str:
        """
        파일 확장자로 Content-Type 반환

        Args:
            file_extension: 파일 확장자 (.jpg, .png 등)

        Returns:
            Content-Type 문자열
        """
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff'
        }

        return content_types.get(file_extension.lower(), 'application/octet-stream')

    def delete_image(self, s3_key: str, filename: str) -> bool:
        """
        S3에서 이미지 삭제

        Args:
            s3_key: S3 저장 경로 식별자 (UUID v7)
            filename: 원본 파일명

        Returns:
            True if deleted, False otherwise
        """
        file_extension = Path(filename).suffix or '.jpg'
        s3_object_key = f"rapa25/data/raw_image/{s3_key}/{s3_key}{file_extension}"

        try:
            print(f"🗑️  S3 삭제: {s3_object_key}")
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_object_key
            )
            print(f"✅ S3 삭제 완료")
            return True

        except Exception as e:
            print(f"❌ S3 삭제 실패: {e}")
            return False

    def check_exists(self, s3_key: str, filename: str) -> bool:
        """
        S3에 파일이 존재하는지 확인

        Args:
            s3_key: S3 저장 경로 식별자 (UUID v7)
            filename: 원본 파일명

        Returns:
            True if exists, False otherwise
        """
        file_extension = Path(filename).suffix or '.jpg'
        s3_object_key = f"rapa25/data/raw_image/{s3_key}/{s3_key}{file_extension}"

        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_object_key
            )
            return True
        except Exception:
            return False


# 사용 예시
if __name__ == "__main__":
    import sys

    # S3 업로더 초기화
    uploader = S3Uploader(
        bucket_name=os.getenv("S3_BUCKET", "nanow"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "ap-northeast-2")
    )

    if len(sys.argv) < 3:
        print("사용법: python s3_uploader.py <local_path> <s3_key>")
        sys.exit(1)

    local_path = sys.argv[1]
    s3_key = sys.argv[2]

    # 파일명 추출
    filename = Path(local_path).name

    try:
        # 업로드 테스트
        upload_info = uploader.upload_image(
            local_path=local_path,
            s3_key=s3_key,
            filename=filename
        )

        print("\n✅ 업로드 정보:")
        print(f"  - S3 경로: {upload_info['s3_path']}")
        print(f"  - Bucket: {upload_info['bucket']}")
        print(f"  - Key: {upload_info['key']}")
        print(f"  - 파일 크기: {upload_info['file_size']:,} bytes")
        print(f"  - 업로드 시각: {upload_info['upload_timestamp']}")

        # 존재 확인
        exists = uploader.check_exists(s3_key, filename)
        print(f"\n📦 S3 존재 확인: {'✅ 존재함' if exists else '❌ 없음'}")

    except Exception as e:
        print(f"\n❌ 에러: {e}")
        sys.exit(1)
