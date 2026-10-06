# -*- coding: utf-8 -*-
"""SE373 · Flight Booking Agent · Phase 1: Mock Domain & Data.

Mô-đun quản lý Mock Database chuyến bay và đặt chỗ in-memory.
Cung cấp dữ liệu thử nghiệm xác định (deterministic), hỗ trợ reset toàn bộ trạng thái
để phục vụ cho việc kiểm thử và chạy benchmark lặp lại.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


# Danh sách chuyến bay mặc định cố tình bao phủ các kịch bản:
# Case A (Normal): Chuyến bay hợp lệ và còn ghế.
# Case B (Multiple choices): Cùng tuyến/ngày có nhiều lựa chọn khác hãng, giờ, giá.
# Case C (Sold out): Chuyến bay có available_seats == 0.
# Case D (Budget issue): Tuyến HAN -> SGN ngày 2026-10-16 mọi chuyến đều >= 2.200.000đ (vượt budget thấp).
# Case E (Multi-constraint): Chuyến Vietnam Airlines, bay buổi sáng (<12:00), hạng BUSINESS.
INITIAL_FLIGHTS: List[Dict[str, Any]] = [
    # Route: SGN -> HAN (2026-10-15) - Đa dạng lựa chọn (Case A, B, E)
    {
        "flight_id": "VN210",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "06:00",
        "arrival_time": "08:15",
        "cabin_class": "ECONOMY",
        "base_price": 1800000,
        "available_seats": 5,
        "status": "SCHEDULED",
    },
    {
        "flight_id": "VJ120",
        "airline": "Vietjet Air",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "09:30",
        "arrival_time": "11:45",
        "cabin_class": "ECONOMY",
        "base_price": 1200000,
        "available_seats": 12,
        "status": "SCHEDULED",
    },
    {
        "flight_id": "QH202",
        "airline": "Bamboo Airways",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "14:00",
        "arrival_time": "16:15",
        "cabin_class": "ECONOMY",
        "base_price": 1500000,
        "available_seats": 8,
        "status": "SCHEDULED",
    },
    {
        # Case E: Vietnam Airlines + Morning (< 12:00) + BUSINESS
        "flight_id": "VN214",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "10:00",
        "arrival_time": "12:15",
        "cabin_class": "BUSINESS",
        "base_price": 3800000,
        "available_seats": 4,
        "status": "SCHEDULED",
    },

    # Route: SGN -> DAD (2026-10-15) - Có chuyến hết vé (Case C)
    {
        # Case C: Sold out
        "flight_id": "VJ624",
        "airline": "Vietjet Air",
        "origin": "SGN",
        "destination": "DAD",
        "departure_date": "2026-10-15",
        "departure_time": "07:15",
        "arrival_time": "08:35",
        "cabin_class": "ECONOMY",
        "base_price": 950000,
        "available_seats": 0,
        "status": "SCHEDULED",
    },
    {
        "flight_id": "VN130",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "DAD",
        "departure_date": "2026-10-15",
        "departure_time": "08:45",
        "arrival_time": "10:05",
        "cabin_class": "ECONOMY",
        "base_price": 1600000,
        "available_seats": 6,
        "status": "SCHEDULED",
    },
    {
        "flight_id": "QH152",
        "airline": "Bamboo Airways",
        "origin": "SGN",
        "destination": "DAD",
        "departure_date": "2026-10-15",
        "departure_time": "17:30",
        "arrival_time": "18:50",
        "cabin_class": "ECONOMY",
        "base_price": 1350000,
        "available_seats": 7,
        "status": "SCHEDULED",
    },

    # Route: HAN -> SGN (2026-10-16) - Mọi chuyến đều giá cao (Case D: Budget issue)
    {
        "flight_id": "VN221",
        "airline": "Vietnam Airlines",
        "origin": "HAN",
        "destination": "SGN",
        "departure_date": "2026-10-16",
        "departure_time": "07:30",
        "arrival_time": "09:45",
        "cabin_class": "ECONOMY",
        "base_price": 2500000,
        "available_seats": 9,
        "status": "SCHEDULED",
    },
    {
        "flight_id": "QH215",
        "airline": "Bamboo Airways",
        "origin": "HAN",
        "destination": "SGN",
        "departure_date": "2026-10-16",
        "departure_time": "13:00",
        "arrival_time": "15:15",
        "cabin_class": "ECONOMY",
        "base_price": 2200000,
        "available_seats": 3,
        "status": "SCHEDULED",
    },

    # Route: DAD -> SGN (2026-10-16) - Tuyến khứ hồi Đà Nẵng
    {
        "flight_id": "VN131",
        "airline": "Vietnam Airlines",
        "origin": "DAD",
        "destination": "SGN",
        "departure_date": "2026-10-16",
        "departure_time": "09:00",
        "arrival_time": "10:20",
        "cabin_class": "ECONOMY",
        "base_price": 1400000,
        "available_seats": 5,
        "status": "SCHEDULED",
    },
]


class MockFlightDatabase:
    """Cơ sở dữ liệu in-memory lưu trữ chuyến bay và đơn đặt vé."""

    def __init__(self, initial_flights: Optional[List[Dict[str, Any]]] = None) -> None:
        self._initial_template = copy.deepcopy(INITIAL_FLIGHTS if initial_flights is None else initial_flights)
        self.flights: Dict[str, Dict[str, Any]] = {}
        self.bookings: Dict[str, Dict[str, Any]] = {}
        self._booking_counter: int = 0
        self.reset()

    def reset(self) -> None:
        """Khôi phục toàn bộ dữ liệu ban đầu, xóa đơn đặt vé và reset bộ đếm."""
        self.flights = {
            f["flight_id"]: copy.deepcopy(f) for f in self._initial_template
        }
        self.bookings = {}
        self._booking_counter = 0

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        cabin_class: Optional[str] = None,
        airline: Optional[str] = None,
        max_budget: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Tìm kiếm chuyến bay theo các tiêu chí đã chuẩn hóa."""
        res: List[Dict[str, Any]] = []
        for f in self.flights.values():
            if f["origin"].upper() != origin.upper():
                continue
            if f["destination"].upper() != destination.upper():
                continue
            if f["departure_date"] != departure_date:
                continue
            if cabin_class and f["cabin_class"].upper() != cabin_class.upper():
                continue
            if airline and f["airline"].lower() != airline.lower():
                continue
            if max_budget is not None and f["base_price"] > max_budget:
                continue
            res.append(copy.deepcopy(f))
        return res

    def get_flight(self, flight_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết một chuyến bay theo ID."""
        f = self.flights.get(flight_id.upper())
        return copy.deepcopy(f) if f else None

    def get_available_seats(self, flight_id: str) -> Optional[int]:
        """Lấy số ghế còn lại của chuyến bay. Trả về None nếu không tìm thấy."""
        f = self.flights.get(flight_id.upper())
        return f["available_seats"] if f else None

    def create_booking(
        self,
        flight_id: str,
        passenger_name: str,
        passenger_count: int,
        total_price: int,
    ) -> Dict[str, Any]:
        """Tạo đơn đặt chỗ mới và trừ số ghế tương ứng trong DB.

        Ném ValueError nếu chuyến bay không tồn tại hoặc không đủ ghế.
        """
        fid = flight_id.upper()
        if fid not in self.flights:
            raise ValueError(f"Flight ID '{flight_id}' not found.")

        flight = self.flights[fid]
        if passenger_count <= 0:
            raise ValueError("Passenger count must be greater than 0.")

        if flight["available_seats"] < passenger_count:
            raise ValueError(
                f"Not enough seats. Available: {flight['available_seats']}, requested: {passenger_count}."
            )

        # Trừ ghế trong database
        flight["available_seats"] -= passenger_count

        self._booking_counter += 1
        booking_id = f"BK{self._booking_counter:03d}"
        booking_record = {
            "booking_id": booking_id,
            "flight_id": fid,
            "airline": flight["airline"],
            "origin": flight["origin"],
            "destination": flight["destination"],
            "departure_date": flight["departure_date"],
            "departure_time": flight["departure_time"],
            "cabin_class": flight["cabin_class"],
            "passenger_name": passenger_name.strip(),
            "passenger_count": passenger_count,
            "unit_price": flight["base_price"],
            "total_price": total_price,
            "status": "CONFIRMED",
        }
        self.bookings[booking_id] = copy.deepcopy(booking_record)
        return copy.deepcopy(booking_record)

    def get_booking(self, booking_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin đơn đặt chỗ theo mã booking_id."""
        b = self.bookings.get(booking_id.upper())
        return copy.deepcopy(b) if b else None

    def list_bookings(self) -> List[Dict[str, Any]]:
        """Liệt kê toàn bộ các đơn đặt chỗ hiện có."""
        return [copy.deepcopy(b) for b in self.bookings.values()]


# Default singleton instance để dùng chung khi cần
default_db = MockFlightDatabase()
