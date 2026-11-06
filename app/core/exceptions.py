from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class BookingNotFoundException(AppException):
    def __init__(self, detail: str = "Booking not found") -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class SlotFullyBookedException(AppException):
    def __init__(self, detail: str = "Slot is fully booked") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class BookingAlreadyCancelledException(AppException):
    def __init__(self, detail: str = "Booking is already cancelled") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def app_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
