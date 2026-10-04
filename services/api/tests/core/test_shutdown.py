import asyncio

from app.core.shutdown import stop_task


async def test_finished_task_is_left_alone():
    task = asyncio.create_task(asyncio.sleep(0))
    await stop_task(task, "quick", timeout=0.5)
    assert task.done()
    assert not task.cancelled()


async def test_stuck_task_is_cancelled_within_budget():
    task = asyncio.create_task(asyncio.Event().wait())
    loop = asyncio.get_running_loop()
    start = loop.time()
    await stop_task(task, "stuck", timeout=0.1)
    assert task.cancelled()
    assert loop.time() - start < 1.0
