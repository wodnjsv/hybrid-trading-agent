"""수집기 메인: universe 폴링 + 프레임 수신/파싱/녹음 + 주기 flush."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime

from manju.config import Config
from manju.kis import auth, rest
from manju.kis.ws import KISWebSocket
from manju.kis.parse import parse_frame
from manju.collector.subscriber import plan_changes
from manju.collector.recorder import Recorder
from manju.collector.compact import compact_date
from manju.collector.keepawake import keep_awake

logger = logging.getLogger(__name__)


async def _universe_loop(cfg: Config, token: str, ws: KISWebSocket, state: dict):
    """주기적으로 거래대금 상위 재선정 → 구독 등록/해지."""
    while True:
        try:
            desired = rest.top_symbols_by_value(token, cfg, cfg.universe_size)
            to_reg, to_unreg, active = plan_changes(
                state["subscribed"], desired, cfg.max_registrations)
            for tr_id, sym in to_unreg:
                await ws.unregister(tr_id, sym)
            for tr_id, sym in to_reg:
                await ws.register(tr_id, sym)
            state["subscribed"] = set(active)
            logger.info("universe: %d active", len(active))
        except Exception as e:                       # noqa: BLE001
            logger.warning("universe loop error: %s", e)
        await asyncio.sleep(cfg.poll_interval_sec)


async def _recv_loop(ws: KISWebSocket, recorder: Recorder):
    async for raw in ws.frames():
        for event in parse_frame(raw, datetime.now()):
            recorder.record(event)


async def _flush_loop(recorder: Recorder, interval: int = 10):
    while True:
        await asyncio.sleep(interval)
        recorder.flush()


async def run(cfg: Config) -> None:
    token = auth.issue_access_token(cfg)
    ws = KISWebSocket(cfg.ws_url, auth.issue_approval_key(cfg))
    await ws.connect()
    recorder = Recorder(cfg.data_dir)
    state = {"subscribed": set()}
    try:
        await asyncio.gather(
            _universe_loop(cfg, token, ws, state),
            _recv_loop(ws, recorder),
            _flush_loop(recorder),
        )
    finally:
        recorder.flush()
        # 정상 종료(Ctrl+C 포함) 시 그날 shard들을 종목당 1파일로 병합 → 수동 복사 용이
        for d in sorted(recorder.dates_written):
            try:
                n = compact_date(cfg.data_dir, d)
                logger.info("compacted %s: %d symbol-file(s)", d, n)
            except Exception as e:                       # noqa: BLE001
                logger.warning("compaction failed for %s: %s", d, e)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with keep_awake():
        try:
            asyncio.run(run(Config.load()))
        except KeyboardInterrupt:
            logger.info("수집기 중지됨 (Ctrl+C)")


if __name__ == "__main__":
    main()
