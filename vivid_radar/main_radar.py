import asyncio
import sys
from datetime import datetime
from vivid_core.notifier import notifier
from vivid_core.logger import logger
from vivid_core.config_loader import config
from a1_channel import ChannelScout
from a2_topic import TopicDiscovery

async def main():
    now = datetime.now()
    hour = now.strftime("%H")

    # 1. 시작 알림
    notifier.notify("VIVID Radar", f"오전 {hour}시 데이터 수집을 시작합니다.")
    logger.info(f"Radar task started at {now}")

    try:
        # A1 실행 — 키워드는 radar_config.json 의 "a1_keyword" 필드에서 로드
        keyword = config.get("a1_keyword", "이란전쟁")
        scout = ChannelScout(keyword)
        await scout.run()

        # A2 실행
        discovery = TopicDiscovery()
        await discovery.run()
        
        # 2. 종료 알림
        notifier.notify("VIVID Radar", "데이터 수집 및 분석이 완료되었습니다.")
        logger.info("Radar task completed successfully.")
    except Exception as e:
        logger.error(f"Radar task failed: {e}")
        notifier.notify("VIVID Radar", f"에러 발생: {str(e)[:50]}...")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
