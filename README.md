# lab13-Chuev-Maxim
**Лабораторная работа 13**

**Студент:** Чуев Максим Сергеевич 

**Группа:** 220032-11 

**Вариант:** 29

**Сложность:** средняя

# Hotel MAS — Мультиагентная система управления гостиницей


## Описание

Распределённая мультиагентная система для управления гостиницей. Агенты написаны на Go, оркестратор и REST API — на Python. Взаимодействие через брокер сообщений NATS.

## Компоненты

### NATS Broker
Брокер сообщений. Принимает публикации и доставляет их подписчикам. Использует **queue groups** для балансировки нагрузки между несколькими экземплярами одного агента.

- Порт `4222` — основной (подключение агентов)
- Порт `8222` — HTTP мониторинг

### CheckInAgent (Go)
Агент заселения и выселения гостей.

- Топик: `hotel.checkin`
- Queue group: `checkin-workers`
- Типы задач: `check_in`, `check_out`
- При выселении автоматически публикует задачу уборки в `hotel.cleaning`
- Запускается в 3 экземплярах, NATS равномерно распределяет задачи

### Orchestrator (Python)
Центральный управляющий компонент. Отправляет задачи агентам и ожидает результаты через `asyncio.Future`.

- Подписка на `hotel.results`
- Retry: до 3 попыток с паузой 2 сек при таймауте
- Метрики: счётчики отправленных, успешных, ошибочных задач

### FastAPI (Python)
REST API поверх оркестратора. Принимает HTTP-запросы и передаёт их в оркестратор.

- `GET  /health` — проверка состояния
- `POST /checkin` — заселение гостя
- `POST /checkout` — выселение гостя
- `POST /cleaning` — уборка номера
- `POST /requests` — запрос гостя (room_service, towels, taxi, wake_up_call)
- `POST /billing/charge` — добавить списание
- Swagger UI: http://localhost:8000/docs

## Структура проекта

```
hotel-mas/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── AGENTS.md
├── ARCHITECTURE.md
├── PROMPT_LOG.md
├── agents/
│   └── checkin/
│       ├── Dockerfile
│       ├── go.mod
│       ├── main.go
│       └── main_test.go
├── orchestrator/
│   ├── Dockerfile
│   ├── logger.py
│   ├── metrics.py
│   ├── orchestrator.py
│   └── requirements.txt
├── api/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
└── tests/
    ├── pytest.ini
    ├── requirements-test.txt
    └── test_orchestrator.py
```

## Топики NATS

| Топик             | Издатель       | Подписчик       | Назначение                  |
|-------------------|----------------|-----------------|-----------------------------|
| `hotel.checkin`   | Orchestrator   | CheckInAgent    | Задачи заселения/выселения  |
| `hotel.cleaning`  | CheckInAgent   | (будущий агент) | Задачи уборки номеров       |
| `hotel.requests`  | Orchestrator   | (будущий агент) | Запросы гостей              |
| `hotel.billing`   | Orchestrator   | (будущий агент) | Задачи биллинга             |
| `hotel.results`   | CheckInAgent   | Orchestrator    | Результаты выполнения задач |

## Запуск

### Требования
- Docker Desktop

### Запуск всей системы

```bash
docker compose up --build
```

После запуска:
- Swagger UI: http://localhost:8000/docs
- NATS мониторинг: http://localhost:8222

### Остановка

```bash
docker compose down
```

### Просмотр логов

```bash
docker compose logs -f checkin-agent-1
docker compose logs -f orchestrator
docker compose logs -f api
```

## Тесты

### Go (модульные тесты агента)

```bash
cd agents/checkin
go test ./... -v
```

### Python (тесты оркестратора с моками)

```bash
cd tests
pip install -r requirements-test.txt
pytest -v
```

## Переменные окружения

| Переменная | По умолчанию            | Описание                  |
|------------|-------------------------|---------------------------|
| `NATS_URL` | `nats://localhost:4222` | Адрес NATS-брокера        |
| `LOG_DIR`  | `logs`                  | Папка для файлов логов    |
| `AGENT_ID` | `default`               | Идентификатор агента в логах |