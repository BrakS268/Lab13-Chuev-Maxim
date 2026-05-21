import asyncio
import json
import uuid
import os
from typing import Dict, Optional

import nats


class HotelOrchestrator:
    def __init__(self):
        self.nc: Optional[nats.NATS] = None
        self.pending: Dict[str, asyncio.Future] = {}

    async def connect(self):
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        self.nc = await nats.connect(nats_url)
        await self.nc.subscribe("hotel.results", cb=self._on_result)
        print(f"[Orchestrator] подключён к NATS {nats_url}")

    async def disconnect(self):
        if self.nc:
            await self.nc.close()

    async def _on_result(self, msg):
        result = json.loads(msg.data.decode())
        task_id = result.get("task_id")
        if task_id in self.pending:
            self.pending[task_id].set_result(result)
            del self.pending[task_id]

    async def send_task(self, subject: str, payload: dict, timeout: int = 30) -> dict:
        task_id = str(uuid.uuid4())
        payload["task_id"] = task_id

        future = asyncio.get_event_loop().create_future()
        self.pending[task_id] = future

        await self.nc.publish(subject, json.dumps(payload).encode())
        print(f"[Orchestrator] отправлена задача {task_id} в {subject}")

        try:
            result = await asyncio.wait_for(future, timeout)
            return result
        except asyncio.TimeoutError:
            self.pending.pop(task_id, None)
            raise TimeoutError(f"задача {task_id} не выполнена за {timeout} сек")

    async def check_in(self, guest_name: str, room_number: int, nights: int, check_in_date: str) -> dict:
        return await self.send_task("hotel.checkin", {
            "type": "check_in",
            "guest_name": guest_name,
            "room_number": room_number,
            "nights": nights,
            "check_in_date": check_in_date,
        })

    async def check_out(self, guest_name: str, room_number: int) -> dict:
        return await self.send_task("hotel.checkin", {
            "type": "check_out",
            "guest_name": guest_name,
            "room_number": room_number,
        })

    async def clean_room(self, room_number: int, priority: str = "normal") -> dict:
        return await self.send_task("hotel.cleaning", {
            "type": "clean_room",
            "room_number": room_number,
            "priority": priority,
        })

    async def guest_request(self, guest_name: str, room_number: int, request_type: str, details: str) -> dict:
        return await self.send_task("hotel.requests", {
            "type": request_type,
            "guest_name": guest_name,
            "room_number": room_number,
            "details": details,
        })

    async def add_charge(self, guest_name: str, room_number: int, amount: float, description: str) -> dict:
        return await self.send_task("hotel.billing", {
            "type": "add_charge",
            "guest_name": guest_name,
            "room_number": room_number,
            "amount": amount,
            "description": description,
            "currency": "RUB",
        })


async def main():
    orchestrator = HotelOrchestrator()
    await orchestrator.connect()

    try:
        print("\n--- Сценарий: заселение гостя ---")
        result = await orchestrator.check_in(
            guest_name="Иван Иванов",
            room_number=101,
            nights=3,
            check_in_date="2025-05-21",
        )
        print(f"[Результат] {result}")

        print("\n--- Сценарий: запрос гостя ---")
        result = await orchestrator.guest_request(
            guest_name="Иван Иванов",
            room_number=101,
            request_type="room_service",
            details="Кофе и круассан",
        )
        print(f"[Результат] {result}")

        print("\n--- Сценарий: выселение ---")
        result = await orchestrator.check_out(
            guest_name="Иван Иванов",
            room_number=101,
        )
        print(f"[Результат] {result}")

    except TimeoutError as e:
        print(f"[Ошибка] таймаут: {e}")
    finally:
        await orchestrator.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
