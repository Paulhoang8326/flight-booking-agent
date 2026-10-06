from langchain.agents import create_agent
from flight_booking_agent.models import ScriptedBookingModel, real_model
from flight_booking_agent.middleware import harness_middleware

def run(session, mode='offline'):
    model = ScriptedBookingModel(session=session) if mode == 'offline' else real_model()
    agent = create_agent(model=model, tools=list(session.registry.values()),
        middleware=harness_middleware(session, real=mode=='llm'),
        system_prompt='Find flights under immutable constraints. Use tools sequentially. '
            'Never invent approvals. If book is blocked for confirmation, stop and hand off. '
            'Budget is TOTAL for all passengers. Request: ' + session.request.model_dump_json())
    agent.invoke({'messages':[{'role':'user','content':session.request.model_dump_json()}]},
                 config={'recursion_limit':90})
    if session.status == 'RUNNING':
        if session.booking_id and session.verify():
            session.status = 'COMPLETED'
        else:
            session.stop('NEED_USER_CONFIRMATION', 'Vui lòng chọn chuyến và xác nhận quote để tiếp tục.')
