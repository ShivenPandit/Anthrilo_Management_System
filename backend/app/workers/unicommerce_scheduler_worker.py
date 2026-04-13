"""Standalone worker process for Unicommerce scheduled sync jobs."""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import settings
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def _wait_for_shutdown(stop_event: asyncio.Event) -> None:
    await stop_event.wait()


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _trigger_shutdown() -> None:
        if not stop_event.is_set():
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _trigger_shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(_trigger_shutdown))


async def main() -> None:
    if not settings.UNICOMMERCE_SYNC_ENABLE_SCHEDULER:
        logger.warning(
            "Unicommerce scheduler worker is disabled. "
            "Set UNICOMMERCE_SYNC_ENABLE_SCHEDULER=true for the worker service."
        )
        return

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    orchestrator = get_unicommerce_sync_orchestrator()
    started = orchestrator.start_scheduler()

    if started:
        logger.info("Unicommerce scheduler worker started")
    else:
        logger.info("Unicommerce scheduler worker found scheduler already running")

    try:
        await _wait_for_shutdown(stop_event)
    finally:
        await orchestrator.stop_scheduler()
        logger.info("Unicommerce scheduler worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
