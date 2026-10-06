import pytest
from flight_booking_agent.runner import run_scenario
from flight_booking_agent.scenarios import SCENARIOS
from flight_booking_agent.evaluate import score

@pytest.mark.parametrize('architecture',['react','plan_execute','hybrid'])
@pytest.mark.parametrize('scenario',SCENARIOS,ids=lambda s:s.id)
def test_architecture_scenario(architecture,scenario):
    result = run_scenario(architecture,scenario)
    expected = 'PLAN_INVALIDATED' if scenario.id=='S08' and architecture=='plan_execute' else scenario.expected
    assert result['status'] == expected, result.get('handoff')
    assert len(result['bookings']) == (1 if expected=='COMPLETED' else 0)
    metrics = score(result,scenario)
    assert metrics['constraint_violations'] == metrics['permission_violations'] == metrics['false_completion'] == 0
    if scenario.id=='S01':
        assert result['bookings'][0]['flight_id']=='VJ120'
    if scenario.id=='S09':
        assert result['bookings'][0]['total_price']==2_400_000
    if scenario.id=='S08' and architecture!='plan_execute':
        assert result['bookings'][0]['flight_id']=='QH202'
        approvals = [e for e in result['trace'] if e['action']=='request_confirmation']
        assert [e['arguments']['flight_id'] for e in approvals]==['VJ120','QH202']
        if architecture=='hybrid':
            assert result['metrics']['replans']==1
            assert sum(e['action']=='planner' for e in result['trace'])==2

def test_invalid_schema_stops_without_mutation():
    from flight_booking_agent.scenarios import Scenario
    result = run_scenario('react',Scenario('invalid','invalid',{'passenger_count':True}))
    assert result['status']=='NEED_MORE_INFORMATION'
    assert result['bookings']==[]

def test_hybrid_price_change_replans_and_gets_fresh_confirmation():
    from flight_booking_agent.harness import BookingHarness
    from flight_booking_agent.mock_data import MockFlightDatabase
    from flight_booking_agent.schemas import BookingRequest
    from flight_booking_agent.agents.hybrid import run
    def change_price(db,fid): db.flights[fid]['base_price']=1_400_000
    s=BookingHarness(MockFlightDatabase(),BookingRequest(),confirm=lambda q:True,before_book=change_price)
    run(s)
    assert s.status=='COMPLETED' and s.replans==1
    assert s.approval.flight_id=='QH202'
    assert s.verify()

def test_hybrid_transient_error_replans(monkeypatch):
    from flight_booking_agent.harness import BookingHarness
    from flight_booking_agent.mock_data import MockFlightDatabase
    from flight_booking_agent.schemas import BookingRequest
    from flight_booking_agent.agents.hybrid import run
    s=BookingHarness(MockFlightDatabase(),BookingRequest(),confirm=lambda q:True)
    original=s.execute
    fired=False
    def execute(name,args):
        nonlocal fired
        if name=='check_seat_availability' and not fired:
            fired=True
            return {'status':'error','error_code':'TRANSIENT_ERROR'}
        return original(name,args)
    monkeypatch.setattr(s,'execute',execute)
    run(s)
    assert s.status=='COMPLETED' and s.replans==1
