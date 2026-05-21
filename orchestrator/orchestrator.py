import asyncio
import json
import uuid
import os
from typing import Dict, Optional

import nats

from logger import setup_logger
from metrics import Metrics

MAX_RETRIES = 3
RETRY_DELAY = 2


class HotelOrchestrator:
    def __init__(self):
        self.nc: Optional[nats.NATS] = None
        self.pending: Dict[str, asyncio.Future] = {}
        self.logger = setup_logger("orchestrator")
        self.metrics = Metrics()

    async def connect(self):
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        self.nc = await nats.connect(nats_url)
        await self.nc.subscribe("hotel.results", cb=self._on_result)
        self.logger.info("подключён к NATS %s", nats_url)

    async def disconnect(self):
        if self.nc:
            await self.nc.close()
        self.logger.info("отключён от NATS")
        self.logger.info(self.metrics.summary())

    async def _on_result(self, msg):
        result = json.loads(msg.data.decode())
        task_id = result.get("task_id")
        if task_id in self.pending:
            self.pending[task_id].set_result(result)
            del self.pending[task_id]
            self.logger.debug("получен результат для задачи %s", task_id)

    async def send_task(self, subject: str, payload: dict, timeout: int = 30) -> dict:
        task_id = str(uuid.uuid4())
        payload["task_id"] = task_id

        for attempt in range(1, MAX_RETRIES + 1):
            future = asyncio.get_event_loop().create_future()
            self.pending[task_id] = future

            self.metrics.record_sent(subject)
            await self.nc.publish(subject, json.dumps(payload).encode())
            self.logger.info("отправлена задача %s в %s (попытка %d/%d)", task_id, subject, attempt, MAX_RETRIES)

            try:
                result = await asyncio.wait_for(future, timeout)
                if result.get("success"):
                    self.metrics.record_success()
                    self.logger.info("задача %s выполнена успешно: %s", task_id, result.get("output"))
                else:
                    self.metrics.record_failure()
                    self.logger.error("задача %s завершилась с ошибкой: %s", task_id, result.get("output"))
                return result

            except asyncio.TimeoutError:
                self.pending.pop(task_id, None)
                self.metrics.record_timeout()
                self.logger.error(
                    "таймаут задачи %s (топик=%s, попытка %d/%d)",
                    task_id, subject, attempt, MAX_RETRIES,
                )
                if attempt < MAX_RETRIES:
                    self.metrics.record_retry()
                    self.logger.info("повтор через %d сек...", RETRY_DELAY)
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    raise TimeoutError(
                        f"задача {task_id} не выполнена после {MAX_RETRIES} попыток"
                    )

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
        print("\n--- Демо балансировки: 4 заселения параллельно ---")
        guests = [
            ("Иван Иванов", 101),
            ("Мария Петрова", 102),
            ("Сергей Сидоров", 103),
            ("Анна Кузнецова", 104),
        ]
        tasks = [
            orchestrator.check_in(name, room, 2, "2025-05-21")
            for name, room in guests
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            print(f"[Результат] {r}")

        print("\n--- Выселение всех ---")
        tasks = [orchestrator.check_out(name, room) for name, room in guests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            print(f"[Результат] {r}")

    except TimeoutError as e:
        print(f"[Ошибка] исчерпаны все попытки: {e}")
    finally:
        await orchestrator.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
