"""Each scenario has an independent request and deterministic environment hook."""
from dataclasses import dataclass, field

@dataclass
class Scenario:
    id: str
    description: str
    changes: dict = field(default_factory=dict)
    answer: bool | None = True
    event: str | None = None
    expected: str = 'COMPLETED'
    booking_expected: bool = False

SCENARIOS = [
    Scenario('S01','Normal cheapest success', booking_expected=True),
    Scenario('S02','Multiple candidates without policy',{'selection_policy':None},expected='NEED_USER_SELECTION'),
    Scenario('S03','Missing date',{'departure_date':''},expected='NEED_MORE_INFORMATION'),
    Scenario('S04','No flight on requested date',{'departure_date':'2026-10-20'},expected='NO_FLIGHT_FOUND'),
    Scenario('S05','No approval',answer=None,expected='NEED_USER_CONFIRMATION'),
    Scenario('S06','User declines',answer=False,expected='USER_DECLINED'),
    Scenario('S07','Selected flight already sold out',{'destination':'DAD','selected_flight':'VJ624'},expected='SOLD_OUT'),
    Scenario('S08','Seats disappear immediately before booking',event='sold_out',booking_expected=True),
    Scenario('S09','Two passengers total budget',{'passenger_count':2,'max_budget':2_500_000},booking_expected=True),
    Scenario('S10','Budget cannot cover all passengers',{'passenger_count':2,'max_budget':2_000_000},expected='NO_FLIGHT_FOUND'),
]

def apply_event(db, flight_id):
    db.flights[flight_id]['available_seats'] = 0
