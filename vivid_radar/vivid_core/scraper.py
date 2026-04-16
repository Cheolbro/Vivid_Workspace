import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext
from .logger import logger

class BaseScraper:
    """
    Playwright 기반의 고성능 스크래퍼 베이스 클래스.
    리소스 차단 및 사용자 프로필 연동 기능을 제공합니다.
    """
    def __init__(self, user_data_dir: Optional[str] = None, headless: bool = True):
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.pw = None
        self.browser = None
        self.context: Optional[BrowserContext] = None

    async def start(self, user_data_dir: Optional[str] = None, headless: Optional[bool] = None):
        """
        브라우저를 시작합니다. 
        실행 중인 브라우저가 있다면 먼저 닫습니다. (순차 실행 지원용)
        """
        if self.pw:
            await self.stop()

        # 인자 업데이트
        if user_data_dir is not None: self.user_data_dir = user_data_dir
        if headless is not None: self.headless = headless

        self.pw = await async_playwright().start()
        
        if self.user_data_dir:
            # Persistent Context (로그인 세션 유지용)
            logger.info(f"Launching Persistent Context: {self.user_data_dir}")
            self.context = await self.pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
        else:
            # Incognito Context (익명 모드)
            logger.info("Launching Incognito Context")
            self.browser = await self.pw.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

    async def get_page(self) -> Page:
        page = await self.context.new_page()
        # 리소스 차단 로직
        await page.route("**/*", self._route_interceptor)
        return page

    async def _route_interceptor(self, route):
        resource_types = ["image", "font", "stylesheet", "media", "other"]
        if route.request.resource_type in resource_types:
            await route.abort()
        elif "google-analytics" in route.request.url or "doubleclick" in route.request.url:
            await route.abort()
        else:
            await route.continue_()

    async def stop(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.pw:
                await self.pw.stop()
        except Exception:
            pass
        finally:
            self.context = None
            self.browser = None
            self.pw = None
        logger.info("Scraper stopped.")

    async def safe_goto(self, page: Page, url: str, wait_until="networkidle"):
        try:
            await page.goto(url, wait_until=wait_until, timeout=30000)
            return True
        except Exception as e:
            logger.error(f"Goto error ({url}): {e}")
            return False

    async def get_element_text(self, page: Page, selector: str) -> str:
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
            return (await element.inner_text()).strip() if element else ""
        except:
            return ""
