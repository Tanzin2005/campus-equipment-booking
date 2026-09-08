from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class Registration(Login):
    name: Name
    password: str = Field(min_length=12, max_length=128)


class User(BaseModel):
    id: int
    name: str
    email: str
    role: Literal["student", "admin"]


class AuthResponse(BaseModel):
    user: User
    csrf_token: str


class Interval(Input):
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def validate_interval(self):
        self.start_at, self.end_at = utc(self.start_at), utc(self.end_at)
        if self.end_at <= self.start_at:
            raise ValueError("End time must be after start time")
        if self.start_at <= datetime.now(timezone.utc):
            raise ValueError("Start time must be in the future")
        if self.end_at - self.start_at > timedelta(hours=24):
            raise ValueError("Each reservation can last up to 24 hours")
        return self


class BookingRequest(Interval):
    equipment_id: int = Field(gt=0)
    purpose: Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)] = ""


class EquipmentInput(Input):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    category: Literal["Electronics", "Computing", "Presentation", "Fabrication"] = "Electronics"
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=600)] = ""
    active: bool = True


class Equipment(EquipmentInput):
    id: int
    available: bool | None = None


class Booking(BaseModel):
    id: int
    equipment_id: int
    user_id: int | None
    student_name: str
    purpose: str
    start_at: AwareDatetime
    end_at: AwareDatetime
    status: Literal["confirmed", "cancelled"]
    created_at: AwareDatetime
    equipment_name: str
    location: str

    @field_validator("start_at", "end_at", "created_at", mode="before")
    @classmethod
    def normalize_datetime(cls, value):
        return utc(value) if isinstance(value, datetime) else value


class BookingPage(BaseModel):
    items: list[Booking]
    total: int
    limit: int
    offset: int
