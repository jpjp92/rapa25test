"""
Progress Tracker - 대규모 배치 처리를 위한 진행 상황 추적 (raw_image25용)

특징:
- JSONL 형식 (append-only, 크래시 안전)
- In-memory cache로 빠른 조회
- Resume 기능 (중단 후 재시작 가능)
- 실패 파일 자동 추적
- 날짜별 로그 관리
"""

import os
import json
from datetime import datetime
from typing import Dict, Set, Optional, Any
from pathlib import Path
from .logger import Logger


class ProgressTracker:
    """
    진행 상황 추적 및 Resume 기능 제공

    파일 형식 (JSONL):
        {"filename": "image1.jpg", "status": "success", "timestamp": "2025-10-16T10:00:00", "record_id": "uuid-xxx"}
        {"filename": "image2.jpg", "status": "failed", "timestamp": "2025-10-16T10:00:30", "error": "Timeout"}
        {"filename": "image3.jpg", "status": "success", "timestamp": "2025-10-16T10:01:00", "record_id": "uuid-yyy"}
    """

    def __init__(self, progress_file: str = "tmp/progress.jsonl", use_logger: bool = True):
        """
        Args:
            progress_file: 진행 상황 저장 파일 경로 (하위 호환성)
            use_logger: 새 Logger 사용 여부 (True: logs/날짜/, False: tmp/)
        """
        self.use_logger = use_logger

        if use_logger:
            # 새 로거 사용 (logs/YYYY-MM-DD/)
            self.logger = Logger()
            self.progress_file = self.logger.progress_log
        else:
            # 기존 방식 (tmp/progress.jsonl)
            self.logger = None
            self.progress_file = Path(progress_file)
            self.progress_file.parent.mkdir(parents=True, exist_ok=True)

        # In-memory cache (현재 실행에서만 사용, 로그 로딩 안 함)
        self.processed_files: Set[str] = set()
        self.failed_files: Dict[str, str] = {}  # {filename: error_message}
        self.records: Dict[str, Dict] = {}  # {filename: record_data}

        # ⚠️ 이전 로그는 로딩하지 않음 - DB 체크로 중복 관리
        print(f"📂 Progress Tracker 초기화 (로그 전용 모드)")
        print(f"   로그 파일: {self.progress_file}")
        print(f"   ⚠️  중복 체크는 DB에서만 수행")

    def _load_progress(self):
        """이전 진행 상황 로딩 비활성화 - DB 중복 체크로 대체"""
        # 이전 로그를 로딩하지 않음
        # 모든 중복 체크는 DB에서 수행
        pass

    def is_processed(self, filename: str) -> bool:
        """
        이미 처리된 파일인지 확인

        Args:
            filename: 파일명

        Returns:
            True if already processed successfully
        """
        return filename in self.processed_files

    def is_failed(self, filename: str) -> bool:
        """
        이전에 실패한 파일인지 확인

        Args:
            filename: 파일명

        Returns:
            True if previously failed
        """
        return filename in self.failed_files

    def get_error(self, filename: str) -> Optional[str]:
        """
        실패 에러 메시지 조회

        Args:
            filename: 파일명

        Returns:
            에러 메시지 (실패 기록이 없으면 None)
        """
        return self.failed_files.get(filename)

    def save_success(self, filename: str, record_id: str = None, s3_key: str = None, **kwargs):
        """
        성공 기록 저장

        Args:
            filename: 파일명
            record_id: DB record ID
            s3_key: S3 key
            **kwargs: 추가 메타데이터 (worker_id 포함)
        """
        # 새 로거 사용 시
        if self.use_logger and self.logger:
            self.logger.log_success(
                filename=filename,
                record_id=record_id,
                s3_key=s3_key,
                **kwargs
            )
        else:
            # 기존 방식
            record = {
                'filename': filename,
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'record_id': record_id,
                's3_key': s3_key,
                **kwargs
            }
            self._append_record(record)

        # In-memory cache 업데이트
        self.processed_files.add(filename)
        self.records[filename] = {
            'filename': filename,
            'status': 'success',
            'record_id': record_id,
            's3_key': s3_key,
            **kwargs
        }

        if filename in self.failed_files:
            del self.failed_files[filename]

    def save_failed(self, filename: str, error: str, **kwargs):
        """
        실패 기록 저장 (progress.jsonl + error.log)

        Args:
            filename: 파일명
            error: 에러 메시지
            **kwargs: 추가 메타데이터 (worker_id 포함)
        """
        # 새 로거 사용 시 (error.log에도 상세 기록)
        if self.use_logger and self.logger:
            self.logger.log_failed(
                filename=filename,
                error=error,
                **kwargs
            )
        else:
            # 기존 방식
            record = {
                'filename': filename,
                'status': 'failed',
                'timestamp': datetime.now().isoformat(),
                'error': error,
                **kwargs
            }
            self._append_record(record)

        # In-memory cache 업데이트
        self.failed_files[filename] = error

        if filename in self.processed_files:
            self.processed_files.remove(filename)

    def save_skipped(self, filename: str, reason: str = 'duplicate', **kwargs):
        """
        스킵 기록 저장 (중복 등)

        Args:
            filename: 파일명
            reason: 스킵 사유
            **kwargs: 추가 메타데이터 (worker_id 포함)
        """
        # 새 로거 사용 시
        if self.use_logger and self.logger:
            self.logger.log_skipped(
                filename=filename,
                reason=reason,
                **kwargs
            )
        else:
            # 기존 방식
            record = {
                'filename': filename,
                'status': 'skipped',
                'timestamp': datetime.now().isoformat(),
                'reason': reason,
                **kwargs
            }
            self._append_record(record)

    def _append_record(self, record: Dict[str, Any]):
        """
        레코드를 JSONL 파일에 append (atomic write)

        Args:
            record: 저장할 레코드
        """
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            f.flush()  # 즉시 디스크에 기록

    def get_stats(self) -> Dict[str, int]:
        """
        현재 통계 반환

        Returns:
            {'success': 123, 'failed': 5}
        """
        return {
            'success': len(self.processed_files),
            'failed': len(self.failed_files),
        }

    def get_remaining_files(self, all_files: list) -> list:
        """
        아직 처리하지 않은 파일 목록 반환

        Args:
            all_files: 전체 파일 목록

        Returns:
            처리되지 않은 파일 목록
        """
        return [f for f in all_files if not self.is_processed(f)]

    def print_summary(self, elapsed_seconds: float = None):
        """
        진행 상황 요약 출력

        Args:
            elapsed_seconds: 경과 시간 (초), None이면 시간 표시 안 함
        """
        stats = self.get_stats()

        print(f"\n{'='*80}")
        print(f"📊 진행 상황 요약")
        print(f"{'='*80}")
        print(f"  ✅ 성공: {stats['success']:,}개")
        print(f"  ❌ 실패: {stats['failed']:,}개")

        if elapsed_seconds is not None:
            formatted_time = self._format_time(elapsed_seconds)
            total_processed = stats['success'] + stats['failed']
            if total_processed > 0 and elapsed_seconds > 0:
                speed = total_processed / elapsed_seconds
                print(f"  ⏱️  소요 시간: {formatted_time}")
                print(f"  ⚡ 평균 속도: {speed:.2f}개/초")

        print(f"  📁 진행 파일: {self.progress_file}")
        print(f"{'='*80}\n")

    @staticmethod
    def _format_time(seconds: float) -> str:
        """
        초를 보기 좋은 형식으로 변환

        Args:
            seconds: 초 단위 시간

        Returns:
            포맷된 시간 문자열 (예: "36초", "5분 30초", "1시간 15분")
        """
        if seconds < 60:
            return f"{seconds:.0f}초"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = int(seconds % 60)
            return f"{minutes}분 {remaining_seconds}초"
        else:
            hours = int(seconds // 3600)
            remaining_minutes = int((seconds % 3600) // 60)
            return f"{hours}시간 {remaining_minutes}분"


if __name__ == "__main__":
    # 테스트
    tracker = ProgressTracker("tmp/test_progress.jsonl")

    # 성공 기록
    tracker.save_success("test1.jpg", record_id="uuid-123", s3_key="s3-key-123")
    tracker.save_success("test2.jpg", record_id="uuid-456", s3_key="s3-key-456")

    # 실패 기록
    tracker.save_failed("test3.jpg", error="Gemini API timeout")

    # 스킵 기록
    tracker.save_skipped("test4.jpg", reason="duplicate")

    # 확인
    print(f"test1.jpg 처리됨? {tracker.is_processed('test1.jpg')}")
    print(f"test3.jpg 실패? {tracker.is_failed('test3.jpg')}")
    print(f"test3.jpg 에러: {tracker.get_error('test3.jpg')}")

    # 요약
    tracker.print_summary()

    # 남은 파일
    all_files = ["test1.jpg", "test2.jpg", "test3.jpg", "test4.jpg", "test5.jpg"]
    remaining = tracker.get_remaining_files(all_files)
    print(f"남은 파일: {remaining}")
