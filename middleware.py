"""A single tool gate shared with the explicit graph executor."""
import json
from langchain.agents.middleware import wrap_tool_call, wrap_model_call
from langchain_core.messages import ToolMessage

def harness_middleware(session, real=False):
    @wrap_tool_call
    def gate(request, handler):
        call = request.tool_call
        if real and call['name'] == 'book_flight' and session.status == 'RUNNING':
            # The human callback is outside the model. Only offer a validated quote.
            args = call['args']
            flight = session.db.get_flight(args.get('flight_id',''))
            if session.matches(flight):
                candidates = [f for f in session.db.flights.values() if session.matches(f)
                              and f['available_seats'] >= session.request.passenger_count]
                session.select({'flights':candidates})
                if session.status == 'RUNNING' and session.selected == args.get('flight_id'):
                    session.request_confirmation()
        # Intentionally invoke the validated registry through Harness, not handler.
        result = session.execute(call['name'], call['args'])
        return ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=call['id'])

    @wrap_model_call
    def model_gate(request, handler):
        if real:
            session.model_calls += 1
            if session.model_calls > 25:
                raise ValueError('MODEL_BUDGET_EXCEEDED')
        response = handler(request)
        return response
    return [gate, model_gate]
