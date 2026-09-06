"""Milestone 1: local demonstration API, before authentication is added."""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.database import connect, initialize


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_id: int = Field(gt=0)
    student_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def check_times(self):
        # Normalize before comparing, including inputs with different offsets.
        self.start_at = self.start_at.astimezone(timezone.utc)
        self.end_at = self.end_at.astimezone(timezone.utc)
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.start_at <= datetime.now(timezone.utc):
            raise ValueError("start_at must be in the future")
        return self


class Equipment(BaseModel):
    id: int
    name: str
    location: str


class Booking(BaseModel):
    id: int
    equipment_id: int
    student_name: str
    start_at: AwareDatetime
    end_at: AwareDatetime


def create_app(db_path: Path | None = None) -> FastAPI:
    path = db_path if db_path is not None else Path(os.getenv("BOOKING_DB", "data/bookings.db"))

    @asynccontextmanager
    async def lifespan(app):
        initialize(path)
        yield

    app = FastAPI(
        title="Campus Equipment Booking", version="0.1.0",
        description="Local learning prototype. Authentication and ownership checks are planned.",
        lifespan=lifespan,
    )

    @app.get("/")
    def home():
        return {"message": "Campus Equipment Booking API", "documentation": "/docs"}

    @app.get("/equipment", response_model=list[Equipment])
    def list_equipment():
        with connect(path) as db:
            return [dict(row) for row in db.execute("SELECT * FROM equipment ORDER BY id")]

    @app.get("/bookings", response_model=list[Booking])
    def list_bookings(
        equipment_id: Annotated[int | None, Query(gt=0)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        with connect(path) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM bookings WHERE (? IS NULL OR equipment_id = ?) "
                "ORDER BY start_at, id LIMIT ? OFFSET ?",
                (equipment_id, equipment_id, limit, offset),
            )]

    @app.post("/bookings", response_model=Booking, status_code=201)
    def create_booking(request: BookingRequest):
        # Fixed-width UTC timestamps sort chronologically as SQLite TEXT.
        start = request.start_at.isoformat(timespec="microseconds")
        end = request.end_at.isoformat(timespec="microseconds")
        with connect(path) as db:
            # Acquire the write lock BEFORE checking availability. Otherwise,
            # two requests could both see a free slot and both insert it.
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM equipment WHERE id = ?", (request.equipment_id,)).fetchone():
                raise HTTPException(404, "Equipment not found")
            conflict = db.execute(
                "SELECT 1 FROM bookings WHERE equipment_id = ? "
                "AND start_at < ? AND end_at > ? LIMIT 1",
                (request.equipment_id, end, start),
            ).fetchone()
            if conflict:
                raise HTTPException(409, "Equipment is already booked during that time")
            cursor = db.execute(
                "INSERT INTO bookings (equipment_id, student_name, start_at, end_at) VALUES (?, ?, ?, ?)",
                (request.equipment_id, request.student_name, start, end),
            )
            return dict(db.execute("SELECT * FROM bookings WHERE id = ?", (cursor.lastrowid,)).fetchone())

    return app


app = create_app()
