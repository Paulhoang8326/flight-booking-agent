# -*- coding: utf-8 -*-
"""SE373 · Tests for Phase 3: Core Harness & Extended Safety Harness."""
from datetime import date
import pytest

from flight_booking_agent.mock_data import MockFlightDatabase
from flight_booking_agent.harness import (
    DataValidator,
    PermissionChecker,
    PermissionStatus,
    CompletionChecker,
    HandoffManager,
    StopReasons,
    create_handoff,
    format_handoff_message,
    LoopDetector,
    BudgetLimiter,
    CoreHarness,
)


# =============================================================================
# A. TESTS FOR DATA VALIDATOR
# =============================================================================
def test_validator_route():
    validator = DataValidator()
    # SGN -> HAN: valid
    res_ok = validator.validate_route("SGN", "HAN")
    assert res_ok.valid is True

    # SGN -> SGN: invalid (same origin/dest)
    res_same = validator.validate_route("SGN", "SGN")
    assert res_same.valid is False
    assert res_same.error_code == "SAME_ORIGIN_DESTINATION"

    # XXX -> HAN: invalid origin
    res_unknown = validator.validate_route("XXX", "HAN")
    assert res_unknown.valid is False
    assert res_unknown.error_code == "INVALID_ORIGIN"

    # SGN -> YYY: invalid destination
    res_dest = validator.validate_route("SGN", "YYY")
    assert res_dest.valid is False
    assert res_dest.error_code == "INVALID_DESTINATION"


def test_validator_date():
    validator = DataValidator()
    fixed_ref = date(2026, 10, 1)

    # Valid future date
    res_ok = validator.validate_date("2026-10-15", reference_date=fixed_ref)
    assert res_ok.valid is True

    # 2026-10-32: invalid calendar date
    res_invalid_cal = validator.validate_date("2026-10-32", reference_date=fixed_ref)
    assert res_invalid_cal.valid is False
    assert res_invalid_cal.error_code == "INVALID_DATE_CALENDAR"

    # 2020-01-01: past date
    res_past = validator.validate_date("2020-01-01", reference_date=fixed_ref)
    assert res_past.valid is False
    assert res_past.error_code == "PAST_DATE"

    # Not a date string
    res_empty = validator.validate_date("", reference_date=fixed_ref)
    assert res_empty.valid is False
    assert res_empty.error_code == "INVALID_DATE_FORMAT"


def test_validator_passenger_count():
    validator = DataValidator()
    # count = 0: invalid
    res_zero = validator.validate_passenger_count(0)
    assert res_zero.valid is False
    assert res_zero.error_code == "INVALID_PASSENGER_COUNT"

    # count = -2: invalid
    res_neg = validator.validate_passenger_count(-2)
    assert res_neg.valid is False
    assert res_neg.error_code == "INVALID_PASSENGER_COUNT"

    # count = 10: exceeds max online booking
    res_over = validator.validate_passenger_count(10)
    assert res_over.valid is False
    assert res_over.error_code == "EXCEEDS_MAX_PASSENGERS"

    # count = 3: valid
    res_ok = validator.validate_passenger_count(3)
    assert res_ok.valid is True


def test_validator_budget():
    validator = DataValidator()
    # Negative budget: invalid
    res_neg = validator.validate_budget(-500000)
    assert res_neg.valid is False
    assert res_neg.error_code == "INVALID_BUDGET"

    # Zero budget: invalid
    res_zero = validator.validate_budget(0)
    assert res_zero.valid is False
    assert res_zero.error_code == "INVALID_BUDGET"

    # Positive budget: valid
    res_pos = validator.validate_budget(2000000)
    assert res_pos.valid is True

    # None budget: valid (optional)
    res_none = validator.validate_budget(None)
    assert res_none.valid is True


# =============================================================================
# B. TESTS FOR PERMISSION CHECKER
# =============================================================================
def test_perm_01_read_tools_pending_allowed():
    """PERM-01: search_flights + PENDING -> allowed."""
    checker = PermissionChecker()
    assert checker.status == PermissionStatus.PENDING

    for tool_name in ["search_flights", "get_flight_details", "check_seat_availability", "calculate_price"]:
        res = checker.check(tool_name)
        assert res.allowed is True
        assert res.requires_handoff is False


def test_perm_02_book_flight_pending_blocked():
    """PERM-02: book_flight + PENDING -> blocked -> USER_CONFIRMATION_REQUIRED."""
    checker = PermissionChecker()
    checker.reset()  # ensure PENDING
    res = checker.check("book_flight")
    assert res.allowed is False
    assert res.requires_handoff is True
    assert res.reason == "USER_CONFIRMATION_REQUIRED"


def test_perm_03_book_flight_approved_allowed():
    """PERM-03: book_flight + APPROVED -> allowed."""
    checker = PermissionChecker()
    checker.approve()
    assert checker.status == PermissionStatus.APPROVED

    res = checker.check("book_flight")
    assert res.allowed is True
    assert res.requires_handoff is False
    assert res.reason == "ACTION_APPROVED_BY_USER"


def test_perm_04_book_flight_denied_blocked():
    """PERM-04: book_flight + DENIED -> blocked."""
    checker = PermissionChecker()
    checker.deny()
    assert checker.status == PermissionStatus.DENIED

    res = checker.check("book_flight")
    assert res.allowed is False
    assert res.requires_handoff is True
    assert res.reason == "USER_CONFIRMATION_DENIED"


# =============================================================================
# C. TESTS FOR COMPLETION CHECKER (Computational Sensor)
# =============================================================================
def test_comp_01_valid_confirmed_booking():
    """COMP-01: DB có booking CONFIRMED hợp lệ -> completed = True."""
    db = MockFlightDatabase()
    booking = db.create_booking(
        flight_id="VN210",
        passenger_name="Nguyen Van A",
        passenger_count=1,
        total_price=1800000,
    )
    checker = CompletionChecker(db)
    res = checker.check(
        booking_id=booking["booking_id"],
        expected_flight_id="VN210",
        expected_passenger_count=1,
        max_budget=2000000,
    )
    assert res.completed is True
    assert res.booking_id == booking["booking_id"]
    assert res.reason == "BOOKING_VERIFIED"


def test_comp_02_missing_booking():
    """COMP-02: Không tồn tại booking -> completed = False."""
    db = MockFlightDatabase()
    checker = CompletionChecker(db)
    res = checker.check(booking_id="BK999")
    assert res.completed is False
    assert res.reason == "BOOKING_NOT_FOUND_IN_DB"


def test_comp_03_booking_exceeds_budget():
    """COMP-03: Booking price vượt budget -> completed = False."""
    db = MockFlightDatabase()
    booking = db.create_booking(
        flight_id="VN210",
        passenger_name="Nguyen Van A",
        passenger_count=2,
        total_price=3600000,
    )
    checker = CompletionChecker(db)
    res = checker.check(
        booking_id=booking["booking_id"],
        max_budget=3000000,  # Ngân sách chỉ 3tr trong khi thực tế 3.6tr
    )
    assert res.completed is False
    assert res.reason == "BUDGET_EXCEEDED"


def test_comp_04_computational_sensor_ignores_llm_text():
    """COMP-04: LLM text không được ảnh hưởng đến kết quả completion.

    Chứng minh Computational Sensor: Model nói 'Đã đặt vé thành công' nhưng
    DB không có booking thì completed vẫn phải là False.
    """
    db = MockFlightDatabase()
    # DB hoàn toàn rỗng, chưa hề có booking nào
    assert len(db.list_bookings()) == 0

    checker = CompletionChecker(db)

    # LLM tự huyễn hoặc rằng đã đặt vé xong
    fake_llm_speech = (
        "Tuyệt vời! Tôi đã đặt thành công vé máy bay cho bạn trên chuyến VN210. "
        "Mã vé của bạn là BK001. Chúc bạn có một chuyến đi vui vẻ!"
    )

    res = checker.check(
        booking_id="BK001",
        model_message=fake_llm_speech,
    )
    # Computational Sensor phải bắt được sự dối trá này vì DB chưa hề có BK001
    assert res.completed is False
    assert res.reason == "BOOKING_NOT_FOUND_IN_DB"


# =============================================================================
# D. TESTS FOR HANDOFF MANAGER
# =============================================================================
def test_handoff_format_4_fields():
    """Bàn giao luôn đảm bảo 4 trường chuẩn theo demo và slide bài giảng."""
    handoff = create_handoff(
        stop_reason=StopReasons.NEED_USER_CONFIRMATION,
        da_thu=["search_flights({'origin': 'SGN', 'destination': 'HAN'})", "check_seat_availability({'flight_id': 'VN210'})"],
        trang_thai={"chuyen_chon": "VN210", "tong_tien": 1800000},
        cau_hoi_cho_nguoi="Xác nhận đặt vé chuyến VN210 với tổng tiền 1.800.000đ?",
    )
    assert set(handoff.keys()) == {"stop_reason", "da_thu", "trang_thai", "cau_hoi_cho_nguoi"}
    assert handoff["stop_reason"] == StopReasons.NEED_USER_CONFIRMATION
    assert len(handoff["da_thu"]) == 2

    # In ra dạng chuỗi
    msg = format_handoff_message(handoff)
    assert "DỪNG BẤT THƯỜNG" in msg
    assert "Xác nhận đặt vé" in msg


# =============================================================================
# E. TESTS FOR LOOP DETECTOR
# =============================================================================
def test_loop_detector_repeated_action():
    """Mô phỏng lặp action: search_flights(SGN, HAN) lặp lại lần 2 trong window -> báo lỗi."""
    detector = LoopDetector(window=6, repeat_k=2)

    # Vòng 1: gọi lần đầu -> bình thường
    w1 = detector.check("search_flights", {"origin": "SGN", "destination": "HAN"})
    assert w1 is None

    # Vòng 2: gọi với tham số khác -> bình thường
    w2 = detector.check("search_flights", {"origin": "HAN", "destination": "SGN"})
    assert w2 is None

    # Vòng 3: gọi lại y hệt vòng 1 -> phát hiện lặp
    w3 = detector.check("search_flights", {"origin": "SGN", "destination": "HAN"})
    assert w3 is not None
    assert "LOOP" in w3
    assert "'search_flights' gọi 2 lần với cùng tham số" in w3


def test_loop_detector_repeated_observation():
    """Phát hiện tool trả về cùng observation nhiều lần liên tiếp."""
    detector = LoopDetector(window=6, same_obs_k=3)
    obs = {"error": "not found"}

    detector.check("search_travel_info", {"query": "Vung Tau"}, observation=obs)
    detector.check("search_travel_info", {"query": "Vũng Tàu"}, observation=obs)
    warn = detector.check("search_travel_info", {"query": "Vung Tau City"}, observation=obs)

    assert warn is not None
    assert "LOOP" in warn
    assert "3 lời gọi khác tham số nhưng trả về cùng một kết quả" in warn


# =============================================================================
# F. TESTS FOR BUDGET LIMITER & CORE HARNESS
# =============================================================================
def test_budget_limiter_exceeds_thresholds():
    limiter = BudgetLimiter(max_steps=3, max_tool_calls=4)

    assert limiter.record_step() is None
    assert limiter.record_step() is None
    assert limiter.record_step() is None
    # Bước 4 vượt trần 3
    warn_step = limiter.record_step()
    assert warn_step is not None
    assert "BUDGET_EXCEEDED" in warn_step

    limiter.reset()
    for _ in range(4):
        assert limiter.record_tool_call() is None
    warn_tool = limiter.record_tool_call()
    assert warn_tool is not None
    assert "BUDGET_EXCEEDED" in warn_tool


def test_core_harness_integration():
    """Kiểm tra điều phối tích hợp của CoreHarness."""
    db = MockFlightDatabase()
    harness = CoreHarness(db=db, max_steps=5, max_tool_calls=5)

    # 1. Action READ được phép
    perm = harness.permission_checker.check("search_flights")
    assert perm.allowed is True
    harness.record_action("search_flights", {"origin": "SGN", "destination": "HAN"})

    # 2. Action book_flight bị chặn khi PENDING
    perm_book = harness.permission_checker.check("book_flight")
    assert perm_book.allowed is False
    assert perm_book.requires_handoff is True

    # 3. Tạo handoff package
    handoff = harness.create_handoff_package(
        stop_reason=StopReasons.NEED_USER_CONFIRMATION,
        question="Vui lòng xác nhận phê duyệt đặt vé?",
    )
    assert handoff["stop_reason"] == StopReasons.NEED_USER_CONFIRMATION
    assert len(handoff["da_thu"]) == 1
    assert "search_flights" in handoff["da_thu"][0]
