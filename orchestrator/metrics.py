import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Metrics:
    tasks_sent: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_timed_out: int = 0
    tasks_retried: int = 0
    tasks_by_subject: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _start_time: float = field(default_factory=time.time)

    def record_sent(self, subject: str):
        self.tasks_sent += 1
        self.tasks_by_subject[subject] += 1

    def record_success(self):
        self.tasks_succeeded += 1

    def record_failure(self):
        self.tasks_failed += 1

    def record_timeout(self):
        self.tasks_timed_out += 1

    def record_retry(self):
        self.tasks_retried += 1

    def summary(self) -> str:
        uptime = int(time.time() - self._start_time)
        lines = [
            "=== Метрики оркестратора ===",
            f"  Uptime:      {uptime} сек",
            f"  Отправлено:  {self.tasks_sent}",
            f"  Успешно:     {self.tasks_succeeded}",
            f"  Ошибок:      {self.tasks_failed}",
            f"  Таймаутов:   {self.tasks_timed_out}",
            f"  Повторов:    {self.tasks_retried}",
            "  По топикам:",
        ]
        for subject, count in self.tasks_by_subject.items():
            lines.append(f"    {subject}: {count}")
        return "\n".join(lines)
