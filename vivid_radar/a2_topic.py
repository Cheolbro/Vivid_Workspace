import asyncio
import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict
from vivid_core.scraper import BaseScraper
from vivid_core.db_manager import db
from vivid_core.logger import logger
from vivid_core.config_loader import config

class TopicDiscovery(BaseScraper):
    """
    Module A2: 핫한 주제 탐색 모듈.
    VPH, Outlier 지표를 계산하고 최종 주제를 선정합니다.
    - Phase 1: 알고리즘 기반 후보 추출 (Persistent Context)
    - Phase 2: 시크릿 교차 검증 (Incognito Context)
    """
    def __init__(self, mode: str = "B", user_data_dir: str = None, headless: bool = True):
        super().__init__(user_data_dir=user_data_dir, headless=headless)
        self.mode = mode

    async def run(self):
        logger.info(f"Starting Module A2: TopicDiscovery (Mode {self.mode})")
        
        # Phase 1: 알고리즘 기반 추출 (Persistent Context)
        # 만약 user_data_dir이 없으면 처음부터 Incognito로 시작
        await self.start()
        
        logger.info("[Phase 1] Collecting candidates from algorithm feed...")
        page = await self.get_page()
        
        if self.mode == "A":
            await self.safe_goto(page, "https://www.youtube.com/feed/subscriptions")
        else:
            await self.safe_goto(page, "https://www.youtube.com")
        
        video_cards = await page.query_selector_all("ytd-rich-item-renderer, ytd-grid-video-renderer")
        candidates = []
        
        for card in video_cards[:20]: # 상위 20개 분석
            video_data = await self._parse_video_card(card)
            if video_data and self._is_potential_topic(video_data):
                candidates.append(video_data)

        logger.info(f"Phase 1 finished. Found {len(candidates)} candidates.")

        # Phase 2: 시크릿 교차 검증 (Incognito Context)
        logger.info("[Phase 2] Cross-validating candidates in Incognito mode...")
        # 기존 브라우저를 닫고 Incognito로 새로 시작
        await self.start(user_data_dir=None) 
        
        hot_topics = []
        for cand in candidates:
            if await self._validate_topic(cand["title"]):
                cand["is_hot_topic"] = 1
                self._save_to_db(cand)
                hot_topics.append(cand)
                logger.success(f"Hot topic confirmed: {cand['title']}")
            
            if len(hot_topics) >= config.get("a2_min_topics"):
                break

        await self.stop()
        logger.info(f"Module A2 finished. Found {len(hot_topics)} hot topics.")

    async def _parse_video_card(self, card) -> Dict | None:
        try:
            # 셀렉터는 유튜브 레이아웃 변경에 따라 유동적일 수 있음
            title_el = await card.query_selector("#video-title, #video-title-link")
            title = await title_el.inner_text() if title_el else ""
            
            # 메타데이터 추출 (조회수, 시간 등)
            meta_els = await card.query_selector_all("#metadata-line span")
            views_text = await meta_els[0].inner_text() if len(meta_els) > 0 else ""
            time_text = await meta_els[1].inner_text() if len(meta_els) > 1 else ""
            
            views = self._parse_views(views_text)
            hours = self._parse_hours(time_text)
            vph = views / max(hours, 1)
            
            title_text = title.strip()
            # 제목 + 업로드 시각으로 결정론적 ID 생성 (중복 저장 방지)
            video_id = hashlib.md5(f"{title_text}:{hours}".encode()).hexdigest()[:16]
            return {
                "video_id": video_id,
                "title": title_text,
                "views": views,
                "vph": vph,
                "outlier_score": 2.5,  # TODO: 실제 채널 평균 조회수 대비 계산 필요
                "published_at": datetime.now() - timedelta(hours=hours)
            }
        except Exception as e:
            return None

    def _is_potential_topic(self, data: Dict) -> bool:
        vph_threshold = config.get("a2_vph_threshold")
        outlier_threshold = config.get("a2_outlier_threshold")
        return data["vph"] >= vph_threshold and data["outlier_score"] >= outlier_threshold

    async def _validate_topic(self, title: str) -> bool:
        """시크릿 창 검색 검증: AI 라벨 영상 3개 이상 노출 여부"""
        from urllib.parse import quote
        page = await self.get_page()
        try:
            search_url = f"https://www.youtube.com/results?search_query={quote(title)}"
            await self.safe_goto(page, search_url)
            
            # AI 라벨 카운트
            content = await page.content()
            ai_label_count = content.count("변경되었거나 합성된 콘텐츠")
            logger.info(f"Validation: '{title}' -> AI labels found: {ai_label_count}")
            return ai_label_count >= 3
        finally:
            await page.close()

    def _parse_views(self, text: str) -> int:
        if not text: return 0
        match = re.search(r'([\d\.]+)([만천회KMB])', text)
        if not match: return 0
        num, unit = match.groups()
        num = float(num)
        mapping = {'회': 1, '천': 1000, '만': 10000, 'K': 1000, 'M': 1000000}
        return int(num * mapping.get(unit, 1))

    def _parse_hours(self, text: str) -> int:
        if '시간 전' in text:
            return int(re.search(r'\d+', text).group())
        elif '일 전' in text:
            return int(re.search(r'\d+', text).group()) * 24
        elif '분 전' in text:
            return 1 # 1시간 미만은 1시간으로 처리
        return 24 # 기본값

    def _save_to_db(self, data: Dict):
        db.execute_query("""
            INSERT OR REPLACE INTO videos (video_id, title, views, vph, outlier_score, is_hot_topic)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (data["video_id"], data["title"], data["views"], data["vph"], data["outlier_score"], data["is_hot_topic"]))

if __name__ == "__main__":
    discovery = TopicDiscovery()
    asyncio.run(discovery.run())
