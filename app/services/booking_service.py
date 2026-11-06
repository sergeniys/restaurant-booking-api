import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BookingAlreadyCancelledException,
    BookingNotFoundException,
    SlotFullyBookedException,
)
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingStatus


class SlotLockManager:
    """Provides per-slot asyncio locks to prevent race conditions when creating bookings."""

    def __init__(self) -> None:
        self._locks: dict[tuple[date, time], asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def lock_slot(self, booking_date: date, booking_time: time) -> AsyncGenerator[None, None]:
        key = (booking_date, booking_time)
        async with self._guard:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            lock = self._locks[key]

        async with lock:
            yield


# Global lock manager instance shared across requests
slot_lock_manager = SlotLockManager()


class BookingService:
    def __init__(
        self, session: AsyncSession, lock_manager: SlotLockManager = slot_lock_manager
    ) -> None:
        self.session = session
        self.lock_manager = lock_manager

    async def create_booking(self, booking_in: BookingCreate) -> Booking:
        # Acquire slot-specific lock to guarantee atomic slot check and booking
        async with self.lock_manager.lock_slot(booking_in.booking_date, booking_in.booking_time):
            # Count currently active bookings for the requested slot
            count_stmt = select(func.count(Booking.id)).where(
                Booking.booking_date == booking_in.booking_date,
                Booking.booking_time == booking_in.booking_time,
                Booking.status == BookingStatus.ACTIVE,
            )
            active_count = await self.session.scalar(count_stmt) or 0

            if active_count >= settings.MAX_TABLES_PER_SLOT:
                raise SlotFullyBookedException()

            booking = Booking(
                name=booking_in.name,
                phone=booking_in.phone,
                booking_date=booking_in.booking_date,
                booking_time=booking_in.booking_time,
                guests=booking_in.guests,
                status=BookingStatus.ACTIVE,
            )
            self.session.add(booking)
            await self.session.commit()
            await self.session.refresh(booking)
            return booking

    async def get_booking_by_id(self, booking_id: int) -> Booking:
        stmt = select(Booking).where(Booking.id == booking_id)
        booking = await self.session.scalar(stmt)
        if not booking:
            raise BookingNotFoundException()
        return booking

    async def cancel_booking(self, booking_id: int) -> Booking:
        booking = await self.get_booking_by_id(booking_id)
        if booking.status == BookingStatus.CANCELLED:
            raise BookingAlreadyCancelledException()

        booking.status = BookingStatus.CANCELLED
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def list_bookings(
        self,
        booking_date: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[Booking], int]:
        count_stmt = select(func.count(Booking.id))
        if booking_date is not None:
            count_stmt = count_stmt.where(Booking.booking_date == booking_date)
        total = await self.session.scalar(count_stmt) or 0

        query = select(Booking)
        if booking_date is not None:
            query = query.where(Booking.booking_date == booking_date)

        query = (
            query.order_by(
                Booking.booking_date.asc(),
                Booking.booking_time.asc(),
                Booking.id.asc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(query)
        items = result.scalars().all()
        return items, total
