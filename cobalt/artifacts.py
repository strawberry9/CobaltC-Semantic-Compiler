"""Read-only access to the supplied, versioned implementation inputs."""
import json
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parent.parent

@lru_cache(maxsize=None)
def artifact(suffix):
    matches=list(ROOT.glob(f'CobaltC_1.0.3_{suffix}'))
    if len(matches)!=1:raise RuntimeError(f'Expected exactly one supplied artifact: {suffix}')
    return json.loads(matches[0].read_text(encoding='utf-8'))


def corpus():
    classified={r['id']:r for r in artifact('Rule_Classification.json')['rules']}
    formal={r[0]:r for r in artifact('Formal_Inference_and_Transition_Rules_v3.json')['formal_rules']}
    trace={r['rule_id']:r for r in artifact('Rule_to_IR_Traceability_v3.json')['records']}
    graph=artifact('Rule_Dependency_Graph.json')
    if set(classified)!=set(trace) or set(classified)!={n['id'] for n in graph['nodes']}:
        raise ValueError('Rule corpus ID sets disagree')
    if not all(e['from'] in classified and e['to'] in classified for e in graph['edges']):
        raise ValueError('Dangling dependency')
    return classified,formal
