import pytest
from pydantic import ValidationError
from flight_booking_agent.harness import BookingHarness
from flight_booking_agent.mock_data import MockFlightDatabase
from flight_booking_agent.schemas import BookingRequest

def session(**changes):
    s = BookingHarness(MockFlightDatabase(),BookingRequest(**changes),confirm=lambda q:True)
    s.selected='VJ120'
    return s

def test_no_approval_blocks_write():
    s = session()
    s.quote={'total_price':1_200_000}
    result=s.execute('book_flight',s.arguments('book_flight'))
    assert result['error_code']=='USER_CONFIRMATION_REQUIRED'
    assert not s.db.bookings

def test_approval_not_reusable_for_other_flight():
    s=session(); s.request_confirmation()
    s.selected='QH202'; s.quote={'total_price':1_500_000}
    result=s.execute('book_flight',s.arguments('book_flight'))
    assert result['error_code']=='USER_CONFIRMATION_REQUIRED'
    assert not s.db.bookings

def test_changed_price_requires_new_approval():
    s=session(); s.request_confirmation()
    s.db.flights['VJ120']['base_price']=1_300_000
    args=s.arguments('book_flight'); args['total_price']=1_300_000
    assert s.execute('book_flight',args)['error_code']=='USER_CONFIRMATION_REQUIRED'
    assert not s.db.bookings

def test_changed_passengers_and_request_blocked():
    s=session(); s.request_confirmation()
    args=s.arguments('book_flight'); args['passenger_count']=2
    assert s.execute('book_flight',args)['error_code']=='PASSENGER_COUNT_CHANGED'
    other=session(request_id='other-request')
    other.approval=s.approval; other.quote=s.quote
    assert other.execute('book_flight',other.arguments('book_flight'))['status']=='blocked'

@pytest.mark.parametrize('field,value',[('departure_date','2026-10-16'),('origin','HAN'),('max_budget',9_999_999)])
def test_agent_cannot_change_search_constraint(field,value):
    s=session(); args=s.search_args(); args[field]=value
    assert s.execute('search_flights',args)['error_code']=='CONSTRAINT_CHANGED'

def test_frozen_request():
    s=session()
    with pytest.raises(ValidationError): s.request.max_budget=99_999_999

def test_false_completion_and_tampered_booking():
    s=session(); assert not s.verify('BK001')
    s.request_confirmation(); s.execute('book_flight',s.arguments('book_flight'))
    assert s.verify()
    s.db.bookings[s.booking_id]['request_id']='wrong'
    assert not s.verify()

def test_missing_approval_audit_fails_completion():
    s=session(); s.request_confirmation(); s.execute('book_flight',s.arguments('book_flight'))
    s.audit_approvals.clear()
    assert not s.verify()

def test_idempotent_repeated_delivery():
    s=session(); s.request_confirmation()
    args=s.arguments('book_flight')
    first=s.execute('book_flight',args)
    second=s.execute('book_flight',args)
    assert first['booking_id']==second['booking_id']
    assert len(s.db.bookings)==1
    assert s.db.flights['VJ120']['available_seats']==11

def test_sold_out_not_mutated():
    s=session(); s.request_confirmation(); s.db.flights['VJ120']['available_seats']=0
    assert s.execute('book_flight',s.arguments('book_flight'))['error_code']=='SEATS_NOT_AVAILABLE'
    assert not s.db.bookings

def test_unknown_tool_and_unknown_argument():
    s=session()
    assert s.execute('pay',{})['status']=='blocked'
    args=s.search_args(); args['approval']=True
    assert s.execute('search_flights',args)['error_code']=='UNKNOWN_ARGUMENT'

def test_total_budget_search_filters_all_passengers():
    s=session(passenger_count=2,max_budget=2_500_000)
    result=s.execute('search_flights',s.search_args())
    assert [f['flight_id'] for f in result['flights']]==['VJ120']

def test_boolean_tool_passenger_argument_blocked():
    s=session()
    assert s.execute('calculate_price',{'flight_id':'VJ120','passenger_count':True})['status']=='blocked'

def test_empty_database_stays_empty():
    assert MockFlightDatabase([]).flights == {}

def test_route_changes_before_booking_are_blocked():
    s=session(); s.request_confirmation()
    def change_route(db,fid): db.flights[fid]['destination']='DAD'
    s.before_book=change_route
    assert s.execute('book_flight',s.arguments('book_flight'))['error_code']=='CONSTRAINT_MISMATCH'
    assert not s.db.bookings
