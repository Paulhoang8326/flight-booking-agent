"""Frozen constraints and explicit structured plans; amounts in integer VND."""
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field

class BookingRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', strict=True)
    request_id: str = 'demo-request'
    origin: str = 'SGN'
    destination: str = 'HAN'
    departure_date: str = '2026-10-15'
    passenger_count: int = Field(default=1, ge=1, le=9)
    passenger_name: str = Field(default='Hoang Khoi Nguyen', min_length=1)
    max_budget: int = Field(default=2_000_000, gt=0)
    cabin_class: Literal['ECONOMY', 'BUSINESS'] = 'ECONOMY'
    airline: str | None = None
    selection_policy: Literal['cheapest', 'earliest'] | None = 'cheapest'
    selected_flight: str | None = None

class Flight(BaseModel):
    flight_id: str
    origin: str
    destination: str
    departure_date: str
    cabin_class: str
    base_price: int
    available_seats: int

class Approval(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_fingerprint: str
    flight_id: str
    passenger_count: int
    total_price: int

class Booking(BaseModel):
    booking_id: str
    request_id: str
    flight_id: str
    passenger_count: int
    total_price: int
    status: Literal['CONFIRMED']

class ToolResult(BaseModel):
    status: str
    data: dict[str, Any] = Field(default_factory=dict)

class PlanStep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['search_flights', 'select_candidate', 'get_flight_details',
                    'check_seat_availability', 'calculate_price',
                    'request_confirmation', 'book_flight', 'verify_completion']

class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    steps: list[PlanStep] = Field(min_length=1, max_length=12)
