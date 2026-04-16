import asyncio
import re
from typing import List, Dict
from datetime import datetime, timedelta
from vivid_core.scraper import BaseScraper
from vivid_core.db_manager import db
from vivid_core.logger import logger
from vivid_core.config_loader import config
from vivid_core.notifier import notifier

class ChannelScout(BaseScraper):
    """
    Module A1: 레퍼런스 채널 스카우트 모듈.
    A급 레퍼런스 채널을 발굴하여 SQLite에 저장합니다.
    """
    def __init__(self, keyword: str, user_data_dir: str = None, headless: bool = True):
        super().__init__(user_data_dir=user_data_dir, headless=headless)
        self.keyword = keyword
        self.target_channels: List[Dict] = []

    async def run(self):
        logger.info(f"Starting Module A1 for keyword: {self.keyword}")
        await self.start()
        page = await self.get_page()

        # 1. 키워드 검색 및 채널 수집
        search_url = f"https://www.youtube.com/results?search_query={self.keyword}&sp=EgIQAg%253D%253D" # 채널 필터 적용
        await self.safe_goto(page, search_url)
        
        channel_elements = await page.query_selector_all("#content-section")
        channel_urls = []
        for el in channel_elements[:10]: # 상위 10개 채널 대상
            href = await el.eval_on_selector("a#main-link", "el => el.href")
            if href:
                channel_urls.append(href)

        for url in channel_urls:
            if len(self.target_channels) >= config.get("a1_min_channels"):
                break
            
            channel_data = await self._analyze_channel(url)
            if channel_data:
                self._save_to_db(channel_data)
                self.target_channels.append(channel_data)
                logger.success(f"Channel found and saved: {channel_data['name']}")

        await self.stop()
        logger.info(f"Module A1 finished. Found {len(self.target_channels)} channels.")

    async def _analyze_channel(self, url: str) -> Dict | None:
        page = await self.get_page()
        try:
            # 채널 홈 접속
            await self.safe_goto(page, url)
            channel_name = await self.get_element_text(page, "#channel-name #text")
            sub_text = await self.get_element_text(page, "#subscriber-count")
            sub_count = self._parse_subscriber_count(sub_text)

            # 3. 구독자 기준 필터: max(내구독자*10, 5000)
            my_sub = config.get("my_subscriber_count")
            min_sub = max(my_sub * 10, config.get("a1_min_subscribers"))
            if sub_count > min_sub:
                logger.info(f"Skipping {channel_name}: Subscriber count {sub_count} > {min_sub}")
                return None

            # 2. AI 라벨 전수 조사 (0순위 필터)
            # 최근 동영상 탭으로 이동
            await self.safe_goto(page, f"{url}/videos")
            video_elements = await page.query_selector_all("ytd-rich-item-renderer")
            
            # 최근 3~5개 영상 AI 라벨 확인
            check_count = min(len(video_elements), 5)
            video_urls = []
            for i in range(check_count):
                v_url = await video_elements[i].eval_on_selector("a#video-title-link", "el => el.href")
                video_urls.append(v_url)

            for v_url in video_urls:
                if not await self._check_ai_label(v_url):
                    logger.warning(f"Skipping {channel_name}: AI Label missing in video {v_url}")
                    return None # 하나라도 누락 시 즉시 탈락

            # 4. 활동성 검증 (최근 4개 영상 7일 이내)
            # 5. 실력 검증 ((최근 10개 평균 조회수 / 구독자) >= 3)
            # (이 부분은 상세 파싱 로직이 필요하며, 예시로 3개 통과 시 반환)
            
            # 실력 검증 수치 계산 (모의)
            perf_score = 3.5 # 실제 구현 시 평균 조회수 계산 로직 추가
            
            return {
                "channel_id": url.split("/")[-1],
                "name": channel_name,
                "subscriber_count": sub_count,
                "performance_score": perf_score,
                "ai_label_confirmed": 1
            }

        finally:
            await page.close()

    async def _check_ai_label(self, video_url: str) -> bool:
        """영상 상세 페이지에서 '변경되었거나 합성된 콘텐츠' 라벨 확인"""
        page = await self.get_page()
        try:
            await self.safe_goto(page, video_url)
            # 설명란 확장
            expand_button = await page.query_selector("#expand")
            if expand_button: await expand_button.click()
            
            content = await page.content()
            return "변경되었거나 합성된 콘텐츠" in content
        finally:
            await page.close()

    def _parse_subscriber_count(self, text: str) -> int:
        if not text: return 0
        match = re.search(r'([\d\.]+)([만천명KMB])', text)
        if not match: return 0
        num, unit = match.groups()
        num = float(num)
        mapping = {'명': 1, '천': 1000, '만': 10000, 'K': 1000, 'M': 1000000}
        return int(num * mapping.get(unit, 1))

    def _save_to_db(self, data: Dict):
        db.execute_query("""
            INSERT OR REPLACE INTO channels (channel_id, name, subscriber_count, performance_score, ai_label_confirmed)
            VALUES (?, ?, ?, ?, ?)
        """, (data["channel_id"], data["name"], data["subscriber_count"], data["performance_score"], data["ai_label_confirmed"]))

if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "이란전쟁"
    scout = ChannelScout(keyword)
    asyncio.run(scout.run())
