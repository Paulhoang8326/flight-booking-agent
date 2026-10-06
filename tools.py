# -*- coding: utf-8 -*-
"""SE373 · Flight Booking Agent · Phase 2: Mock Tools.

Bộ 5 tools thao tác với hệ thống đặt vé:
1. search_flights: Tìm chuyến bay theo tiêu chí.
2. get_flight_details: Tra cứu chi tiết một chuyến bay theo ID.
3. check_seat_availability: Kiểm tra tình trạng chỗ trống cho số lượng khách.
4. calculate_price: Tính tổng giá vé xác định theo đơn giá và số khách.
5. book_flight: Thực hiện ghi nhận đặt chỗ vào Mock DB.

LƯU Ý THIẾT KẾ:
- Tool `book_flight` KHÔNG kiểm tra quyền (Human Permission). Việc kiểm quyền
  thuộc trách nhiệm hoàn toàn của Harness (PermissionChecker).
- Tool chỉ validate nghiệp vụ: chuyến bay tồn tại, số khách hợp lệ, đủ ghế,
  và tổng tiền khớp với giá niêm yết.
- Mọi tool trả về dictionary có cấu trúc rõ ràng (không trả text mơ hồ).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from langchain_core.tools import tool

from flight_booking_agent.mock_data import MockFlightDatabase, default_db

# Biến database đang hoạt động (có thể tráo đổi cho từng kịch bản benchmark)
_ACTIVE_DB: MockFlightDatabase = default_db


def set_active_db(db: MockFlightDatabase) -> None:
    """Thiết lập mock database đang hoạt động cho các standalone tool calls."""
    global _ACTIVE_DB
    _ACTIVE_DB = db


def get_active_db() -> MockFlightDatabase:
    """Lấy database đang hoạt động."""
    return _ACTIVE_DB


# -----------------------------------------------------------------------------
# 1. search_flights
# -----------------------------------------------------------------------------
def raw_search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: Optional[str] = None,
    airline: Optional[str] = None,
    max_budget: Optional[int] = None,
    db: Optional[MockFlightDatabase] = None,
) -> Dict[str, Any]:
    """Tìm chuyến bay theo các tiêu chí đã cho."""
    database = db or _ACTIVE_DB
    results = database.search_flights(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        cabin_class=cabin_class,
        airline=airline,
        max_budget=max_budget,
    )
    if not results:
        hint_parts = []
        if max_budget is not None:
            hint_parts.append("thử tăng ngân sách")
        hint_parts.append("hoặc thử đổi ngày bay/hạng vé khác")
        return {
            "status": "not_found",
            "count": 0,
            "flights": [],
            "reason": f"Không tìm thấy chuyến bay từ {origin} đi {destination} ngày {departure_date}.",
            "hint": ", ".join(hint_parts),
        }

    return {
        "status": "ok",
        "count": len(results),
        "flights": results,
    }


# -----------------------------------------------------------------------------
# 2. get_flight_details
# -----------------------------------------------------------------------------
def raw_get_flight_details(
    flight_id: str,
    db: Optional[MockFlightDatabase] = None,
) -> Dict[str, Any]:
    """Tra cứu chi tiết một chuyến bay theo mã chuyến bay."""
    database = db or _ACTIVE_DB
    f = database.get_flight(flight_id)
    if not f:
        return {
            "status": "error",
            "error_code": "FLIGHT_NOT_FOUND",
            "message": f"Chuyến bay '{flight_id}' không tồn tại trong hệ thống.",
        }
    return {
        "status": "ok",
        "flight": f,
    }


# -----------------------------------------------------------------------------
# 3. check_seat_availability
# -----------------------------------------------------------------------------
def raw_check_seat_availability(
    flight_id: str,
    passenger_count: int = 1,
    db: Optional[MockFlightDatabase] = None,
) -> Dict[str, Any]:
    """Kiểm tra số ghế còn trống của chuyến bay có đáp ứng số khách hay không."""
    database = db or _ACTIVE_DB
    f = database.get_flight(flight_id)
    if not f:
        return {
            "status": "error",
            "error_code": "FLIGHT_NOT_FOUND",
            "message": f"Chuyến bay '{flight_id}' không tồn tại trong hệ thống.",
        }

    available_seats = f["available_seats"]
    if available_seats < passenger_count or available_seats == 0:
        return {
            "status": "sold_out",
            "available": False,
            "flight_id": f["flight_id"],
            "requested_seats": passenger_count,
            "available_seats": available_seats,
            "hint": f"Chuyến bay {flight_id} chỉ còn {available_seats} ghế, không đủ cho {passenger_count} khách.",
        }

    return {
        "status": "ok",
        "available": True,
        "flight_id": f["flight_id"],
        "requested_seats": passenger_count,
        "available_seats": available_seats,
    }


# -----------------------------------------------------------------------------
# 4. calculate_price
# -----------------------------------------------------------------------------
def raw_calculate_price(
    flight_id: str,
    passenger_count: int = 1,
    db: Optional[MockFlightDatabase] = None,
) -> Dict[str, Any]:
    """Tính tổng chi phí vé theo đơn giá niêm yết và số hành khách."""
    database = db or _ACTIVE_DB
    f = database.get_flight(flight_id)
    if not f:
        return {
            "status": "error",
            "error_code": "FLIGHT_NOT_FOUND",
            "message": f"Chuyến bay '{flight_id}' không tồn tại trong hệ thống.",
        }

    if passenger_count <= 0:
        return {
            "status": "error",
            "error_code": "INVALID_PASSENGER_COUNT",
            "message": "Số lượng hành khách phải lớn hơn 0.",
        }

    unit_price = f["base_price"]
    total_price = unit_price * passenger_count
    return {
        "status": "ok",
        "flight_id": f["flight_id"],
        "airline": f["airline"],
        "unit_price": unit_price,
        "passenger_count": passenger_count,
        "total_price": total_price,
    }


# -----------------------------------------------------------------------------
# 5. book_flight
# -----------------------------------------------------------------------------
def raw_book_flight(
    flight_id: str,
    passenger_name: str,
    passenger_count: int,
    total_price: int,
    db: Optional[MockFlightDatabase] = None,
) -> Dict[str, Any]:
    """Thực hiện đặt vé và ghi nhận vào Mock Database.

    CHÚ Ý: Tool này KHÔNG tự kiểm tra Human Permission.
    Harness (PermissionChecker) có trách nhiệm kiểm tra xem hành động đã được
    APPROVED hay chưa TRƯỚC KHI cho phép tool này chạy.
    """
    database = db or _ACTIVE_DB
    f = database.get_flight(flight_id)
    if not f:
        return {
            "status": "error",
            "error_code": "FLIGHT_NOT_FOUND",
            "message": f"Chuyến bay '{flight_id}' không tồn tại.",
        }

    if passenger_count <= 0:
        return {
            "status": "error",
            "error_code": "INVALID_PASSENGER_COUNT",
            "message": "Số lượng hành khách phải lớn hơn hoặc bằng 1.",
        }

    if not passenger_name or not passenger_name.strip():
        return {
            "status": "error",
            "error_code": "INVALID_PASSENGER_NAME",
            "message": "Tên hành khách không được để trống.",
        }

    expected_total = f["base_price"] * passenger_count
    if total_price != expected_total:
        return {
            "status": "error",
            "error_code": "PRICE_MISMATCH",
            "message": f"Tổng tiền không khớp. Niêm yết: {expected_total}đ ({f['base_price']}đ x {passenger_count}), nhận được: {total_price}đ.",
        }

    if f["available_seats"] < passenger_count:
        return {
            "status": "error",
            "error_code": "SEATS_NOT_AVAILABLE",
            "message": f"Không đủ ghế trống. Còn lại: {f['available_seats']}, yêu cầu: {passenger_count}.",
        }

    try:
        booking = database.create_booking(
            flight_id=flight_id,
            passenger_name=passenger_name,
            passenger_count=passenger_count,
            total_price=total_price,
        )
        return {
            "status": "CONFIRMED",
            "booking_id": booking["booking_id"],
            "booking": booking,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_code": "BOOKING_FAILED",
            "message": str(e),
        }


# -----------------------------------------------------------------------------
# LangChain Tool Factory & Exports
# -----------------------------------------------------------------------------
def create_flight_tools(db: Optional[MockFlightDatabase] = None) -> List[Any]:
    """Tạo danh sách 5 LangChain tools được liên kết với một MockFlightDatabase cụ thể."""
    target_db = db or _ACTIVE_DB

    @tool
    def search_flights(
        origin: str,
        destination: str,
        departure_date: str,
        cabin_class: Optional[str] = None,
        airline: Optional[str] = None,
        max_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Tìm chuyến bay theo điểm đi (SGN/HAN/DAD), điểm đến, ngày bay (YYYY-MM-DD), hạng vé, hãng bay hoặc ngân sách tối đa."""
        return raw_search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            cabin_class=cabin_class,
            airline=airline,
            max_budget=max_budget,
            db=target_db,
        )

    @tool
    def get_flight_details(flight_id: str) -> Dict[str, Any]:
        """Lấy thông tin chi tiết một chuyến bay theo mã chuyến bay (ví dụ 'VN210', 'VJ120')."""
        return raw_get_flight_details(flight_id=flight_id, db=target_db)

    @tool
    def check_seat_availability(flight_id: str, passenger_count: int = 1) -> Dict[str, Any]:
        """Kiểm tra xem chuyến bay còn đủ số lượng ghế trống cho hành khách hay không."""
        return raw_check_seat_availability(
            flight_id=flight_id, passenger_count=passenger_count, db=target_db
        )

    @tool
    def calculate_price(flight_id: str, passenger_count: int = 1) -> Dict[str, Any]:
        """Tính toán tổng chi phí đặt vé dựa trên đơn giá chuyến bay và số lượng hành khách."""
        return raw_calculate_price(
            flight_id=flight_id, passenger_count=passenger_count, db=target_db
        )

    @tool
    def book_flight(
        flight_id: str,
        passenger_name: str,
        passenger_count: int,
        total_price: int,
    ) -> Dict[str, Any]:
        """Thực hiện đặt vé máy bay và ghi nhận giao dịch vào hệ thống (Sensitive Write action)."""
        return raw_book_flight(
            flight_id=flight_id,
            passenger_name=passenger_name,
            passenger_count=passenger_count,
            total_price=total_price,
            db=target_db,
        )

    return [
        search_flights,
        get_flight_details,
        check_seat_availability,
        calculate_price,
        book_flight,
    ]


# Mặc định xuất 5 LangChain tools kết nối với default_db
search_flights, get_flight_details, check_seat_availability, calculate_price, book_flight = (
    create_flight_tools(default_db)
)
