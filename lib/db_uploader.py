"""
PostgreSQL 데이터베이스 업로더 (raw_image용)
rapa25.raw_image 테이블에 이미지 분석 결과 저장
"""

import os
import json
from typing import Dict, Optional
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv


class DatabaseUploader:
    """PostgreSQL 데이터베이스 업로더"""

    def __init__(self, database_url: Optional[str] = None):
        """
        DatabaseUploader 초기화

        Args:
            database_url: PostgreSQL 연결 문자열 (None이면 환경변수 DATABASE_URL 사용)
        """
        load_dotenv()

        self.database_url = database_url or os.getenv('DATABASE_URL')

        if not self.database_url:
            raise ValueError("DATABASE_URL not found in environment variables")

        # SQLAlchemy 엔진 생성
        self.engine = create_engine(
            self.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True  # 연결 상태 자동 체크
        )

        print(f'✅ DB 연결 초기화: {self.database_url.split("@")[1]}')

    def check_duplicate(self, file_hash: str) -> bool:
        """
        파일 해시로 중복 체크

        Args:
            file_hash: 파일 해시값

        Returns:
            중복 여부 (True: 중복됨, False: 중복 아님)
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT id FROM rapa25.raw_image WHERE file_hash = :hash LIMIT 1"),
                {"hash": file_hash}
            )
            exists = result.fetchone() is not None

        if exists:
            print(f'⚠️  중복 파일 발견: {file_hash[:16]}...')

        return exists

    def check_duplicate_by_filename(self, filename: str) -> bool:
        """
        파일명으로 중복 체크 (다운로드 전 빠른 검증용)

        Args:
            filename: 파일명 (예: "02_01_02_000002.jpg")

        Returns:
            중복 여부 (True: 중복됨, False: 중복 아님)
        """
        with self.engine.connect() as conn:
            # raw_storage.original.file_path에서 파일명 추출하여 비교
            result = conn.execute(
                text("""
                    SELECT id
                    FROM rapa25.raw_image
                    WHERE raw_storage->'original'->>'file_path' LIKE :filename_pattern
                    LIMIT 1
                """),
                {"filename_pattern": f"%{filename}"}
            )
            exists = result.fetchone() is not None

        if exists:
            print(f'⚠️  DB에서 파일명 중복 발견: {filename}')

        return exists

    def check_duplicate_batch(self, filenames: list[str], remote_dir: str = None) -> set[str]:
        """
        여러 파일명을 배치로 중복 체크 (대량 처리 최적화)

        Args:
            filenames: 파일명 리스트 (상대 경로, 예: "디렉토리/파일.jpg")
            remote_dir: FTP 원격 디렉토리 (전체 경로 매칭용)

        Returns:
            DB에 이미 존재하는 파일명 집합 (set)
        """
        if not filenames:
            return set()

        with self.engine.connect() as conn:
            if remote_dir:
                # 전체 경로 매칭 (raw_video25 방식)
                full_paths = [f"{remote_dir}/{fn}" for fn in filenames]
                
                result = conn.execute(
                    text("""
                        SELECT raw_storage->'original'->>'file_path' AS full_path
                        FROM rapa25.raw_image
                        WHERE raw_storage->'original'->>'file_path' = ANY(:full_paths)
                    """),
                    {"full_paths": full_paths}
                )
                
                # 전체 경로에서 remote_dir 제거하여 상대 경로로 반환
                existing_full_paths = {row[0] for row in result.fetchall()}
                existing_files = {
                    path.replace(f"{remote_dir}/", "") 
                    for path in existing_full_paths
                }
            else:
                # 기존 부분 매칭 방식 (하위 호환성)
                result = conn.execute(
                    text("""
                        SELECT DISTINCT 
                            regexp_replace(
                                raw_storage->'original'->>'file_path',
                                '^.*/FTP/RAPA2025/2\\.한국적배경및객체생성데이터/',
                                ''
                            ) AS relative_path
                        FROM rapa25.raw_image
                        WHERE raw_storage->'original'->>'file_path' LIKE ANY(:patterns)
                    """),
                    {"patterns": [f"%{fn}" for fn in filenames]}
                )
                
                existing_files = {row[0] for row in result.fetchall()}

        if existing_files:
            print(f'⚠️  DB에 이미 존재하는 파일: {len(existing_files)}개')

        return existing_files

    def get_next_file_id(self) -> int:
        """
        raw_meta.File_info.Id의 다음 번호 생성 (갭 재사용 방식)

        동작:
        1. 삭제된 번호(갭)가 있으면 가장 작은 번호 재사용
        2. 갭이 없으면 max(Id) + 1

        Returns:
            다음 Id 번호 (갭 재사용 또는 max+1)
        """
        try:
            with self.engine.connect() as conn:
                # 1. 빈 번호(갭) 찾기 (최적화된 쿼리)
                result = conn.execute(
                    text("""
                        WITH existing_ids AS (
                            SELECT CAST(raw_meta->'File_info'->>'Id' AS INTEGER) AS id
                            FROM rapa25.raw_image
                            WHERE raw_meta IS NOT NULL
                            AND raw_meta->'File_info'->>'Id' IS NOT NULL
                            AND raw_meta->'File_info'->>'Id' ~ '^[0-9]+$'
                            ORDER BY id
                        ),
                        numbered AS (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (ORDER BY id) AS row_num
                            FROM existing_ids
                        )
                        SELECT row_num AS gap_id
                        FROM numbered
                        WHERE id != row_num
                        ORDER BY row_num
                        LIMIT 1
                    """)
                )

                gap_row = result.fetchone()

                # 2. 갭이 있으면 반환
                if gap_row is not None:
                    gap_id = gap_row[0]
                    print(f'🔄 갭 재사용: Id={gap_id}')
                    return gap_id

                # 3. 갭이 없으면 max + 1
                result = conn.execute(
                    text("""
                        SELECT COALESCE(
                            MAX(CAST(raw_meta->'File_info'->>'Id' AS INTEGER)),
                            0
                        ) + 1 AS next_id
                        FROM rapa25.raw_image
                        WHERE raw_meta IS NOT NULL
                        AND raw_meta->'File_info'->>'Id' IS NOT NULL
                        AND raw_meta->'File_info'->>'Id' ~ '^[0-9]+$'
                    """)
                )
                next_id = result.fetchone()[0]
                return next_id

        except Exception as e:
            print(f'⚠️  next_id 조회 실패, 기본값 1 사용: {e}')
            return 1

    def upload_image_result(
        self,
        filename: str,
        s3_key: str,
        file_hash: str,
        raw_storage: Dict,
        raw_gemini: Dict,
        raw_meta: Dict,
        status: str = "정상"
    ) -> Optional[str]:
        """
        이미지 분석 결과를 DB에 저장

        Args:
            filename: 원본 파일명
            s3_key: S3 저장 경로 식별자 (UUID v7)
            file_hash: 파일 해시값
            raw_storage: 원본 파일 및 S3 정보
            raw_gemini: Gemini 분석 결과
            raw_meta: 메타데이터 정보
            status: 파일 상태 (정상/오류)

        Returns:
            생성된 레코드 ID (UUID) 또는 None (실패 시)
        """
        try:
            print(f'💾 DB INSERT 시작...')

            with self.engine.begin() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO rapa25.raw_image (
                            s3_key,
                            file_hash,
                            status,
                            raw_storage,
                            raw_gemini,
                            raw_meta
                        ) VALUES (
                            CAST(:s3_key AS uuid),
                            :file_hash,
                            :status,
                            CAST(:raw_storage AS jsonb),
                            CAST(:raw_gemini AS jsonb),
                            CAST(:raw_meta AS jsonb)
                        )
                        ON CONFLICT ((raw_storage->'original'->>'file_path'), file_hash) DO NOTHING
                        RETURNING id
                    """),
                    {
                        "s3_key": s3_key,
                        "file_hash": file_hash,
                        "status": status,
                        "raw_storage": json.dumps(raw_storage, ensure_ascii=False),
                        "raw_gemini": json.dumps(raw_gemini, ensure_ascii=False),
                        "raw_meta": json.dumps(raw_meta, ensure_ascii=False)
                    }
                )

                row = result.fetchone()

                # ON CONFLICT로 인해 아무것도 삽입되지 않으면 None 반환
                if row is None:
                    print(f'⚠️  중복 파일로 인해 INSERT 건너뜀 (file_hash 충돌)')
                    return None

                record_id = row[0]
                print(f'✅ DB INSERT 성공: {record_id}')

                return str(record_id)

        except IntegrityError as e:
            print(f'❌ DB 무결성 오류 (중복 또는 제약 위반): {e}')
            return None

        except Exception as e:
            print(f'❌ DB INSERT 실패: {e}')
            return None

    def get_record_by_hash(self, file_hash: str) -> Optional[Dict]:
        """
        파일 해시로 레코드 조회

        Args:
            file_hash: 파일 해시값

        Returns:
            레코드 딕셔너리 또는 None
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM rapa25.raw_image WHERE file_hash = :hash LIMIT 1"),
                {"hash": file_hash}
            )
            row = result.fetchone()

            if row:
                return dict(row._mapping)

        return None

    def check_duplicate_by_path_and_hash(self, file_path: str, file_hash: str) -> Optional[Dict]:
        """
        경로와 해시 조합으로 중복 확인
        
        같은 해시라도 경로가 다르면 별도 데이터로 처리
        (예: 다른 에피소드의 같은 장면)

        Args:
            file_path: 전체 파일 경로 (예: /FTP/.../147회/u_000109.jpg)
            file_hash: 파일 해시값

        Returns:
            레코드 딕셔너리 또는 None
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, file_hash, raw_storage->'original'->>'file_path' as path
                    FROM rapa25.raw_image 
                    WHERE raw_storage->'original'->>'file_path' = :path
                    AND file_hash = :hash
                    LIMIT 1
                """),
                {"path": file_path, "hash": file_hash}
            )
            row = result.fetchone()

            if row:
                return dict(row._mapping)

        return None

    def test_connection(self) -> bool:
        """
        DB 연결 테스트

        Returns:
            연결 성공 여부
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                print(f'✅ DB 연결 성공')
                print(f'   PostgreSQL 버전: {version.split(",")[0]}')
                return True

        except Exception as e:
            print(f'❌ DB 연결 실패: {e}')
            return False


# 사용 예시
if __name__ == "__main__":
    try:
        # DB 업로더 생성
        uploader = DatabaseUploader()

        # 연결 테스트
        if uploader.test_connection():
            print("\n✅ DB 모듈 준비 완료!")
            print("\n사용 예시:")
            print("record_id = uploader.upload_image_result(")
            print("    filename='test.jpg',")
            print("    s3_key='uuid-xxx',")
            print("    file_hash='abc123...',")
            print("    raw_storage={...},")
            print("    raw_gemini={...},")
            print("    raw_meta={...}")
            print(")")

    except Exception as e:
        print(f"\n❌ 오류: {e}")
