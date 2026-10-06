"""One structured plan, one step per graph node; no automatic replanning."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from flight_booking_agent.models import planner

class ExecutionState(TypedDict):
    index: int
    recover: bool

def run(session, mode='offline', adaptive=False):
    plans = []

    def plan_node(state):
        plans.append(planner(session, mode))
        return {'index':0, 'recover':False}

    def execute_node(state):
        action = plans[-1].steps[state['index']].action
        recover = False
        if action == 'select_candidate':
            session.select(session.trace[-1]['observation'])
        elif action == 'request_confirmation':
            session.request_confirmation()
        elif action == 'verify_completion':
            if session.verify():
                session.status = 'COMPLETED'
            else:
                session.stop('FALSE_COMPLETION_BLOCKED', 'Booking không vượt qua kiểm tra DB.')
        else:
            result = session.execute(action, session.arguments(action))
            failure = ((action == 'check_seat_availability' and not result.get('available')) or
                       (action == 'book_flight' and result.get('status') != 'CONFIRMED'))
            if failure:
                reason = result.get('error_code','SOLD_OUT')
                recoverable = reason in ('SOLD_OUT','SEATS_NOT_AVAILABLE','FLIGHT_NOT_FOUND',
                                         'TRANSIENT_ERROR','CONSTRAINT_MISMATCH','QUOTE_CHANGED')
                if adaptive and recoverable and session.replans < 2:
                    session.failed_candidates.add(session.selected)
                    session.approval = None
                    session.quote = None
                    session.replans += 1
                    recover = True
                else:
                    status = 'SOLD_OUT' if session.request.selected_flight and reason == 'SOLD_OUT' else 'PLAN_INVALIDATED'
                    session.stop(status, 'Kế hoạch mất hiệu lực: ' + reason + '. Vui lòng chọn lại.')
            elif result.get('status') == 'blocked':
                session.stop(result['error_code'], 'Hành động bị Harness chặn. Vui lòng kiểm tra yêu cầu.')
        return {'index':state['index']+1, 'recover':recover}

    def route(state):
        if session.status != 'RUNNING':
            return END
        if state['recover']:
            return 'planner'
        return 'executor' if state['index'] < len(plans[-1].steps) else END

    graph = StateGraph(ExecutionState)
    graph.add_node('planner', plan_node)
    graph.add_node('executor', execute_node)
    graph.add_edge(START, 'planner')
    graph.add_edge('planner', 'executor')
    graph.add_conditional_edges('executor', route, ['planner','executor',END])
    graph.compile().invoke({'index':0, 'recover':False}, config={'recursion_limit':50})
