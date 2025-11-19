"""
NAS FTP 클라이언트 (raw_image25용)
NAS 서버에 연결하여 원천 이미지 데이터 다운로드

사용법 (터미널):
    # 단독 실행 - FTP 연결 테스트 및 파일 목록 확인
    cd /opt/jupyter/rapa25/raw_image25/lib
    python ftp_client.py

    # 또는 모듈로 사용
    from lib.ftp_client import FTPClient, create_ftp_client_from_env

주요 기능:
    - NAS FTP 서버 연결
    - 디렉토리 파일 목록 조회 (확장자 필터링)
    - 단일/일괄 파일 다운로드
    - Context manager 지원 (자동 연결/종료)

환경 변수 (.env):
    FTP_HOST, FTP_USER, FTP_PASSWORD, FTP_PORT
"""

import os
from ftplib import FTP
from pathlib import Path
from typing import List, Optional
from datetime import datetime


class FTPClient:
    """NAS FTP 연결 및 파일 다운로드"""

    def __init__(self, host: str, user: str, password: str, port: int = 21):
        """
        FTP 클라이언트 초기화

        Args:
            host: FTP 호스트 주소
            user: FTP 사용자명
            password: FTP 비밀번호
            port: FTP 포트 (기본값: 21)
        """
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.ftp = None
        self.connected = False

    def connect(self) -> bool:
        """
        FTP 서버에 연결

        Returns:
            연결 성공 여부
        """
        try:
            print(f"🔌 FTP 연결 중... {self.host}:{self.port}")
            self.ftp = FTP()
            self.ftp.connect(self.host, self.port, timeout=30)
            self.ftp.login(self.user, self.password)
            self.ftp.encoding = 'utf-8'
            self.connected = True
            print(f"✅ FTP 연결 성공: {self.ftp.getwelcome()}")
            return True
        except Exception as e:
            print(f"❌ FTP 연결 실패: {e}")
            self.connected = False
            return False
    
    def reconnect(self) -> bool:
        """
        FTP 재연결 시도
        
        Returns:
            재연결 성공 여부
        """
        print("🔄 FTP 재연결 시도 중...")
        self.close()
        return self.connect()

    def list_files(self, remote_dir: str, extension: Optional[str] = None, recursive: bool = True) -> List[str]:
        """
        원격 디렉토리의 파일 목록 조회 (재귀 탐색 지원)

        Args:
            remote_dir: 원격 디렉토리 경로
            extension: 파일 확장자 필터 (예: '.jpg')
            recursive: 하위 디렉토리 재귀 탐색 여부 (기본: True)

        Returns:
            파일명 리스트 (재귀일 경우 상대 경로 포함)
        """
        if not self.connected:
            print("❌ FTP 연결되지 않음")
            return []

        try:
            print(f"📂 디렉토리 조회: {remote_dir}")
            
            if recursive:
                # 재귀적으로 모든 하위 디렉토리 탐색
                return self._list_files_recursive(remote_dir, extension)
            else:
                # 현재 디렉토리만 조회
                return self._list_files_single(remote_dir, extension)

        except Exception as e:
            print(f"❌ 파일 목록 조회 실패: {e}")
            return []
    
    def _list_files_single(self, remote_dir: str, extension: Optional[str] = None) -> List[str]:
        """단일 디렉토리 파일 목록 조회 (재귀 없음)"""
        self.ftp.cwd(remote_dir)

        # 파일 목록 가져오기
        files = []
        self.ftp.retrlines('LIST', lambda x: files.append(x))

        # 파일명만 추출 (디렉토리 제외)
        file_names = []
        for file_info in files:
            parts = file_info.split()
            if len(parts) >= 9:
                # 파일인지 확인 (디렉토리는 'd'로 시작)
                if not file_info.startswith('d'):
                    filename = ' '.join(parts[8:])  # 파일명 추출

                    # 확장자 필터링
                    if extension:
                        if filename.lower().endswith(extension.lower()):
                            file_names.append(filename)
                    else:
                        file_names.append(filename)

        return file_names
    
    def _list_files_recursive(self, remote_dir: str, extension: Optional[str] = None, base_dir: str = None, depth: int = 0, max_depth: int = 10) -> List[str]:
        """재귀적으로 하위 디렉토리 탐색"""
        if depth >= max_depth:
            return []
        
        if base_dir is None:
            base_dir = remote_dir
        
        all_files = []
        
        try:
            self.ftp.cwd(remote_dir)
            
            # 현재 디렉토리의 항목 목록
            items = []
            self.ftp.retrlines('LIST', lambda x: items.append(x))
            
            for item_info in items:
                parts = item_info.split()
                if len(parts) >= 9:
                    item_name = ' '.join(parts[8:])
                    
                    # 숨김 파일 제외
                    if item_name.startswith('.'):
                        continue
                    
                    # 디렉토리인 경우
                    if item_info.startswith('d'):
                        # 하위 디렉토리 재귀 탐색
                        subdir_path = f"{remote_dir}/{item_name}".replace('//', '/')
                        sub_files = self._list_files_recursive(subdir_path, extension, base_dir, depth + 1, max_depth)
                        all_files.extend(sub_files)
                    
                    # 파일인 경우
                    else:
                        # 확장자 필터링
                        if extension:
                            if item_name.lower().endswith(extension.lower()):
                                # 상대 경로 포함한 파일명
                                relative_path = remote_dir.replace(base_dir, '').strip('/')
                                if relative_path:
                                    file_path = f"{relative_path}/{item_name}"
                                else:
                                    file_path = item_name
                                all_files.append(file_path)
                        else:
                            relative_path = remote_dir.replace(base_dir, '').strip('/')
                            if relative_path:
                                file_path = f"{relative_path}/{item_name}"
                            else:
                                file_path = item_name
                            all_files.append(file_path)
            
            # 루트 호출에서만 결과 출력
            if depth == 0:
                print(f"✅ 파일 {len(all_files)}개 발견")
            
        except Exception as e:
            if depth == 0:
                print(f"❌ 디렉토리 탐색 실패 {remote_dir}: {e}")
        
        return all_files

    def download_file(self, remote_dir: str, filename: str, local_path: str, max_retries: int = 3) -> Optional[str]:
        """
        파일 다운로드 (상대 경로 지원 + 재시도 로직)

        Args:
            remote_dir: 원격 루트 디렉토리 경로
            filename: 다운로드할 파일명 (상대 경로 포함 가능, 예: "100세 프로젝트/file.jpg")
            local_path: 로컬 저장 디렉토리
            max_retries: 최대 재시도 횟수 (기본: 3)

        Returns:
            다운로드된 파일의 전체 경로 (실패 시 None)
        """
        for attempt in range(max_retries):
            try:
                if not self.connected:
                    if not self.reconnect():
                        print(f"❌ FTP 재연결 실패 (시도 {attempt + 1}/{max_retries})")
                        continue

                # 파일의 전체 원격 경로 구성
                # filename에 상대 경로가 포함되어 있을 수 있음
                remote_file_path = f"{remote_dir}/{filename}".replace('//', '/')
                
                # 파일명만 추출 (경로 제외)
                just_filename = os.path.basename(filename)
                
                # 로컬 저장 경로 결정
                if os.path.isdir(local_path):
                    local_file_path = os.path.join(local_path, just_filename)
                else:
                    local_file_path = local_path

                # 디렉토리 생성
                os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

                if attempt == 0:
                    print(f"⬇️  다운로드 중: {filename}")
                    print(f"   → {local_file_path}")
                else:
                    print(f"🔄 재시도 {attempt + 1}/{max_retries}: {filename}")

                # 파일 다운로드 (바이너리 모드)
                # 전체 원격 경로로 다운로드
                with open(local_file_path, 'wb') as local_file:
                    self.ftp.retrbinary(f'RETR {remote_file_path}', local_file.write)

                file_size = os.path.getsize(local_file_path)
                file_size_mb = file_size / (1024 * 1024)
                if attempt == 0:
                    print(f"✅ 다운로드 완료: {file_size_mb:.2f} MB")
                else:
                    print(f"✅ 재시도 성공: {file_size_mb:.2f} MB")

                return local_file_path

            except Exception as e:
                error_msg = str(e)
                print(f"❌ 파일 다운로드 실패 (시도 {attempt + 1}/{max_retries}): {error_msg}")
                
                # Broken pipe, Connection reset 등의 연결 오류인 경우 재연결
                if any(err in error_msg.lower() for err in ['broken pipe', 'connection', 'timeout', 'reset']):
                    self.connected = False
                    if attempt < max_retries - 1:
                        print(f"⚠️  연결 오류 감지, 재연결 후 재시도...")
                        if not self.reconnect():
                            continue
                    else:
                        print(f"💀 최대 재시도 횟수 초과: {filename}")
                        return None
                else:
                    # 다른 오류는 재시도 없이 즉시 실패
                    return None
        
        return None

    def download_files_batch(
        self,
        remote_dir: str,
        local_dir: str,
        extension: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[str]:
        """
        여러 파일 일괄 다운로드

        Args:
            remote_dir: 원격 디렉토리 경로
            local_dir: 로컬 저장 디렉토리
            extension: 필터링할 확장자
            limit: 다운로드할 최대 파일 개수

        Returns:
            다운로드된 파일 경로 리스트
        """
        files = self.list_files(remote_dir, extension)

        if limit:
            files = files[:limit]

        downloaded_files = []
        for i, filename in enumerate(files, 1):
            print(f"\n[{i}/{len(files)}] 다운로드 중...")
            local_path = self.download_file(remote_dir, filename, local_dir)
            if local_path:
                downloaded_files.append(local_path)

        return downloaded_files

    def close(self):
        """FTP 연결 종료"""
        if self.ftp and self.connected:
            try:
                self.ftp.quit()
                print("✅ FTP 연결 종료")
            except:
                self.ftp.close()
            finally:
                self.connected = False

    def __enter__(self):
        """Context manager 진입"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        self.close()


def create_ftp_client_from_env() -> FTPClient:
    """
    환경 변수에서 FTP 정보를 읽어 클라이언트 생성

    Returns:
        FTPClient 인스턴스
    """
    from dotenv import load_dotenv
    load_dotenv()

    host = os.getenv('FTP_HOST')
    user = os.getenv('FTP_USER')
    password = os.getenv('FTP_PASSWORD')
    port = int(os.getenv('FTP_PORT', 21))

    if not all([host, user, password]):
        raise ValueError("FTP 환경 변수가 설정되지 않았습니다 (FTP_HOST, FTP_USER, FTP_PASSWORD)")

    return FTPClient(host, user, password, port)


# 테스트 코드
if __name__ == "__main__":
    print("=== FTP Client 테스트 ===\n")

    # 환경 변수에서 FTP 클라이언트 생성
    client = create_ftp_client_from_env()

    # Context manager 사용
    with client:
        # 데이터 가공 경로 (FTP_PROCESSING_DIR2)
        remote_dir = os.getenv('FTP_IMAGE_DIR', os.getenv('FTP_PROCESSING_DIR2', '/FTP/RAPA2025/2.한국적배경및객체생성데이터'))
        print(f"\n데이터 경로: {remote_dir}\n")

        # 이미지 파일 목록 조회 (.jpg, .png 등)
        image_files = client.list_files(remote_dir, extension='.jpg')

        if image_files:
            print(f"\n발견된 이미지 파일:")
            for i, filename in enumerate(image_files[:5], 1):  # 처음 5개만 출력
                print(f"  {i}. {filename}")

            # 첫 번째 파일 다운로드 테스트
            if len(image_files) > 0:
                print(f"\n첫 번째 파일 다운로드 테스트:")
                local_path = client.download_file(
                    remote_dir,
                    image_files[0],
                    '/opt/jupyter/rapa25/raw_image25/tmp/images/'
                )
                if local_path:
                    print(f"✅ 테스트 완료: {local_path}")
