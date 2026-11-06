import re
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any, Self
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_serializer,
    field_validator,
    model_validator,
)

from app.core.config import settings

PHONE_RE = re.compile(r"(\+7|8)\d{10}")
NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё -]+$")
TIME_FORMAT_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class BookingStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class BookingBase(BaseModel):
    name: str = Field(min_length=2, max_length=50, examples=["Анна Петрова"])
    phone: str = Field(examples=["+79991234567"])
    booking_date: date
    booking_time: time = Field(examples=["19:00"])
    guests: StrictInt = Field(ge=1, le=12)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_serializer("booking_time", when_used="json")
    def serialize_booking_time(self, v: time) -> str:
        return v.strftime("%H:%M")


class BookingCreate(BookingBase):
    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2 or len(cleaned) > 50:
            raise ValueError("Имя должно содержать от 2 до 50 символов после обрезки пробелов")
        if not NAME_RE.fullmatch(cleaned):
            raise ValueError(
                "Имя может содержать только символы кириллицы, латиницы, пробелы и дефис"
            )
        if not any(c.isalpha() for c in cleaned):
            raise ValueError("Имя должно содержать хотя бы одну букву")
        return cleaned

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        cleaned = re.sub(r"[\s()\-]", "", value)
        if not PHONE_RE.fullmatch(cleaned):
            raise ValueError("Введите номер в формате +7XXXXXXXXXX или 8XXXXXXXXXX")
        return "+7" + cleaned[-10:]

    @field_validator("booking_date")
    @classmethod
    def validate_booking_date(cls, value: date) -> date:
        moscow_tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(moscow_tz).date()
        max_date = today + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD)
        if value < today:
            raise ValueError("Дата бронирования не может быть в прошлом")
        if value > max_date:
            raise ValueError(
                f"Дата бронирования не может превышать "
                f"{settings.BOOKING_MAX_DAYS_AHEAD} дней от сегодняшней"
            )
        return value

    @field_validator("booking_time", mode="before")
    @classmethod
    def validate_booking_time_input(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not TIME_FORMAT_RE.fullmatch(value):
                raise ValueError(
                    "Время бронирования должно быть в формате HH:MM (целые часы 12:00-22:00)"
                )
        return value

    @field_validator("booking_time")
    @classmethod
    def validate_booking_time_slot(cls, value: time) -> time:
        if value.minute != 0 or value.second != 0 or value.microsecond != 0:
            raise ValueError("Допустимы только целые часы 12:00, 13:00 ... 22:00")
        if not (settings.BOOKING_OPEN_HOUR <= value.hour <= settings.BOOKING_CLOSE_HOUR):
            raise ValueError(
                f"Время бронирования должно быть между "
                f"{settings.BOOKING_OPEN_HOUR}:00 и {settings.BOOKING_CLOSE_HOUR}:00"
            )
        return value

    @model_validator(mode="after")
    def validate_not_past_slot(self) -> Self:
        moscow_tz = ZoneInfo(settings.TIMEZONE)
        now_moscow = datetime.now(moscow_tz)
        if self.booking_date == now_moscow.date():
            slot_dt = datetime.combine(self.booking_date, self.booking_time, tzinfo=moscow_tz)
            if slot_dt <= now_moscow:
                raise ValueError("Для сегодняшней даты нельзя выбрать уже прошедший слот")
        return self


class BookingOut(BookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: BookingStatus
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


class BookingList(BaseModel):
    items: list[BookingOut]
    total: int
