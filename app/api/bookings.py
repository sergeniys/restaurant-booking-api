from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.booking import BookingCreate, BookingList, BookingOut
from app.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def get_booking_service(session: Annotated[AsyncSession, Depends(get_db)]) -> BookingService:
    return BookingService(session=session)


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать бронь",
    description=(
        "Валидирует данные, бронирует слот (не более 10 активных броней на слот) "
        "и возвращает созданную бронь."
    ),
)
async def create_booking(
    booking_in: BookingCreate,
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> BookingOut:
    booking = await service.create_booking(booking_in)
    return BookingOut.model_validate(booking)


@router.get(
    "",
    response_model=BookingList,
    status_code=status.HTTP_200_OK,
    summary="Список броней",
    description=(
        "Список броней, отсортированный по дате и времени. "
        "Поддерживает фильтрацию по дате и пагинацию."
    ),
)
async def list_bookings(
    service: Annotated[BookingService, Depends(get_booking_service)],
    date_filter: Annotated[
        date | None, Query(alias="date", description="Фильтр по дате брони")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Лимит броней в ответе (1-100)")] = 20,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
) -> BookingList:
    items, total = await service.list_bookings(
        booking_date=date_filter,
        limit=limit,
        offset=offset,
    )
    return BookingList(
        items=[BookingOut.model_validate(item) for item in items],
        total=total,
    )


@router.get(
    "/{id}",
    response_model=BookingOut,
    status_code=status.HTTP_200_OK,
    summary="Получить бронь по id",
    description=(
        "Возвращает объект брони по её уникальному идентификатору или 404, если не найдена."
    ),
)
async def get_booking(
    booking_id: Annotated[int, Path(alias="id", description="ID брони", ge=1)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> BookingOut:
    booking = await service.get_booking_by_id(booking_id)
    return BookingOut.model_validate(booking)


@router.delete(
    "/{id}",
    response_model=BookingOut,
    status_code=status.HTTP_200_OK,
    summary="Отменить бронь",
    description=(
        "Меняет статус брони на cancelled, запись физически не удаляется. Освобождает слот."
    ),
)
async def cancel_booking(
    booking_id: Annotated[int, Path(alias="id", description="ID брони", ge=1)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> BookingOut:
    booking = await service.cancel_booking(booking_id)
    return BookingOut.model_validate(booking)
