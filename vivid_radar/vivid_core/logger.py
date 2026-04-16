import logging
import sys
from typing import Any, Callable

# GUI 등에서 로그를 실시간으로 가로채기 위한 콜백 타입
LogCallback = Callable[[str, str], None]

class VividLogger:
    """
    VIVID 시스템 내에서 표준 로깅과 GUI 이벤트를 통합 관리하는 커스텀 로거.
    """
    def __init__(self, name: str = "VividRadar"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # 기본 콘솔 핸들러 설정
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
        self._callbacks: list[LogCallback] = []

    def add_callback(self, callback: LogCallback) -> None:
        """로그 발생 시 호출될 콜백 함수를 등록합니다. (예: GUI 텍스트창 업데이트)"""
        self._callbacks.append(callback)

    def _emit(self, level: str, message: str) -> None:
        for cb in self._callbacks:
            try:
                cb(level, message)
            except Exception:
                pass

    def info(self, msg: str) -> None:
        self.logger.info(msg)
        self._emit("INFO", msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)
        self._emit("WARNING", msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)
        self._emit("ERROR", msg)

    def success(self, msg: str) -> None:
        """성공 메시지 (C_HIGHLIGHT 대응용)"""
        self.logger.info(f"[SUCCESS] {msg}")
        self._emit("SUCCESS", msg)

# 글로벌 싱글톤 인스턴스
logger = VividLogger()
