import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orchestrator"))

from orchestrator import HotelOrchestrator


def make_orchestrator():
    orch = HotelOrchestrator()
    orch.nc = AsyncMock()
    return orch


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def inject_result(orch, task_id: str, result: dict):
    async def _inject():
        await asyncio.sleep(0.05)
        future = orch.pending.get(task_id)
        if future and not future.done():
            future.set_result(result)
    asyncio.get_event_loop().create_task(_inject())


@pytest.fixture
def orch():
    return make_orchestrator()


@pytest.mark.asyncio
async def test_check_in_success(orch):
    async def side_effect(subject, data):
        payload = json.loads(data.decode())
        task_id = payload["task_id"]
        await asyncio.sleep(0.05)
        future = orch.pending.get(task_id)
        if future:
            future.set_result({"task_id": task_id, "success": True, "output": "заселён", "room_status": "occupied"})

    orch.nc.publish = AsyncMock(side_effect=side_effect)

    result = await orch.check_in("Иван Иванов", 101, 3, "2025-05-21")

    assert result["success"] is True
    assert result["room_status"] == "occupied"


@pytest.mark.asyncio
async def test_check_in_failure(orch):
    async def side_effect(subject, data):
        payload = json.loads(data.decode())
        task_id = payload["task_id"]
        await asyncio.sleep(0.05)
        future = orch.pending.get(task_id)
        if future:
            future.set_result({"task_id": task_id, "success": False, "output": "номер занят"})

    orch.nc.publish = AsyncMock(side_effect=side_effect)

    result = await orch.check_in("Иван Иванов", 101, 3, "2025-05-21")

    assert result["success"] is False
    assert orch.metrics.tasks_failed == 1


@pytest.mark.asyncio
async def test_check_out_success(orch):
    async def side_effect(subject, data):
        payload = json.loads(data.decode())
        task_id = payload["task_id"]
        await asyncio.sleep(0.05)
        future = orch.pending.get(task_id)
        if future:
            future.set_result({"task_id": task_id, "success": True, "output": "выселен", "room_status": "needs_cleaning"})

    orch.nc.publish = AsyncMock(side_effect=side_effect)

    result = await orch.check_out("Иван Иванов", 101)

    assert result["success"] is True
    assert result["room_status"] == "needs_cleaning"


@pytest.mark.asyncio
async def test_timeout_triggers_retry(orch):
    orch.nc.publish = AsyncMock()

    with pytest.raises(TimeoutError) as exc_info:
        await orch.send_task("hotel.checkin", {"type": "check_in"}, timeout=0.1)

    assert "не выполнена после 3 попыток" in str(exc_info.value)
    assert orch.metrics.tasks_timed_out == 3
    assert orch.metrics.tasks_retried == 2


@pytest.mark.asyncio
async def test_metrics_count(orch):
    async def side_effect(subject, data):
        payload = json.loads(data.decode())
        task_id = payload["task_id"]
        await asyncio.sleep(0.05)
        future = orch.pending.get(task_id)
        if future:
            future.set_result({"task_id": task_id, "success": True, "output": "ok"})

    orch.nc.publish = AsyncMock(side_effect=side_effect)

    await orch.check_in("Гость А", 101, 1, "2025-05-21")
    await orch.check_in("Гость Б", 102, 2, "2025-05-21")

    assert orch.metrics.tasks_sent == 2
    assert orch.metrics.tasks_succeeded == 2
    assert orch.metrics.tasks_failed == 0
