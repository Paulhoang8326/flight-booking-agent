"""Capture direct negative Harness evidence for the report."""
import json
from pathlib import Path
if __package__ in (None, ''):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from flight_booking_agent.harness import BookingHarness
from flight_booking_agent.mock_data import MockFlightDatabase
from flight_booking_agent.schemas import BookingRequest

def capture():
    s=BookingHarness(MockFlightDatabase(),BookingRequest())
    s.selected='VJ120'; s.quote={'total_price':1_200_000}
    blocked=s.execute('book_flight',s.arguments('book_flight'))
    completion=s.verify('BK001')
    evidence={'request':s.request.model_dump(),'attempt':s.trace[0],
              'bookings':s.db.list_bookings(),'false_completion_claim':'Da dat ve BK001',
              'completion_by_code':completion,'trace':s.trace}
    assert blocked['status']=='blocked' and not evidence['bookings'] and not completion
    (Path(__file__).parent/'results'/'safety_demo.json').write_text(
        json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': capture()
