"""Run from project folder or python -m flight_booking_agent.main from parent."""
if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import argparse
import json
from pathlib import Path
from flight_booking_agent.scenarios import SCENARIOS
from flight_booking_agent.runner import run_scenario

def main():
    parser = argparse.ArgumentParser(description='Mock flight booking demonstration')
    parser.add_argument('--agent',choices=['react','plan_execute','hybrid'],default='react')
    parser.add_argument('--scenario',choices=[s.id for s in SCENARIOS],default='S01')
    parser.add_argument('--mode',choices=['offline','llm'],default='offline')
    parser.add_argument('--auto-approve',action='store_true',help='SIMULATED user for class demo only')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    scenario = next(s for s in SCENARIOS if s.id == args.scenario)
    def confirm(quote):
        print('CONFIRMATION:', json.dumps(quote,ensure_ascii=False))
        answer = input('Approve this exact booking? [y/n/Enter=pending]: ').strip().lower()
        return True if answer == 'y' else False if answer == 'n' else None
    # Negative permission scenarios retain their prescribed answers.
    callback = None if args.auto_approve or scenario.answer is not True else confirm
    result = run_scenario(args.agent, scenario, args.mode, callback)
    output = json.dumps(result,ensure_ascii=False,indent=2)
    print(output)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(output,encoding='utf-8')
    if result['status'] == 'EXECUTION_ERROR':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
