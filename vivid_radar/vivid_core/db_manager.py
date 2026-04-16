import sqlite3
import os
from pathlib import Path
from datetime import datetime
from .logger import logger

class DBManager:
    """
    VIVID Radar의 로컬 SQLite 데이터베이스를 관리하는 싱글톤 클래스.
    모든 데이터는 vivid_radar/radar_data.db에 저장됩니다.
    """
    def __init__(self, db_path: str = "radar_data.db"):
        # vivid_radar 폴더 내부에 위치하도록 경로 설정
        self.db_path = Path(__file__).parent.parent / db_path
        self._initialize_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        """테이블 및 인덱스 초기 스키마 생성"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # (1) Channels 테이블: is_active 추가 및 인덱스
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    subscriber_count INTEGER,
                    recent_avg_views REAL,
                    performance_score REAL,
                    ai_label_confirmed INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    last_scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_channels_last_scanned ON channels(last_scanned_at)")

            # (2) Videos 테이블: is_hot_topic 및 인덱스
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    title TEXT NOT NULL,
                    views INTEGER,
                    vph REAL,
                    outlier_score REAL,
                    delta_vph REAL DEFAULT 0,
                    ai_label_count INTEGER,
                    is_hot_topic INTEGER DEFAULT 0,
                    published_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(channel_id) REFERENCES channels(channel_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_hot_topic ON videos(is_hot_topic)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_created_at ON videos(created_at)")

            # (3) Title Suggestions 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS title_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_video_id TEXT,
                    suggested_title TEXT NOT NULL,
                    batch_grade TEXT,
                    ai_label_exposure_rank INTEGER,
                    score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(original_video_id) REFERENCES videos(video_id)
                )
            """)
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    def execute_query(self, query: str, params: tuple = ()):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor

    def fetch_all(self, query: str, params: tuple = ()):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def fetch_one(self, query: str, params: tuple = ()):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

# 싱글톤 인스턴스
db = DBManager()
