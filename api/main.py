import asyncio
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "orchestrator"))

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from orchestrator import HotelOrchestrator

orchestrator: Optional[HotelOrchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    orchestrator = HotelOrchestrator()
    await orchestrator.connect()
    yield
    await orchestrator.disconnect()


app = FastAPI(
    title="Hotel MAS API",
    description="REST API для системы управления гостиницей",
    version="1.0.0",
    lifespan=lifespan,
)


class CheckInRequest(BaseModel):
    guest_name: str = Field(..., example="Иван Иванов")
    room_number: int = Field(..., ge=101, example=101)
    nights: int = Field(..., ge=1, example=3)
    check_in_date: str = Field(..., example="2025-05-21")


class CheckOutRequest(BaseModel):
    guest_name: str = Field(..., example="Иван Иванов")
    room_number: int = Field(..., ge=101, example=101)


class CleanRoomRequest(BaseModel):
    room_number: int = Field(..., ge=101, example=101)
    priority: str = Field(default="normal", pattern="^(normal|urgent)$")


class GuestRequestBody(BaseModel):
    guest_name: str = Field(..., example="Иван Иванов")
    room_number: int = Field(..., ge=101, example=101)
    request_type: str = Field(..., example="room_service")
    details: str = Field(..., example="Кофе и круассан")


class AddChargeRequest(BaseModel):
    guest_name: str = Field(..., example="Иван Иванов")
    room_number: int = Field(..., ge=101, example=101)
    amount: float = Field(..., gt=0, example=2500.0)
    description: str = Field(..., example="Проживание 3 ночи")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/checkin")
async def check_in(body: CheckInRequest):
    try:
        result = await orchestrator.check_in(
            guest_name=body.guest_name,
            room_number=body.room_number,
            nights=body.nights,
            check_in_date=body.check_in_date,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("output"))
        return result
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))


@app.post("/checkout")
async def check_out(body: CheckOutRequest):
    try:
        result = await orchestrator.check_out(
            guest_name=body.guest_name,
            room_number=body.room_number,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("output"))
        return result
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))


@app.post("/cleaning")
async def clean_room(body: CleanRoomRequest):
    try:
        result = await orchestrator.clean_room(
            room_number=body.room_number,
            priority=body.priority,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("output"))
        return result
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))


@app.post("/requests")
async def guest_request(body: GuestRequestBody):
    try:
        result = await orchestrator.guest_request(
            guest_name=body.guest_name,
            room_number=body.room_number,
            request_type=body.request_type,
            details=body.details,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("output"))
        return result
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))


@app.post("/billing/charge")
async def add_charge(body: AddChargeRequest):
    try:
        result = await orchestrator.add_charge(
            guest_name=body.guest_name,
            room_number=body.room_number,
            amount=body.amount,
            description=body.description,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("output"))
        return result
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
