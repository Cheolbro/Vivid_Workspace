import json
import os
from pathlib import Path
from .logger import logger

class ConfigLoader:
    """
    VIVID Radar 설정을 관리하는 클래스.
    명세서의 기본 수치들을 기본값으로 가지며, radar_config.json 파일에서 로드 가능합니다.
    """
    def __init__(self, config_file: str = "radar_config.json"):
        self.config_path = Path(__file__).parent.parent / config_file
        self.settings = {
            # Module A1
            "a1_min_subscribers": 5000,
            "a1_activity_days": 7,
            "a1_activity_count": 4,
            "a1_performance_threshold": 3.0,
            "a1_min_channels": 3,
            
            # Module A2
            "a2_vph_threshold": 100,
            "a2_outlier_threshold": 2.0,
            "a2_min_topics": 3,
            
            # Common
            "my_subscriber_count": 100, # 예시값
            "profiles": {}, # { "Display Name": "Full Path" } 딕셔너리 구조
            "headless": True
        }
        self._load_config()
        # 로드 후 프로필 자동 스캔 (디스플레이 이름 기반)
        self._auto_scan_profiles()

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        logger.warning(f"Config file {self.config_path} is empty. Resetting to defaults.")
                        self._save_config()
                        return
                    
                    user_settings = json.loads(content)
                    self.settings.update(user_settings)
                logger.info(f"Configuration loaded from {self.config_path}")
            except Exception as e:
                logger.error(f"Config load error: {e}. Resetting to defaults.")
                self._save_config()
        else:
            self._save_config()

    def _auto_scan_profiles(self):
        """Chrome의 Local State 파일을 파싱하여 프로필 디스플레이 이름을 가져옵니다."""
        chrome_user_data = Path(os.environ.get('LOCALAPPDATA', '')) / "Google/Chrome/User Data"
        local_state_path = chrome_user_data / "Local State"
        
        if not local_state_path.exists():
            logger.warning(f"Chrome Local State not found at {local_state_path}")
            return

        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                info_cache = state.get("profile", {}).get("info_cache", {})
                
                # 기존 프로필 목록 초기화 (중복 방지 및 깔끔한 갱신)
                new_profiles = {}
                
                for folder_name, info in info_cache.items():
                    # 'name' 필드가 있는 경우 해당 이름을 사용, 없으면 폴더명 사용
                    display_name = info.get("name")
                    if not display_name:
                        continue # 이름이 없는 항목은 스킵
                        
                    profile_path = chrome_user_data / folder_name
                    
                    if profile_path.exists():
                        # GUI 표시 이름만 키로 사용 (폴더명 제외)
                        new_profiles[display_name] = str(profile_path)
                
                # 변경 사항이 있을 때만 업데이트 및 저장
                if self.settings["profiles"] != new_profiles:
                    self.settings["profiles"] = new_profiles
                    logger.info("Chrome profiles updated with display names.")
                    self._save_config()
                    
        except Exception as e:
            logger.error(f"Error parsing Chrome Local State: {e}")

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Config save error: {e}")

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

# 싱글톤 인스턴스
config = ConfigLoader()
