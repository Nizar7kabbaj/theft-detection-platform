from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_CANCEL_WAIT_SECONDS = 1.0


async def stop_task(task: asyncio.Task[None], name: str, timeout: float) -> None:
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.warning("%s did not stop in %.1fs, cancelling", name, timeout)
        task.cancel()
        await asyncio.wait({task}, timeout=_CANCEL_WAIT_SECONDS)
        return
    if not task.cancelled() and task.exception() is not None:
        logger.error("%s ended with an error", name, exc_info=task.exception())
