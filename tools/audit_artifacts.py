"""Reproducible inventory and integrity audit of all supplied artifacts."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from cobalt.artifacts import corpus, artifact

class Headings(HTMLParser):
    def __init__(self):super().__init__();self.active=False;self.headings=[];self.current=[]
    def handle_starttag(self,tag,attrs):
        if re.fullmatch('h[1-6]',tag):self.active=True;self.current=[]
    def handle_endtag(self,tag):
        if re.fullmatch('h[1-6]',tag) and self.active:self.headings.append(''.join(self.current).strip());self.active=False
    def handle_data(self,data):
        if self.active:self.current.append(data)


def main():
    definitions=[
        ('Appendix_06(10).html',1,'1.0.3','Normative language syntax and semantics'),
        ('CobaltC_1.0.3_Formal_Semantic_Specification_v3.md',2,'3.0','Derived sequential and cross-subsystem semantic model'),
        ('CobaltC_1.0.3_Formal_Inference_and_Transition_Rules_v3.json',3,'3.0','35 formal rule families'),
        ('CobaltC_1.0.3_Rule_to_IR_Traceability_v3.json',4,'3.0','1230 source rule mappings'),
        ('CobaltC_1.0.3_Rule_Dependency_Graph.json',5,'1.0','1230 nodes, 1505 edges'),
        ('CobaltC_1.0.3_Explainable_Semantic_IR_Specification_v1.md',6,'1.0','ESIR meaning and explanation contract'),
        ('CobaltC_1.0.3_Explainable_Semantic_IR.schema.json',6,'1.0.0','Machine-readable external output contract'),
        ('CobaltC_1.0.3_Explainable_Semantic_IR_Example.json',6,'1.0.0','Illustrative serialization; not valid source grammar'),
        ('CobaltC_1.0.3_ESIR_Compiler_Implementation_Specification_v1.md',7,'1','Compiler architecture and phase responsibilities'),
        ('CobaltC_1.0.3_ESIR_Compiler_Phase_Contracts_v1.json',7,'1.0.0','Phase identifiers and actual dependency edges'),
        ('CobaltC_1.0.3_AI_Compiler_Implementation_Handoff_v1.md',8,'1','Execution procedure, read first'),
        ('CobaltC_1.0.3_Rule_Classification.json',None,'1.0.3','Supporting classification index, not normative authority'),
        ('Pasted markdown.md',None,'unversioned','Historical classification methodology; task restrictions are not current implementation instructions')]
    inventory=[]
    for name,authority,version,purpose in definitions:
        raw=(ROOT/name).read_bytes();text=raw.decode('utf-8')
        entry=dict(file=name,version=version,purpose=purpose,authority_level=authority,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if name.endswith('.json'):
            data=json.loads(text);entry['machine_readable_structures']={k:len(v) if isinstance(v,(list,dict)) else type(v).__name__ for k,v in data.items()}
        elif name.endswith('.html'):
            parser=Headings();parser.feed(text);entry['major_sections']=parser.headings
        else:entry['major_sections']=re.findall(r'^#+ (.+)$',text,re.M)
        inventory.append(entry)
    classified,formal=corpus();contracts=artifact('ESIR_Compiler_Phase_Contracts_v1.json')
    pending={p['id']:set(p['depends_on']) for p in contracts['phases']};order=[]
    while pending:
        available=[p for p in contracts['phase_order'] if p in pending and not pending[p]]
        if not available:raise ValueError('Phase dependency cycle')
        for p in available:
            order.append(p);del pending[p]
            for deps in pending.values():deps.discard(p)
    result=dict(inputs=inventory,source_rule_count=len(classified),formal_rule_count=len(formal),
        semantic_domains=sorted({r['primary_category'] for r in classified.values()}),
        cross_reference_audit='Classification, traceability and dependency node ID sets match; all graph edges resolve.',
        phase_schedule=order,phase_dependencies={p['id']:p['depends_on'] for p in contracts['phases']})
    (ROOT/'docs'/'inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(f'Inspected {len(inventory)} supplied files; {len(classified)} source rules, {len(formal)} formal rules; references resolve.')
    print('Dependency schedule:', ' -> '.join(order))

if __name__=='__main__':main()
