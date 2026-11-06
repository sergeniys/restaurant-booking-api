import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BookingAlreadyCancelledException
from app.schemas.booking import BookingCreate, BookingStatus
from app.services.booking_service import BookingService


def get_future_date(days_ahead: int = 10) -> str:
    moscow_tz = ZoneInfo(settings.TIMEZONE)
    return (datetime.now(moscow_tz).date() + timedelta(days=days_ahead)).isoformat()


@pytest.mark.asyncio
async def test_create_booking_success(client: AsyncClient):
    payload = {
        "name": "Анна Петрова",
        "phone": "+7 (999) 123-45-67",
        "booking_date": get_future_date(5),
        "booking_time": "19:00",
        "guests": 4,
    }
    response = await client.post("/bookings", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Анна Петрова"
    assert data["phone"] == "+79991234567"
    assert data["booking_date"] == payload["booking_date"]
    assert data["booking_time"] == "19:00"
    assert data["guests"] == 4
    assert data["status"] == "active"
    assert "created_at" in data
    assert data["created_at"].endswith("+00:00") or data["created_at"].endswith("Z")


@pytest.mark.asyncio
async def test_create_booking_name_validation(client: AsyncClient):
    base_payload = {
        "phone": "+79991234567",
        "booking_date": get_future_date(5),
        "booking_time": "18:00",
        "guests": 2,
    }

    # Too short
    res = await client.post("/bookings", json={**base_payload, "name": "A"})
    assert res.status_code == 422

    # Too short after strip
    res = await client.post("/bookings", json={**base_payload, "name": "  A  "})
    assert res.status_code == 422

    # Whitespace only
    res = await client.post("/bookings", json={**base_payload, "name": "   "})
    assert res.status_code == 422

    # Too long (>50)
    res = await client.post("/bookings", json={**base_payload, "name": "A" * 51})
    assert res.status_code == 422

    # Digits and symbols not allowed
    res = await client.post("/bookings", json={**base_payload, "name": "Анна123"})
    assert res.status_code == 422

    res = await client.post("/bookings", json={**base_payload, "name": "John@Doe"})
    assert res.status_code == 422

    res = await client.post("/bookings", json={**base_payload, "name": "---"})
    assert res.status_code == 422

    # Tab not allowed
    res = await client.post("/bookings", json={**base_payload, "name": "Анна\tПетрова"})
    assert res.status_code == 422

    # 50 chars after strip with spaces around -> 201
    name_50 = "   " + "А" * 50 + "   "
    res = await client.post("/bookings", json={**base_payload, "name": name_50})
    assert res.status_code == 201
    assert res.json()["name"] == "А" * 50

    # 51 chars after strip with spaces around -> 422
    name_51 = "   " + "А" * 51 + "   "
    res = await client.post("/bookings", json={**base_payload, "name": name_51})
    assert res.status_code == 422

    # Valid name with spaces stripped
    res = await client.post("/bookings", json={**base_payload, "name": "  Иван Иванов  "})
    assert res.status_code == 201
    assert res.json()["name"] == "Иван Иванов"

    # Valid hyphenated name
    res = await client.post("/bookings", json={**base_payload, "name": "Анна-Мария"})
    assert res.status_code == 201
    assert res.json()["name"] == "Анна-Мария"


@pytest.mark.asyncio
async def test_create_booking_phone_validation(client: AsyncClient):
    base_payload = {
        "name": "Иван Смирнов",
        "booking_date": get_future_date(6),
        "booking_time": "15:00",
        "guests": 2,
    }

    # Phone starting with 8
    res = await client.post("/bookings", json={**base_payload, "phone": "89991234567"})
    assert res.status_code == 201
    assert res.json()["phone"] == "+79991234567"

    # Phone with brackets, hyphens and spaces
    res = await client.post("/bookings", json={**base_payload, "phone": "8 (916) 123-45-67"})
    assert res.status_code == 201
    assert res.json()["phone"] == "+79161234567"

    # Invalid length
    res = await client.post("/bookings", json={**base_payload, "phone": "+799912345"})
    assert res.status_code == 422

    res = await client.post("/bookings", json={**base_payload, "phone": "+799912345678"})
    assert res.status_code == 422

    # Invalid country prefix
    res = await client.post("/bookings", json={**base_payload, "phone": "+19991234567"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_booking_date_validation(client: AsyncClient):
    moscow_tz = ZoneInfo(settings.TIMEZONE)
    today = datetime.now(moscow_tz).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    day_90 = (today + timedelta(days=90)).isoformat()
    day_91 = (today + timedelta(days=91)).isoformat()

    base_payload = {
        "name": "Тест Даты",
        "phone": "+79991234567",
        "booking_time": "20:00",
        "guests": 2,
    }

    # Yesterday -> 422
    res = await client.post("/bookings", json={**base_payload, "booking_date": yesterday})
    assert res.status_code == 422

    # 91 days ahead -> 422
    res = await client.post("/bookings", json={**base_payload, "booking_date": day_91})
    assert res.status_code == 422

    # 90 days ahead -> 201
    res = await client.post("/bookings", json={**base_payload, "booking_date": day_90})
    assert res.status_code == 201


@pytest.mark.asyncio
async def test_create_booking_time_validation(client: AsyncClient):
    base_payload = {
        "name": "Тест Времени",
        "phone": "+79991234567",
        "booking_date": get_future_date(10),
        "guests": 2,
    }

    # Non-whole hour (e.g. 12:30) -> 422
    res = await client.post("/bookings", json={**base_payload, "booking_time": "12:30"})
    assert res.status_code == 422

    # With seconds (e.g. 12:00:30) -> 422
    res = await client.post("/bookings", json={**base_payload, "booking_time": "12:00:30"})
    assert res.status_code == 422

    # Before opening hour (11:00) -> 422
    res = await client.post("/bookings", json={**base_payload, "booking_time": "11:00"})
    assert res.status_code == 422

    # After closing hour (23:00) -> 422
    res = await client.post("/bookings", json={**base_payload, "booking_time": "23:00"})
    assert res.status_code == 422

    # Whole hours 12:00 and 22:00 -> 201
    res = await client.post("/bookings", json={**base_payload, "booking_time": "12:00"})
    assert res.status_code == 201

    res = await client.post("/bookings", json={**base_payload, "booking_time": "22:00"})
    assert res.status_code == 201


@pytest.mark.asyncio
async def test_create_booking_past_slot_today(client: AsyncClient):
    moscow_tz = ZoneInfo(settings.TIMEZONE)
    now_moscow = datetime.now(moscow_tz)
    today_str = now_moscow.date().isoformat()

    # If current Moscow time is at or after 12:00, 12:00 slot is in the past
    if now_moscow.hour >= 12:
        payload = {
            "name": "Прошедший Слот",
            "phone": "+79991234567",
            "booking_date": today_str,
            "booking_time": "12:00",
            "guests": 2,
        }
        res = await client.post("/bookings", json=payload)
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_booking_guests_validation(client: AsyncClient):
    base_payload = {
        "name": "Гости Тест",
        "phone": "+79991234567",
        "booking_date": get_future_date(7),
        "booking_time": "17:00",
    }

    # 0 guests -> 422
    res = await client.post("/bookings", json={**base_payload, "guests": 0})
    assert res.status_code == 422

    # Negative guests -> 422
    res = await client.post("/bookings", json={**base_payload, "guests": -1})
    assert res.status_code == 422

    # 13 guests -> 422
    res = await client.post("/bookings", json={**base_payload, "guests": 13})
    assert res.status_code == 422

    # String, float, bool not allowed (StrictInt)
    res = await client.post("/bookings", json={**base_payload, "guests": "5"})
    assert res.status_code == 422

    res = await client.post("/bookings", json={**base_payload, "guests": 5.0})
    assert res.status_code == 422

    res = await client.post("/bookings", json={**base_payload, "guests": True})
    assert res.status_code == 422

    # 1 guest -> 201
    res = await client.post("/bookings", json={**base_payload, "guests": 1})
    assert res.status_code == 201

    # 12 guests -> 201
    res = await client.post("/bookings", json={**base_payload, "guests": 12})
    assert res.status_code == 201


@pytest.mark.asyncio
async def test_get_booking_by_id(client: AsyncClient):
    # Create booking
    payload = {
        "name": "Елена Соколова",
        "phone": "+79991112233",
        "booking_date": get_future_date(8),
        "booking_time": "16:00",
        "guests": 3,
    }
    create_res = await client.post("/bookings", json=payload)
    assert create_res.status_code == 201
    booking_id = create_res.json()["id"]

    # Get by id
    get_res = await client.get(f"/bookings/{booking_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == booking_id
    assert get_res.json()["name"] == "Елена Соколова"

    # Non-existent id -> 404
    not_found_res = await client.get("/bookings/999999")
    assert not_found_res.status_code == 404
    assert not_found_res.json() == {"detail": "Booking not found"}

    # ID 0 and negative -> 404 Not Found (valid integer format, but no such booking)
    res_0 = await client.get("/bookings/0")
    assert res_0.status_code == 404
    assert res_0.json() == {"detail": "Booking not found"}

    res_neg = await client.get("/bookings/-1")
    assert res_neg.status_code == 404
    assert res_neg.json() == {"detail": "Booking not found"}

    # Invalid id type -> 422
    bad_id_res = await client.get("/bookings/not-an-id")
    assert bad_id_res.status_code == 422


@pytest.mark.asyncio
async def test_cancel_booking(client: AsyncClient):
    payload = {
        "name": "Дмитрий Волков",
        "phone": "+79993334455",
        "booking_date": get_future_date(9),
        "booking_time": "18:00",
        "guests": 2,
    }
    create_res = await client.post("/bookings", json=payload)
    assert create_res.status_code == 201
    booking_id = create_res.json()["id"]

    # Cancel booking -> 200
    cancel_res = await client.delete(f"/bookings/{booking_id}")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # Repeat cancellation -> 409
    repeat_res = await client.delete(f"/bookings/{booking_id}")
    assert repeat_res.status_code == 409
    assert repeat_res.json() == {"detail": "Booking is already cancelled"}

    # Cancel non-existent booking -> 404
    not_found_res = await client.delete("/bookings/888888")
    assert not_found_res.status_code == 404
    assert not_found_res.json() == {"detail": "Booking not found"}

    # Cancel id 0 -> 404
    res_cancel_0 = await client.delete("/bookings/0")
    assert res_cancel_0.status_code == 404
    assert res_cancel_0.json() == {"detail": "Booking not found"}


@pytest.mark.asyncio
async def test_slot_capacity_and_reuse_after_cancellation(client: AsyncClient):
    target_date = get_future_date(12)
    slot_time = "20:00"

    # Book 10 tables on the same slot
    created_ids = []
    for i in range(10):
        res = await client.post(
            "/bookings",
            json={
                "name": f"Гость {chr(65 + i)}",
                "phone": f"+7999123450{i}",
                "booking_date": target_date,
                "booking_time": slot_time,
                "guests": 2,
            },
        )
        assert res.status_code == 201
        created_ids.append(res.json()["id"])

    # 11th booking should fail with 409
    res_11 = await client.post(
        "/bookings",
        json={
            "name": "Лишний Гость",
            "phone": "+79999999999",
            "booking_date": target_date,
            "booking_time": slot_time,
            "guests": 2,
        },
    )
    assert res_11.status_code == 409
    assert res_11.json() == {"detail": "Slot is fully booked"}

    # Cancel one booking to free up a table
    cancel_res = await client.delete(f"/bookings/{created_ids[0]}")
    assert cancel_res.status_code == 200

    # Booking on the same slot should now succeed
    res_retry = await client.post(
        "/bookings",
        json={
            "name": "Новый Гость",
            "phone": "+79999999999",
            "booking_date": target_date,
            "booking_time": slot_time,
            "guests": 2,
        },
    )
    assert res_retry.status_code == 201

    # And next one fails again with 409
    res_full_again = await client.post(
        "/bookings",
        json={
            "name": "Еще Один Гость",
            "phone": "+79998887766",
            "booking_date": target_date,
            "booking_time": slot_time,
            "guests": 2,
        },
    )
    assert res_full_again.status_code == 409
    assert res_full_again.json() == {"detail": "Slot is fully booked"}


@pytest.mark.asyncio
async def test_list_bookings_sorting_and_date_filter(client: AsyncClient):
    date1 = get_future_date(15)
    date2 = get_future_date(16)

    # Insert bookings in non-sorted order
    await client.post(
        "/bookings",
        json={
            "name": "Бронь Б",
            "phone": "+79991111111",
            "booking_date": date1,
            "booking_time": "20:00",
            "guests": 2,
        },
    )
    await client.post(
        "/bookings",
        json={
            "name": "Бронь А",
            "phone": "+79992222222",
            "booking_date": date1,
            "booking_time": "14:00",
            "guests": 2,
        },
    )
    await client.post(
        "/bookings",
        json={
            "name": "Бронь В",
            "phone": "+79993333333",
            "booking_date": date2,
            "booking_time": "12:00",
            "guests": 2,
        },
    )

    # List all
    res = await client.get("/bookings")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    items = data["items"]
    assert items[0]["name"] == "Бронь А"  # 14:00 on date1
    assert items[1]["name"] == "Бронь Б"  # 20:00 on date1
    assert items[2]["name"] == "Бронь В"  # 12:00 on date2

    # Filter by date1
    res_filter = await client.get(f"/bookings?date={date1}")
    assert res_filter.status_code == 200
    filter_data = res_filter.json()
    assert filter_data["total"] == 2
    assert len(filter_data["items"]) == 2
    assert all(item["booking_date"] == date1 for item in filter_data["items"])


@pytest.mark.asyncio
async def test_list_bookings_pagination(client: AsyncClient):
    date_val = get_future_date(20)

    for i in range(5):
        res_create = await client.post(
            "/bookings",
            json={
                "name": f"Гость {chr(65 + i)}",
                "phone": f"+7999123450{i}",
                "booking_date": date_val,
                "booking_time": f"{13 + i}:00",
                "guests": 2,
            },
        )
        assert res_create.status_code == 201

    # Page 1: limit=2, offset=0
    res_p1 = await client.get("/bookings?limit=2&offset=0")
    assert res_p1.status_code == 200
    d1 = res_p1.json()
    assert d1["total"] == 5
    assert len(d1["items"]) == 2

    # Page 2: limit=2, offset=2
    res_p2 = await client.get("/bookings?limit=2&offset=2")
    assert res_p2.status_code == 200
    d2 = res_p2.json()
    assert d2["total"] == 5
    assert len(d2["items"]) == 2
    assert d1["items"][0]["id"] != d2["items"][0]["id"]

    # Page 3: limit=2, offset=4
    res_p3 = await client.get("/bookings?limit=2&offset=4")
    assert res_p3.status_code == 200
    d3 = res_p3.json()
    assert d3["total"] == 5
    assert len(d3["items"]) == 1


@pytest.mark.asyncio
async def test_service_layer_direct(db_session: AsyncSession):
    service = BookingService(session=db_session)
    booking_date = datetime.now(ZoneInfo(settings.TIMEZONE)).date() + timedelta(days=25)

    create_data = BookingCreate(
        name="Сергей Васильев",
        phone="+79990001122",
        booking_date=booking_date,
        booking_time="19:00",
        guests=4,
    )
    booking = await service.create_booking(create_data)
    assert booking.id is not None
    assert booking.name == "Сергей Васильев"
    assert booking.status == BookingStatus.ACTIVE

    fetched = await service.get_booking_by_id(booking.id)
    assert fetched.id == booking.id

    cancelled = await service.cancel_booking(booking.id)
    assert cancelled.status == BookingStatus.CANCELLED

    with pytest.raises(BookingAlreadyCancelledException):
        await service.cancel_booking(booking.id)


@pytest.mark.asyncio
async def test_race_condition_protection(client: AsyncClient):
    """Bonus: Verify race condition protection under concurrent load.

    When 9 tables are booked and multiple concurrent requests compete
    for the last 10th table, exactly one must succeed with 201 and
    all others must be rejected with 409 (Slot is fully booked).
    """
    target_date = get_future_date(30)
    slot_time = "19:00"

    # Pre-fill 9 slots
    for i in range(9):
        res = await client.post(
            "/bookings",
            json={
                "name": f"Гость Предварительный {chr(65 + i)}",
                "phone": f"+7999123450{i}",
                "booking_date": target_date,
                "booking_time": slot_time,
                "guests": 2,
            },
        )
        assert res.status_code == 201

    # Send 10 concurrent requests simultaneously competing for the single remaining 10th slot
    async def book_attempt(index: int):
        return await client.post(
            "/bookings",
            json={
                "name": f"Гость Конкурентный {chr(75 + index)}",
                "phone": f"+7999555660{index}",
                "booking_date": target_date,
                "booking_time": slot_time,
                "guests": 2,
            },
        )

    responses = await asyncio.gather(*(book_attempt(i) for i in range(10)))

    status_codes = [r.status_code for r in responses]
    success_count = status_codes.count(201)
    conflict_count = status_codes.count(409)

    # Exactly one request must have acquired the last slot
    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert conflict_count == 9, f"Expected 9 conflicts, got {conflict_count}"

    # Verify every 409 has detail "Slot is fully booked"
    for r in responses:
        if r.status_code == 409:
            assert r.json() == {"detail": "Slot is fully booked"}

    # Verify total active bookings for this slot in DB is exactly 10
    list_res = await client.get(f"/bookings?date={target_date}")
    assert list_res.status_code == 200
    active_in_slot = [
        b
        for b in list_res.json()["items"]
        if b["booking_time"] == slot_time and b["status"] == "active"
    ]
    assert len(active_in_slot) == 10
