# -*- coding: utf-8 -*-
"""SE373 · Tests for Phase 2: Mock Tools."""
import pytest
from flight_booking_agent.mock_data import MockFlightDatabase
from flight_booking_agent.tools import (
    raw_search_flights,
    raw_get_flight_details,
    raw_check_seat_availability,
    raw_calculate_price,
    raw_book_flight,
    create_flight_tools,
)


@pytest.fixture
def fresh_db():
    db = MockFlightDatabase()
    db.reset()
    return db


def test_tool_01_search_flights_success(fresh_db):
    """TOOL-01: search_flights thành công trả về danh sách flights cấu trúc rõ ràng."""
    res = raw_search_flights(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        db=fresh_db,
    )
    assert res["status"] == "ok"
    assert res["count"] == 4
    assert len(res["flights"]) == 4
    assert any(f["flight_id"] == "VN210" for f in res["flights"])


def test_tool_02_search_flights_not_found(fresh_db):
    """TOOL-02: search_flights không tìm thấy trả về not_found kèm hint gợi ý."""
    res = raw_search_flights(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-20",  # ngày không có chuyến
        db=fresh_db,
    )
    assert res["status"] == "not_found"
    assert res["count"] == 0
    assert "hint" in res
    assert "thử đổi ngày bay" in res["hint"]


def test_tool_03_get_flight_details_invalid_id(fresh_db):
    """TOOL-03: get_flight_details với invalid ID trả về error có mã cụ thể."""
    res = raw_get_flight_details("UNKNOWN_999", db=fresh_db)
    assert res["status"] == "error"
    assert res["error_code"] == "FLIGHT_NOT_FOUND"

    # Valid ID
    valid_res = raw_get_flight_details("VN210", db=fresh_db)
    assert valid_res["status"] == "ok"
    assert valid_res["flight"]["airline"] == "Vietnam Airlines"


def test_tool_04_check_seat_availability_sold_out(fresh_db):
    """TOOL-04: check_seat_availability với flight sold out trả về sold_out."""
    # VJ624 là chuyến sold out (available_seats = 0)
    res = raw_check_seat_availability("VJ624", passenger_count=1, db=fresh_db)
    assert res["status"] == "sold_out"
    assert res["available"] is False
    assert res["available_seats"] == 0

    # Chuyến còn 5 ghế nhưng yêu cầu 6 khách
    res_not_enough = raw_check_seat_availability("VN210", passenger_count=6, db=fresh_db)
    assert res_not_enough["status"] == "sold_out"
    assert res_not_enough["available"] is False

    # Chuyến còn đủ ghế
    res_ok = raw_check_seat_availability("VN210", passenger_count=2, db=fresh_db)
    assert res_ok["status"] == "ok"
    assert res_ok["available"] is True
    assert res_ok["available_seats"] == 5


def test_tool_05_calculate_price_deterministic(fresh_db):
    """TOOL-05: calculate_price deterministic."""
    res1 = raw_calculate_price("VN210", passenger_count=2, db=fresh_db)
    res2 = raw_calculate_price("VN210", passenger_count=2, db=fresh_db)
    assert res1 == res2
    assert res1["status"] == "ok"
    assert res1["unit_price"] == 1800000
    assert res1["passenger_count"] == 2
    assert res1["total_price"] == 3600000


def test_tool_06_book_flight_writes_db_correctly(fresh_db):
    """TOOL-06: book_flight ghi DB đúng khi thông tin hợp lệ."""
    res = raw_book_flight(
        flight_id="VN210",
        passenger_name="Nguyen Van A",
        passenger_count=2,
        total_price=3600000,
        db=fresh_db,
    )
    assert res["status"] == "CONFIRMED"
    booking_id = res["booking_id"]
    assert booking_id.startswith("BK")

    # Kiểm tra DB thật sự đã ghi
    saved_booking = fresh_db.get_booking(booking_id)
    assert saved_booking is not None
    assert saved_booking["passenger_name"] == "Nguyen Van A"
    assert saved_booking["total_price"] == 3600000

    # Ghế đã giảm
    assert fresh_db.get_available_seats("VN210") == 3


def test_tool_07_cannot_book_more_seats_than_available(fresh_db):
    """TOOL-07: Không cho book vượt số ghế còn lại."""
    res = raw_book_flight(
        flight_id="VN210",
        passenger_name="Nhom Khach",
        passenger_count=10,  # chỉ có 5 ghế
        total_price=18000000,
        db=fresh_db,
    )
    assert res["status"] == "error"
    assert res["error_code"] == "SEATS_NOT_AVAILABLE"

    # Thử book chuyến sold out
    res_soldout = raw_book_flight(
        flight_id="VJ624",
        passenger_name="Khach Don",
        passenger_count=1,
        total_price=950000,
        db=fresh_db,
    )
    assert res_soldout["status"] == "error"
    assert res_soldout["error_code"] == "SEATS_NOT_AVAILABLE"


def test_tool_book_flight_price_mismatch(fresh_db):
    """book_flight phát hiện chênh lệch giá không khớp giá niêm yết."""
    res = raw_book_flight(
        flight_id="VN210",
        passenger_name="Khach Tra Gia",
        passenger_count=1,
        total_price=1000000,  # Giá đúng là 1800000
        db=fresh_db,
    )
    assert res["status"] == "error"
    assert res["error_code"] == "PRICE_MISMATCH"


def test_langchain_tools_wrapper(fresh_db):
    """Kiểm tra LangChain tools invoke hoạt động đồng bộ với raw tools."""
    tools = create_flight_tools(fresh_db)
    tool_map = {t.name: t for t in tools}

    assert "search_flights" in tool_map
    assert "get_flight_details" in tool_map
    assert "check_seat_availability" in tool_map
    assert "calculate_price" in tool_map
    assert "book_flight" in tool_map

    # Gọi search qua LangChain tool
    search_tool = tool_map["search_flights"]
    res = search_tool.invoke({
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
    })
    assert res["status"] == "ok"
    assert res["count"] == 4
