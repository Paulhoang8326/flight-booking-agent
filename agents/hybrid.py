"""Plan + inspect each execution step + bounded conditional replanning."""
from flight_booking_agent.agents.plan_execute import run as execute_graph

def run(session, mode='offline'):
    execute_graph(session, mode=mode, adaptive=True)
