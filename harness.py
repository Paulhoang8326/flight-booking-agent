# -*- coding: utf-8 -*-
"""SE373 · Flight Booking Agent · Phase 3: Core Harness & Extended Safety Harness.

Kiến trúc Harness bám sát tài liệu bài giảng SE373 (Buổi 03):
- Model chỉ đề xuất hành động / tool call.
- Harness kiểm soát toàn bộ:
  1. DataValidator: Kiểm tra dữ liệu đầu vào bằng code Python thuần túy.
  2. PermissionChecker: Kiểm duyệt hành động nhạy cảm (book_flight) trước khi thực thi.
  3. CompletionChecker: Computational Sensor đọc trực tiếp Mock DB, không tin văn bản LLM.
  4. HandoffManager: Tạo gói bàn giao chuẩn 4 trường cho con người tiếp quản.
  5. LoopDetector: Bắt vòng lặp action/observation và bế tắc (tái hiện từ demo).
  6. BudgetLimiter: Chặn cứng giới hạn số bước và số lượt gọi tool để bảo vệ ngân sách.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

from flight_booking_agent.mock_data import MockFlightDatabase
from flight_booking_agent.schemas import BookingRequest, Approval
import hashlib
import json


# =============================================================================
# 1. DATA VALIDATOR (Ràng buộc dữ liệu bằng code)
# =============================================================================
VALID_AIRPORTS: Set[str] = {"SGN", "HAN", "DAD"}


class BookingHarness:
    """Production path for this mock app. Legacy component APIs below remain for teaching.

    Only execute() is exposed to agents. Approval belongs to the application,
    never to model arguments. All five tool invocations pass through this gate.
    """
    def __init__(self, db, request, confirm=None, before_book=None):
        from flight_booking_agent.tools import create_flight_tools
        self.db, self.request = db, request
        self.registry = {t.name: t for t in create_flight_tools(db)}
        self.confirm = confirm or (lambda quote: None)
        self.before_book = before_book
        self.approval = None
        self.audit_approvals = {}
        self.trace = []
        self.status = 'RUNNING'
        self.handoff = None
        self.selected = None
        self.quote = None
        self.booking_id = None
        self.calls = 0
        self.model_calls = 0
        self.replans = 0
        self.failed_candidates = set()
        self.phase = 'search_flights'
        self.fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()

    def validate_request(self):
        v = DataValidator()
        # Fixed reference makes this dated classroom fixture reproducible.
        checks = [v.validate_route(self.request.origin, self.request.destination),
                  v.validate_date(self.request.departure_date, date(2026, 10, 6)),
                  v.validate_passenger_count(self.request.passenger_count),
                  v.validate_budget(self.request.max_budget)]
        if not all(c.valid for c in checks) or not self.request.passenger_name.strip():
            self.stop('NEED_MORE_INFORMATION', 'Vui lòng cung cấp route, ngày, số khách, tên và ngân sách hợp lệ.')
            return False
        return True

    def stop(self, reason, question):
        self.status = reason
        self.handoff = create_handoff(reason, [e['action'] for e in self.trace],
            {'selected_flight': self.selected, 'quote': self.quote,
             'booking_id': self.booking_id, 'bookings': self.db.list_bookings()}, question)

    def matches(self, f):
        r = self.request
        return bool(f and f['status'] == 'SCHEDULED' and
            all(f[k] == getattr(r, k) for k in ('origin','destination','departure_date','cabin_class')) and
            (not r.airline or f['airline'] == r.airline) and
            (not r.selected_flight or f['flight_id'] == r.selected_flight) and
            f['base_price'] * r.passenger_count <= r.max_budget)

    def approval_matches(self, flight_id, total_price):
        a = self.approval
        return bool(a and a == Approval(request_fingerprint=self.fingerprint,
            flight_id=flight_id, passenger_count=self.request.passenger_count,
            total_price=total_price))

    def execute(self, name, args):
        """Validate the exact schema and immutable constraints before any tool code."""
        self.calls += 1
        decision = 'ALLOW'
        result = None
        r = self.request
        try:
            if self.status != 'RUNNING':
                raise ValueError('SESSION_STOPPED')
            if self.calls > 40:
                raise ValueError('TOOL_BUDGET_EXCEEDED')
            if name not in self.registry:
                raise ValueError('UNKNOWN_TOOL')
            schema = self.registry[name].args_schema
            if set(args) - set(schema.model_fields):
                raise ValueError('UNKNOWN_ARGUMENT')
            schema.model_validate(args, strict=True)
            if name == 'search_flights':
                expected = self.search_args()
                if args != expected:
                    raise ValueError('CONSTRAINT_CHANGED')
            else:
                f = self.db.get_flight(args['flight_id'])
                if not self.matches(f):
                    raise ValueError('CONSTRAINT_MISMATCH')
                if name in ('check_seat_availability','calculate_price','book_flight'):
                    if args.get('passenger_count') != r.passenger_count:
                        raise ValueError('PASSENGER_COUNT_CHANGED')
                if name == 'book_flight':
                    if self.before_book:
                        hook, self.before_book = self.before_book, None
                        hook(self.db, args['flight_id'])
                        f = self.db.get_flight(args['flight_id'])
                    if not self.matches(f):
                        raise ValueError('CONSTRAINT_MISMATCH')
                    total = f['base_price'] * r.passenger_count
                    if args['passenger_name'] != r.passenger_name or args['total_price'] != total:
                        raise ValueError('QUOTE_CHANGED')
                    if not self.approval_matches(args['flight_id'], total):
                        raise PermissionError('USER_CONFIRMATION_REQUIRED')
                    # Idempotency for repeated delivery of the same approved request.
                    existing = [b for b in self.db.list_bookings() if b.get('request_fingerprint') == self.fingerprint]
                    if existing:
                        result = {'status':'CONFIRMED', 'booking_id':existing[0]['booking_id'], 'booking':existing[0]}
            if result is None:
                result = self.registry[name].invoke(args)
            if name == 'search_flights':
                result['flights'] = [f for f in result['flights'] if self.matches(f)]
                result['count'] = len(result['flights'])
            if name == 'book_flight' and result.get('status') == 'CONFIRMED':
                bid = result['booking_id']
                self.db.bookings[bid].update(request_id=r.request_id, request_fingerprint=self.fingerprint)
                self.audit_approvals[bid] = self.approval
                self.booking_id = bid
        except (ValueError, TypeError, KeyError, PermissionError) as exc:
            decision = 'BLOCK'
            result = {'status':'blocked', 'error_code':str(exc)}
        self.trace.append({'action':name, 'arguments':args.copy(),
                           'harness_decision':decision, 'observation':result})
        return result

    def search_args(self):
        r = self.request
        # Raw tool's legacy budget is a unit-price cap; gate converts total budget.
        return dict(origin=r.origin, destination=r.destination, departure_date=r.departure_date,
            cabin_class=r.cabin_class, airline=r.airline, max_budget=r.max_budget // r.passenger_count)

    def select(self, observation):
        flights = [f for f in observation.get('flights', []) if f['flight_id'] not in self.failed_candidates]
        if not flights:
            reason = 'SOLD_OUT' if self.request.selected_flight in self.failed_candidates else 'NO_FLIGHT_FOUND'
            self.stop(reason, 'Không có chuyến phù hợp. Bạn muốn điều chỉnh yêu cầu nào?')
            return
        if self.request.selected_flight:
            flights = [f for f in flights if f['flight_id'] == self.request.selected_flight]
        if len(flights) > 1 and self.request.selection_policy is None:
            self.stop('NEED_USER_SELECTION', 'Bạn chọn mã chuyến nào trong ' + ', '.join(f['flight_id'] for f in flights) + '?')
            return
        key = 'departure_time' if self.request.selection_policy == 'earliest' else 'base_price'
        self.selected = min(flights, key=lambda f: (f[key], f['flight_id']))['flight_id']

    def request_confirmation(self):
        f = self.db.get_flight(self.selected)
        self.quote = {'flight_id':self.selected, 'passenger_count':self.request.passenger_count,
                      'total_price':f['base_price']*self.request.passenger_count,
                      'request_id':self.request.request_id}
        answer = self.confirm(dict(self.quote))
        self.trace.append({'action':'request_confirmation', 'arguments':dict(self.quote),
                           'harness_decision':'USER', 'observation':{'answer':answer}})
        if answer is True:
            self.approval = Approval(request_fingerprint=self.fingerprint,
                flight_id=self.selected, passenger_count=self.request.passenger_count,
                total_price=self.quote['total_price'])
        else:
            self.stop('USER_DECLINED' if answer is False else 'NEED_USER_CONFIRMATION',
                      'Xác nhận đặt vé với đúng chuyến, số khách và tổng tiền trên?')

    def verify(self, booking_id=None):
        bid = booking_id or self.booking_id
        b = self.db.get_booking(bid) if bid else None
        a = self.audit_approvals.get(bid)
        r = self.request
        ok = bool(b and a and b['status'] == 'CONFIRMED' and
            b.get('request_fingerprint') == self.fingerprint and b.get('request_id') == r.request_id and
            b['flight_id'] == self.selected == a.flight_id and
            all(b[k] == getattr(r,k) for k in ('origin','destination','departure_date','cabin_class','passenger_count','passenger_name')) and
            (not r.airline or b['airline'] == r.airline) and
            b['total_price'] == b['unit_price'] * r.passenger_count == a.total_price and
            a.passenger_count == r.passenger_count and a.request_fingerprint == self.fingerprint and
            b['total_price'] <= r.max_budget)
        self.trace.append({'action':'verify_completion', 'arguments':{'booking_id':bid},
                           'harness_decision':'PASS' if ok else 'FAIL', 'observation':{'completed':ok}})
        return ok

    def arguments(self, action):
        if action == 'search_flights':
            return self.search_args()
        args = {'flight_id':self.selected}
        if action in ('calculate_price','check_seat_availability','book_flight'):
            args['passenger_count'] = self.request.passenger_count
        if action == 'book_flight':
            args.update(passenger_name=self.request.passenger_name, total_price=self.quote['total_price'])
        return args


@dataclass
class ValidationResult:
    valid: bool
    error_code: Optional[str] = None
    message: Optional[str] = None


class DataValidator:
    """Kiểm tra tính hợp lệ của các dữ liệu nghiệp vụ bằng code Python."""

    def __init__(self, valid_airports: Optional[Set[str]] = None) -> None:
        self.valid_airports = {a.upper() for a in (valid_airports or VALID_AIRPORTS)}

    def validate_route(self, origin: str, destination: str) -> ValidationResult:
        """Kiểm tra sân bay đi và đến."""
        orig = (origin or "").strip().upper()
        dest = (destination or "").strip().upper()

        if orig not in self.valid_airports:
            return ValidationResult(
                valid=False,
                error_code="INVALID_ORIGIN",
                message=f"Sân bay khởi hành '{origin}' không hợp lệ. Hỗ trợ: {sorted(self.valid_airports)}",
            )
        if dest not in self.valid_airports:
            return ValidationResult(
                valid=False,
                error_code="INVALID_DESTINATION",
                message=f"Sân bay đến '{destination}' không hợp lệ. Hỗ trợ: {sorted(self.valid_airports)}",
            )
        if orig == dest:
            return ValidationResult(
                valid=False,
                error_code="SAME_ORIGIN_DESTINATION",
                message="Sân bay đi và đến không được trùng nhau.",
            )
        return ValidationResult(valid=True)

    def validate_date(
        self,
        date_str: str,
        reference_date: Optional[date] = None,
    ) -> ValidationResult:
        """Kiểm tra định dạng YYYY-MM-DD, tính hợp lệ lịch pháp và không thuộc quá khứ."""
        if not date_str or not isinstance(date_str, str):
            return ValidationResult(
                valid=False,
                error_code="INVALID_DATE_FORMAT",
                message="Ngày bay không được để trống và phải là chuỗi ký tự.",
            )

        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return ValidationResult(
                valid=False,
                error_code="INVALID_DATE_CALENDAR",
                message=f"Ngày '{date_str}' không hợp lệ theo lịch pháp hoặc sai định dạng YYYY-MM-DD.",
            )

        ref = reference_date or date.today()
        if parsed_date < ref:
            return ValidationResult(
                valid=False,
                error_code="PAST_DATE",
                message=f"Ngày bay '{date_str}' không được trong quá khứ so với {ref.isoformat()}.",
            )

        return ValidationResult(valid=True)

    def validate_passenger_count(self, count: int) -> ValidationResult:
        """Kiểm tra số lượng hành khách (1 <= count <= 9)."""
        if type(count) is not int or count < 1:
            return ValidationResult(
                valid=False,
                error_code="INVALID_PASSENGER_COUNT",
                message=f"Số lượng hành khách ({count}) phải lớn hơn hoặc bằng 1.",
            )
        if count > 9:
            return ValidationResult(
                valid=False,
                error_code="EXCEEDS_MAX_PASSENGERS",
                message=f"Số lượng hành khách ({count}) vượt quá giới hạn đặt vé trực tuyến (tối đa 9 khách).",
            )
        return ValidationResult(valid=True)

    def validate_budget(self, budget: Optional[int]) -> ValidationResult:
        """Kiểm tra ngân sách nếu được cung cấp."""
        if budget is not None:
            if not isinstance(budget, (int, float)) or budget <= 0:
                return ValidationResult(
                    valid=False,
                    error_code="INVALID_BUDGET",
                    message=f"Ngân sách ({budget}) phải là số dương lớn hơn 0.",
                )
        return ValidationResult(valid=True)


# =============================================================================
# 2. PERMISSION CHECKER (Kiểm duyệt quyền chạy trước khi thực thi tool)
# =============================================================================
class PermissionStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


# Phân loại thẩm quyền theo slide bài giảng S35, S41
READ_TOOLS: Set[str] = {
    "search_flights",
    "get_flight_details",
    "check_seat_availability",
    "calculate_price",
}
SENSITIVE_WRITE_TOOLS: Set[str] = {
    "book_flight",
}


@dataclass
class PermissionResult:
    allowed: bool
    requires_handoff: bool
    reason: str
    tool_name: str


class PermissionChecker:
    """Kiểm tra quyền hạn của hành động sắp làm.

    Quy tắc:
    - READ tools: luôn được phép chạy.
    - SENSITIVE_WRITE tools (book_flight): chỉ được chạy khi trạng thái là APPROVED.
      Nếu trạng thái là PENDING hoặc DENIED -> chặn và yêu cầu handoff phê duyệt.
    """

    def __init__(self) -> None:
        self.status: str = PermissionStatus.PENDING

    def set_status(self, status: str) -> None:
        if status not in {
            PermissionStatus.PENDING,
            PermissionStatus.APPROVED,
            PermissionStatus.DENIED,
        }:
            raise ValueError(f"Trạng thái permission không hợp lệ: {status}")
        self.status = status

    def approve(self) -> None:
        self.status = PermissionStatus.APPROVED

    def deny(self) -> None:
        self.status = PermissionStatus.DENIED

    def reset(self) -> None:
        self.status = PermissionStatus.PENDING

    def check(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> PermissionResult:
        """Chạy trước khi thực thi tool. Trả về kết quả cho phép hay chặn."""
        if tool_name in READ_TOOLS:
            return PermissionResult(
                allowed=True,
                requires_handoff=False,
                reason="READ_ACTION_ALLOWED",
                tool_name=tool_name,
            )

        if tool_name in SENSITIVE_WRITE_TOOLS:
            if self.status == PermissionStatus.APPROVED:
                return PermissionResult(
                    allowed=True,
                    requires_handoff=False,
                    reason="ACTION_APPROVED_BY_USER",
                    tool_name=tool_name,
                )
            if self.status == PermissionStatus.DENIED:
                return PermissionResult(
                    allowed=False,
                    requires_handoff=True,
                    reason="USER_CONFIRMATION_DENIED",
                    tool_name=tool_name,
                )
            # Mặc định PENDING
            return PermissionResult(
                allowed=False,
                requires_handoff=True,
                reason="USER_CONFIRMATION_REQUIRED",
                tool_name=tool_name,
            )

        # Tool lạ chưa đăng ký
        return PermissionResult(
            allowed=False,
            requires_handoff=True,
            reason="UNKNOWN_TOOL_BLOCKED",
            tool_name=tool_name,
        )


# =============================================================================
# 3. COMPLETION CHECKER (Computational Sensor)
# =============================================================================
@dataclass
class CompletionResult:
    completed: bool
    booking_id: Optional[str]
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class CompletionChecker:
    """Tiêu chí hoàn thành khách quan dựa trên Computational Sensor (S43-S44).

    NGUYÊN TẮC: Hoàn toàn độc lập với câu chữ của model LLM.
    Đọc trực tiếp dữ liệu từ MockFlightDatabase để xác minh tính xác thực.
    """

    def __init__(self, db: MockFlightDatabase) -> None:
        self.db = db

    def check(
        self,
        booking_id: Optional[str],
        expected_flight_id: Optional[str] = None,
        expected_passenger_count: Optional[int] = None,
        max_budget: Optional[int] = None,
        expected_date: Optional[str] = None,
        model_message: Optional[str] = None,  # Cố tình đưa vào để chứng minh LLM text bị bỏ qua
    ) -> CompletionResult:
        """Kiểm chứng tác vụ đặt vé đã hoàn tất đúng chuẩn hay chưa."""
        if not booking_id or not isinstance(booking_id, str):
            return CompletionResult(
                completed=False,
                booking_id=None,
                reason="NO_BOOKING_ID_PROVIDED",
                details={"hint": "Không có booking_id được cung cấp để đối chiếu."},
            )

        booking = self.db.get_booking(booking_id)
        if not booking:
            return CompletionResult(
                completed=False,
                booking_id=booking_id,
                reason="BOOKING_NOT_FOUND_IN_DB",
                details={
                    "hint": f"Mã đặt chỗ {booking_id} không tồn tại trong cơ sở dữ liệu."
                },
            )

        if booking.get("status") != "CONFIRMED":
            return CompletionResult(
                completed=False,
                booking_id=booking_id,
                reason="BOOKING_NOT_CONFIRMED",
                details={"status": booking.get("status")},
            )

        if expected_flight_id and booking.get("flight_id") != expected_flight_id.upper():
            return CompletionResult(
                completed=False,
                booking_id=booking_id,
                reason="FLIGHT_ID_MISMATCH",
                details={
                    "expected": expected_flight_id,
                    "actual": booking.get("flight_id"),
                },
            )

        if (
            expected_passenger_count is not None
            and booking.get("passenger_count") != expected_passenger_count
        ):
            return CompletionResult(
                completed=False,
                booking_id=booking_id,
                reason="PASSENGER_COUNT_MISMATCH",
                details={
                    "expected": expected_passenger_count,
                    "actual": booking.get("passenger_count"),
                },
            )

        if max_budget is not None and booking.get("total_price", 0) > max_budget:
            return CompletionResult(
                completed=False,
                booking_id=booking_id,
                reason="BUDGET_EXCEEDED",
                details={
                    "max_budget": max_budget,
                    "actual_price": booking.get("total_price"),
                },
            )

        if expected_date and booking.get("departure_date") != expected_date:
            return CompletionResult(
                completed=False,
                booking_id=booking_id,
                reason="DEPARTURE_DATE_MISMATCH",
                details={
                    "expected": expected_date,
                    "actual": booking.get("departure_date"),
                },
            )

        return CompletionResult(
            completed=True,
            booking_id=booking_id,
            reason="BOOKING_VERIFIED",
            details=booking,
        )


# =============================================================================
# 4. HANDOFF MANAGER (Gói bàn giao chuẩn 4 trường cho con người)
# =============================================================================
class StopReasons:
    NEED_MORE_INFO = "NEED_MORE_INFO"
    NEED_USER_SELECTION = "NEED_USER_SELECTION"
    NEED_USER_CONFIRMATION = "NEED_USER_CONFIRMATION"
    NO_FLIGHT_FOUND = "NO_FLIGHT_FOUND"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    SOLD_OUT = "SOLD_OUT"
    FAILED_CONSTRAINT = "FAILED_CONSTRAINT"
    FAILED_LOOP = "FAILED_LOOP"
    FAILED_BUDGET = "FAILED_BUDGET"


def create_handoff(
    stop_reason: str,
    da_thu: List[str],
    trang_thai: Dict[str, Any],
    cau_hoi_cho_nguoi: str,
) -> Dict[str, Any]:
    """Tạo gói bàn giao chuẩn 4 trường theo đúng format bài giảng (slide 48, 50)."""
    return {
        "stop_reason": stop_reason,
        "da_thu": list(da_thu),
        "trang_thai": dict(trang_thai),
        "cau_hoi_cho_nguoi": cau_hoi_cho_nguoi,
    }


def format_handoff_message(b: Dict[str, Any]) -> str:
    """Định dạng gói bàn giao thành chuỗi hiển thị trực quan."""
    da_thu_str = " → ".join(b.get("da_thu", [])) if b.get("da_thu") else "(chưa có)"
    return (
        f"DỪNG BẤT THƯỜNG · {b.get('stop_reason')}\n"
        f"  Đã thử          : {da_thu_str}\n"
        f"  Trạng thái      : {b.get('trang_thai')}\n"
        f"  Hỏi người dùng  : {b.get('cau_hoi_cho_nguoi')}"
    )


class HandoffManager:
    """Trình quản lý tạo và định dạng gói bàn giao Human-in-the-loop."""

    @staticmethod
    def create_handoff(
        stop_reason: str,
        da_thu: List[str],
        trang_thai: Dict[str, Any],
        cau_hoi_cho_nguoi: str,
    ) -> Dict[str, Any]:
        return create_handoff(stop_reason, da_thu, trang_thai, cau_hoi_cho_nguoi)

    @staticmethod
    def format_message(b: Dict[str, Any]) -> str:
        return format_handoff_message(b)



# =============================================================================
# 5. LOOP DETECTOR (Kế thừa từ demo giảng viên)
# =============================================================================
class LoopDetector:
    """Bộ phát hiện lặp và bế tắc theo slide S48 và lib/harness.py của giảng viên."""

    def __init__(
        self,
        window: int = 6,
        repeat_k: int = 2,
        same_obs_k: int = 4,
        stall_n: int = 5,
    ) -> None:
        self.recent: deque = deque(maxlen=window)
        self.obs: deque = deque(maxlen=window)
        self.k: int = repeat_k
        self.k_obs: int = same_obs_k
        self.n: int = stall_n
        self.last_progress: Any = None
        self.stall: int = 0

    def check(
        self,
        tool: str,
        args: Dict[str, Any],
        observation: Any = None,
        progress: Any = None,
    ) -> Optional[str]:
        """Trả về chuỗi mô tả lỗi nếu phát hiện lặp hoặc bế tắc, None nếu bình thường."""
        # 1. Trùng action: cùng (tool, args) lặp lại
        fp = (tool, repr(sorted(args.items())))
        count_fp = self.recent.count(fp) + 1
        if count_fp >= self.k:
            return (
                f"LOOP · '{tool}' gọi {count_fp} lần với cùng tham số trong "
                f"{self.recent.maxlen} vòng gần nhất"
            )
        self.recent.append(fp)

        # 2. Trùng observation: tham số khác nhau nhưng kết quả trả về giống hệt
        if observation is not None:
            ofp = repr(observation)
            count_obs = self.obs.count(ofp) + 1
            if count_obs >= self.k_obs:
                return (
                    f"LOOP · {count_obs} lời gọi khác tham số nhưng trả về cùng một kết quả"
                )
            self.obs.append(ofp)

        # 3. Không tiến triển: đại lượng bài toán đứng yên qua n vòng
        if progress is not None:
            self.stall = self.stall + 1 if progress == self.last_progress else 0
            self.last_progress = progress
            if self.stall >= self.n:
                return (
                    f"STALL · tiến triển đứng yên ở {progress!r} qua {self.stall} vòng"
                )

        return None

    def reset(self) -> None:
        """Xóa sạch bộ nhớ vòng lặp."""
        self.recent.clear()
        self.obs.clear()
        self.last_progress = None
        self.stall = 0


# =============================================================================
# 6. BUDGET LIMITER (Giới hạn tài nguyên, số bước & số lượt gọi tool)
# =============================================================================
class BudgetLimiter:
    """Giới hạn cứng số bước suy luận và số lượt gọi tool (slide S38)."""

    def __init__(self, max_steps: int = 8, max_tool_calls: int = 10) -> None:
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.current_steps: int = 0
        self.current_tool_calls: int = 0

    def record_step(self) -> Optional[str]:
        """Ghi nhận thêm 1 bước. Trả về thông báo lỗi nếu chạm trần."""
        self.current_steps += 1
        if self.current_steps > self.max_steps:
            return f"BUDGET_EXCEEDED · Đã vượt quá số bước tối đa ({self.max_steps})"
        return None

    def record_tool_call(self) -> Optional[str]:
        """Ghi nhận thêm 1 lượt gọi tool. Trả về thông báo lỗi nếu chạm trần."""
        self.current_tool_calls += 1
        if self.current_tool_calls > self.max_tool_calls:
            return (
                f"BUDGET_EXCEEDED · Đã vượt quá số lượt gọi tool tối đa ({self.max_tool_calls})"
            )
        return None

    def is_exceeded(self) -> bool:
        return (
            self.current_steps > self.max_steps
            or self.current_tool_calls > self.max_tool_calls
        )

    def reset(self) -> None:
        self.current_steps = 0
        self.current_tool_calls = 0


# =============================================================================
# 7. UNIFIED CORE HARNESS MANAGER
# =============================================================================
class CoreHarness:
    """Lớp điều phối toàn diện Harness cho Flight Booking Agent."""

    def __init__(
        self,
        db: MockFlightDatabase,
        max_steps: int = 8,
        max_tool_calls: int = 10,
    ) -> None:
        self.db = db
        self.validator = DataValidator()
        self.permission_checker = PermissionChecker()
        self.completion_checker = CompletionChecker(db)
        self.loop_detector = LoopDetector(window=6, repeat_k=2)
        self.budget_limiter = BudgetLimiter(
            max_steps=max_steps, max_tool_calls=max_tool_calls
        )
        self.action_history: List[str] = []

    def reset(self) -> None:
        """Reset toàn bộ trạng thái harness."""
        self.permission_checker.reset()
        self.loop_detector.reset()
        self.budget_limiter.reset()
        self.action_history.clear()

    def record_action(self, tool_name: str, args: Dict[str, Any]) -> None:
        """Lưu vết hành động đã thử để phục vụ gói bàn giao handoff."""
        self.action_history.append(f"{tool_name}({args})")

    def create_handoff_package(
        self,
        stop_reason: str,
        question: str,
        extra_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Tạo gói handoff đầy đủ trạng thái hiện tại."""
        state = {
            "so_lan_goi_tool": self.budget_limiter.current_tool_calls,
            "so_buoc": self.budget_limiter.current_steps,
            "permission_status": self.permission_checker.status,
        }
        if extra_state:
            state.update(extra_state)
        return create_handoff(
            stop_reason=stop_reason,
            da_thu=self.action_history,
            trang_thai=state,
            cau_hoi_cho_nguoi=question,
        )
