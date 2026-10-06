"""Scripted BaseChatModel for offline orchestration; optional real OpenAI-compatible model."""
import json
import os
from typing import Any
from pydantic import Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from flight_booking_agent.schemas import Plan, PlanStep

PLAN_ACTIONS = ['search_flights', 'select_candidate', 'get_flight_details',
    'check_seat_availability', 'calculate_price', 'request_confirmation',
    'book_flight', 'verify_completion']

def planner(session, mode='offline'):
    session.model_calls += 1
    if mode == 'offline':
        plan = Plan(steps=[PlanStep(action=a) for a in PLAN_ACTIONS])
    else:
        response = real_model().invoke('Return JSON only with steps [{action: ...}]. '
            'Use exactly these steps in order: ' + ', '.join(PLAN_ACTIONS) +
            '. Request: ' + session.request.model_dump_json())
        plan = Plan.model_validate_json(response.content)
    # Reject omissions/reordering, not executable code or arbitrary tool names.
    if [s.action for s in plan.steps] != PLAN_ACTIONS:
        raise ValueError('UNSAFE_PLAN')
    session.trace.append({'action':'planner', 'arguments':{'replan':session.replans},
        'harness_decision':'VALID_PLAN', 'observation':plan.model_dump()})
    return plan

def real_model():
    from dotenv import load_dotenv
    from pathlib import Path
    from langchain_openai import ChatOpenAI
    load_dotenv(Path(__file__).parent / '.env')
    if not os.getenv('OPENAI_API_KEY'):
        raise ValueError('LLM mode needs OPENAI_API_KEY in project .env')
    return ChatOpenAI(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),
        base_url=os.getenv('OPENAI_BASE_URL') or None, temperature=0, timeout=30, max_retries=1)

class ScriptedBookingModel(BaseChatModel):
    session: Any = Field(exclude=True)

    @property
    def _llm_type(self):
        return 'offline-flight-policy'

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        s = self.session
        s.model_calls += 1
        observations = [json.loads(m.content) for m in messages if m.type == 'tool']
        if s.status != 'RUNNING':
            msg = AIMessage(content=s.status)
        else:
            action = s.phase
            if observations:
                obs = observations[-1]
                if action == 'select_candidate':
                    s.select(obs)
                    s.phase = 'get_flight_details'
                elif action == 'after_seats':
                    if not obs.get('available'):
                        self._recover('SOLD_OUT')
                    else:
                        s.phase = 'calculate_price'
                elif action == 'request_confirmation':
                    s.request_confirmation()
                    s.phase = 'book_flight'
                elif action == 'verify_completion':
                    if obs.get('status') == 'CONFIRMED':
                        s.status = 'COMPLETED' if s.verify() else 'FALSE_COMPLETION_BLOCKED'
                    elif obs.get('error_code') == 'SEATS_NOT_AVAILABLE':
                        self._recover('SEATS_NOT_AVAILABLE')
                    else:
                        s.stop(obs.get('error_code','TOOL_ERROR'), 'Vui lòng kiểm tra lỗi và xác nhận lại.')
            if s.status != 'RUNNING':
                msg = AIMessage(content=s.status)
            else:
                action = s.phase
                transitions = {'search_flights':'select_candidate',
                    'get_flight_details':'check_seat_availability',
                    'check_seat_availability':'after_seats',
                    'calculate_price':'request_confirmation', 'book_flight':'verify_completion'}
                s.phase = transitions[action]
                msg = AIMessage(content='', tool_calls=[{'name':action,
                    'args':s.arguments(action), 'id':f'call_{s.model_calls}', 'type':'tool_call'}])
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _recover(self, reason):
        s = self.session
        s.failed_candidates.add(s.selected)
        s.approval = None
        s.quote = None
        s.trace.append({'action':'adaptive_retry','arguments':{'excluded':s.selected},
            'harness_decision':'RETRY','observation':{'reason':reason}})
        s.phase = 'search_flights'
