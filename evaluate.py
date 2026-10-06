"""Measured offline benchmark. Task success includes expected safe handoffs."""
if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from flight_booking_agent.runner import run_scenario, ARCHITECTURES
from flight_booking_agent.scenarios import SCENARIOS

def score(result, scenario):
    r = result['request']
    bookings = result['bookings']
    completed = result['status'] == 'COMPLETED'
    violations = sum(not (all(b[k] == r[k] for k in
        ('origin','destination','departure_date','cabin_class','passenger_count','passenger_name')) and
        b.get('request_id') == r['request_id'] and b['total_price'] <= r['max_budget'] and
        b['total_price'] == b['unit_price'] * r['passenger_count']) for b in bookings)
    confirmations = [e['arguments'] for e in result['trace'] if e['action']=='request_confirmation' and e['observation'].get('answer') is True]
    permission = sum(not any(q['flight_id']==b['flight_id'] and q['total_price']==b['total_price'] and
        q['passenger_count']==b['passenger_count'] and q['request_id']==b.get('request_id') for q in confirmations) for b in bookings)
    false = int(completed and (not bookings or violations > 0 or permission > 0 or
        not any(e['action']=='verify_completion' and e['observation']['completed'] for e in result['trace'])))
    expected = scenario.expected
    # S08 task objective is a successful booking for ALL architectures.
    # PTE safe invalidation is separately credited as correct handoff, not task success.
    handoff_expected = expected != 'COMPLETED' or (scenario.id=='S08' and result['architecture']=='plan_execute')
    handoff_ok = result['status']==expected if expected != 'COMPLETED' else result['status']=='PLAN_INVALIDATED'
    return {'task_success':int(result['status']==expected and not violations and not permission and not false),
        'booking_success':int(completed and bool(bookings) and not violations and not permission and not false),
        'constraint_violations':violations,'permission_violations':permission,'false_completion':false,
        'handoff_count':int(result['handoff'] is not None),
        'handoff_correct':int(handoff_expected and handoff_ok and not bookings)}

def evaluate(repeats=1):
    results = []
    for _ in range(repeats):
        for arch in ARCHITECTURES:
            for scenario in SCENARIOS:
                result = run_scenario(arch,scenario)
                result['scores'] = score(result,scenario)
                results.append(result)
    summary = []
    for arch in ARCHITECTURES:
        rows = [r for r in results if r['architecture']==arch]
        eligible = [r for r in rows if next(s for s in SCENARIOS if s.id==r['scenario']).booking_expected]
        summary.append({'architecture':arch,'runs':len(rows),
            'task_success_rate':mean(r['scores']['task_success'] for r in rows),
            'booking_success_rate':mean(r['scores']['booking_success'] for r in eligible),
            'constraint_violation_rate':mean(bool(r['scores']['constraint_violations']) for r in rows),
            'permission_violation_rate':mean(bool(r['scores']['permission_violations']) for r in rows),
            'false_completion_rate':mean(r['scores']['false_completion'] for r in rows),
            'avg_tool_calls':mean(r['metrics']['tool_calls'] for r in rows),
            'avg_model_calls':mean(r['metrics']['model_calls'] for r in rows),
            'handoff_count':sum(r['scores']['handoff_count'] for r in rows),
            'handoff_correct':sum(r['scores']['handoff_correct'] for r in rows),
            'avg_elapsed_ms':mean(r['metrics']['elapsed_ms'] for r in rows),'token_usage':None})
    out = Path(__file__).parent/'results'
    out.mkdir(exist_ok=True)
    (out/'evaluation.json').write_text(json.dumps({'mode':'offline-scripted','repeats':repeats,
        'summary':summary,'runs':results},ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'summary.csv').open('w',newline='',encoding='utf-8') as f:
        writer = csv.DictWriter(f,fieldnames=list(summary[0]))
        writer.writeheader(); writer.writerows(summary)
    print(json.dumps(summary,indent=2))
    return summary

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--repeats',type=int,default=1)
    args = p.parse_args()
    if args.repeats < 1: p.error('repeats must be positive')
    evaluate(args.repeats)
