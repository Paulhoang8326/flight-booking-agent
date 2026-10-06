"""Application entry point, human decisions are callbacks owned by CLI/benchmark."""
import time
from pydantic import ValidationError
from flight_booking_agent.schemas import BookingRequest
from flight_booking_agent.harness import BookingHarness, create_handoff
from flight_booking_agent.mock_data import MockFlightDatabase
from flight_booking_agent.scenarios import apply_event
from flight_booking_agent.agents import react, plan_execute, hybrid

ARCHITECTURES = {'react':react, 'plan_execute':plan_execute, 'hybrid':hybrid}

def run_scenario(architecture, scenario, mode='offline', confirm=None):
    start = time.perf_counter()
    data = BookingRequest().model_dump()
    data.update(scenario.changes, request_id=scenario.id)
    try:
        request = BookingRequest(**data)
    except ValidationError as exc:
        return {'architecture':architecture,'scenario':scenario.id,'status':'NEED_MORE_INFORMATION',
            'request':data, 'trace':[], 'bookings':[], 'booking_id':None,
            'handoff':create_handoff('NEED_MORE_INFORMATION',[],{},str(exc)),
            'metrics':{'tool_calls':0,'model_calls':0,'replans':0,'elapsed_ms':(time.perf_counter()-start)*1000}}
    session = BookingHarness(MockFlightDatabase(), request,
        confirm=confirm or (lambda quote: scenario.answer),
        before_book=apply_event if scenario.event == 'sold_out' else None)
    if session.validate_request():
        try:
            ARCHITECTURES[architecture].run(session, mode)
        except Exception as exc:
            session.stop('EXECUTION_ERROR', str(exc))
    return {'architecture':architecture,'scenario':scenario.id,'mode':mode,
        'request':request.model_dump(), 'status':session.status, 'booking_id':session.booking_id,
        'bookings':session.db.list_bookings(), 'trace':session.trace,'handoff':session.handoff,
        'metrics':{'tool_calls':session.calls,'model_calls':session.model_calls,
                   'replans':session.replans,'elapsed_ms':(time.perf_counter()-start)*1000}}
