try:
    from win10toast import ToastNotifier
except ImportError:
    ToastNotifier = None

from .logger import logger

class Notifier:
    """
    윈도우 알림(Toast) 유틸리티.
    라이브러리 미설치 시 로깅으로 대체합니다.
    """
    def __init__(self):
        self.toaster = ToastNotifier() if ToastNotifier else None

    def notify(self, title: str, message: str, duration: int = 5):
        logger.info(f"Notification: {title} - {message}")
        if self.toaster:
            try:
                # 윈도우 팝업 알림 시 threaded=True일 때 발생하는 C타입 에러 방지
                self.toaster.show_toast(
                    title,
                    message,
                    duration=duration,
                    threaded=False
                )
            except Exception as e:
                logger.error(f"Notification error: {e}")

# 싱글톤 인스턴스
notifier = Notifier()
