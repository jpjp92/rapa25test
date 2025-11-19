"""
Logger - 날짜별 로그 관리 (raw_image25용)

특징:
- 날짜별 디렉토리 자동 생성 (logs/YYYY-MM-DD/)
- error.log: 에러만 상세 기록
- progress.jsonl: 성공/실패 여부만 기록
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any


class Logger:
    """
    날짜별 로그 관리

    구조:
        logs/
        ├── 2025-10-17/
        │   ├── error.log        # 에러 상세 로그
        │   └── progress.jsonl   # 진행 상황 (성공/실패)
        └── 2025-10-18/
            ├── error.log
            └── progress.jsonl
    """

    def __init__(self, base_dir: str = "logs"):
        """
        Args:
            base_dir: 로그 베이스 디렉토리
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 오늘 날짜의 로그 디렉토리
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.log_dir = self.base_dir / self.today
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 로그 파일 경로
        self.error_log = self.log_dir / "error.log"
        self.progress_log = self.log_dir / "progress.jsonl"

    def log_error(
        self,
        filename: str,
        error: str,
        worker_id: Optional[int] = None,
        **metadata
    ):
        """
        에러 상세 로그 기록

        Args:
            filename: 파일명
            error: 에러 메시지
            worker_id: Worker ID
            **metadata: 추가 메타데이터
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Worker ID 부분 조건부 추가
        worker_prefix = f"[Worker {worker_id}] " if worker_id else ""

        log_entry = (
            f"[{timestamp}] {worker_prefix}FILE: {filename}\n"
            f"ERROR: {error}\n"
        )

        # 메타데이터 추가
        if metadata:
            log_entry += f"METADATA: {json.dumps(metadata, ensure_ascii=False)}\n"

        log_entry += "-" * 80 + "\n"

        # 에러 로그 파일에 append
        with open(self.error_log, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            f.flush()

    def log_progress(
        self,
        filename: str,
        status: str,
        worker_id: Optional[int] = None,
        **metadata
    ):
        """
        진행 상황 로그 기록 (JSONL)

        Args:
            filename: 파일명
            status: 상태 (success, failed, skipped)
            worker_id: Worker ID
            **metadata: 추가 메타데이터
        """
        record = {
            "filename": filename,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "worker_id": worker_id,
            **metadata
        }

        # progress.jsonl에 append
        with open(self.progress_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            f.flush()

    def log_success(
        self,
        filename: str,
        worker_id: Optional[int] = None,
        record_id: Optional[str] = None,
        s3_key: Optional[str] = None,
        **metadata
    ):
        """
        성공 로그 기록

        Args:
            filename: 파일명
            worker_id: Worker ID
            record_id: DB record ID
            s3_key: S3 key
            **metadata: 추가 메타데이터
        """
        self.log_progress(
            filename=filename,
            status="success",
            worker_id=worker_id,
            record_id=record_id,
            s3_key=s3_key,
            **metadata
        )

    def log_failed(
        self,
        filename: str,
        error: str,
        worker_id: Optional[int] = None,
        **metadata
    ):
        """
        실패 로그 기록 (progress.jsonl + error.log)

        Args:
            filename: 파일명
            error: 에러 메시지
            worker_id: Worker ID
            **metadata: 추가 메타데이터
        """
        # 1. progress.jsonl에 실패 기록
        self.log_progress(
            filename=filename,
            status="failed",
            worker_id=worker_id,
            error=error,
            **metadata
        )

        # 2. error.log에 상세 기록
        self.log_error(
            filename=filename,
            error=error,
            worker_id=worker_id,
            **metadata
        )

    def log_skipped(
        self,
        filename: str,
        reason: str,
        worker_id: Optional[int] = None,
        **metadata
    ):
        """
        스킵 로그 기록

        Args:
            filename: 파일명
            reason: 스킵 사유
            worker_id: Worker ID
            **metadata: 추가 메타데이터
        """
        self.log_progress(
            filename=filename,
            status="skipped",
            worker_id=worker_id,
            reason=reason,
            **metadata
        )

    def get_today_stats(self) -> Dict[str, int]:
        """
        오늘 처리 통계 반환

        Returns:
            {'success': 123, 'failed': 5, 'skipped': 2}
        """
        stats = {'success': 0, 'failed': 0, 'skipped': 0}

        if not self.progress_log.exists():
            return stats

        with open(self.progress_log, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    status = record.get('status', 'unknown')
                    if status in stats:
                        stats[status] += 1
                except json.JSONDecodeError:
                    continue

        return stats

    def print_summary(self):
        """오늘 처리 통계 출력"""
        stats = self.get_today_stats()

        print(f"\n{'='*80}")
        print(f"📊 {self.today} 처리 통계")
        print(f"{'='*80}")
        print(f"  ✅ 성공: {stats['success']:,}개")
        print(f"  ❌ 실패: {stats['failed']:,}개")
        print(f"  ⏭️  스킵: {stats['skipped']:,}개")
        print(f"  📁 로그 디렉토리: {self.log_dir}")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    # 테스트
    logger = Logger()

    # 성공 로그
    logger.log_success(
        filename="test1.jpg",
        worker_id=1,
        record_id="uuid-123",
        s3_key="s3-key-123"
    )

    # 실패 로그
    logger.log_failed(
        filename="test2.jpg",
        error="Gemini API error occurred",
        worker_id=2
    )

    # 스킵 로그
    logger.log_skipped(
        filename="test3.jpg",
        reason="Already processed",
        worker_id=1
    )

    # 통계 출력
    logger.print_summary()
