# -*- coding: utf-8 -*-
"""SE373 · Tests for Phase 1: Mock Domain & Data."""
import pytest
from flight_booking_agent.mock_data import MockFlightDatabase, INITIAL_FLIGHTS


def test_db_01_search_valid_route():
    """DB-01: Search route hợp lệ trả đúng flight."""
    db = MockFlightDatabase()
    results = db.search_flights(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
    )
    # Có 4 chuyến SGN -> HAN (VN210, VJ120, QH202, VN214)
    assert len(results) == 4
    flight_ids = [f["flight_id"] for f in results]
    assert "VN210" in flight_ids
    assert "VJ120" in flight_ids


def test_db_02_sold_out_flight():
    """DB-02: Sold-out flight có available_seats == 0."""
    db = MockFlightDatabase()
    flight = db.get_flight("VJ624")
    assert flight is not None
    assert flight["available_seats"] == 0
    assert db.get_available_seats("VJ624") == 0


def test_db_03_booking_decreases_available_seats():
    """DB-03: Booking thành công làm giảm available seats và lưu booking."""
    db = MockFlightDatabase()
    initial_seats = db.get_available_seats("VN210")
    assert initial_seats == 5

    booking = db.create_booking(
        flight_id="VN210",
        passenger_name="Nguyen Van A",
        passenger_count=2,
        total_price=3600000,
    )
    assert booking["booking_id"] == "BK001"
    assert booking["status"] == "CONFIRMED"
    assert booking["passenger_name"] == "Nguyen Van A"
    assert booking["passenger_count"] == 2

    # Số ghế còn lại phải giảm 2
    new_seats = db.get_available_seats("VN210")
    assert new_seats == initial_seats - 2

    # Đọc lại booking từ DB
    saved = db.get_booking("BK001")
    assert saved is not None
    assert saved["flight_id"] == "VN210"


def test_db_04_reset_restores_state():
    """DB-04: reset() khôi phục hoàn toàn state."""
    db = MockFlightDatabase()
    # Thực hiện 1 booking
    db.create_booking(
        flight_id="VN210",
        passenger_name="Tran Thi B",
        passenger_count=3,
        total_price=5400000,
    )
    assert len(db.list_bookings()) == 1
    assert db.get_available_seats("VN210") == 2

    # Gọi reset
    db.reset()

    # Sau reset: không còn booking, seats phục hồi về 5
    assert len(db.list_bookings()) == 0
    assert db.get_booking("BK001") is None
    assert db.get_available_seats("VN210") == 5

    # Booking tiếp theo sẽ nhận lại BK001
    new_booking = db.create_booking(
        flight_id="VN210",
        passenger_name="Le Van C",
        passenger_count=1,
        total_price=1800000,
    )
    assert new_booking["booking_id"] == "BK001"


def test_db_case_e_multi_constraint_search():
    """Kiểm tra tìm kiếm đa ràng buộc: Vietnam Airlines + sáng (<12:00) + BUSINESS."""
    db = MockFlightDatabase()
    results = db.search_flights(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        cabin_class="BUSINESS",
        airline="Vietnam Airlines",
    )
    assert len(results) == 1
    assert results[0]["flight_id"] == "VN214"
    assert results[0]["departure_time"] == "10:00"
    assert results[0]["base_price"] == 3800000


def test_db_booking_exceeds_available_seats_raises():
    """Không cho phép book quá số ghế còn lại."""
    db = MockFlightDatabase()
    with pytest.raises(ValueError, match="Not enough seats"):
        db.create_booking(
            flight_id="VN210",
            passenger_name="Nhom Khach Dong",
            passenger_count=10,  # chỉ có 5 ghế
            total_price=18000000,
        )

    # Đặt chuyến đã hết vé (available_seats = 0)
    with pytest.raises(ValueError, match="Not enough seats"):
        db.create_booking(
            flight_id="VJ624",
            passenger_name="Khach Xui Xe",
            passenger_count=1,
            total_price=950000,
        )
