"""Record rule exercise evidence; never equate an emitted reference with conformance."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from cobalt import driver
from cobalt.artifacts import corpus


def main():
    original=driver.compile_text; exercised={};current=['unknown']
    def wrapped(*args,**kwargs):
        doc=original(*args,**kwargs)
        for rule in doc['rules']:exercised.setdefault(rule['id'],set()).add(current[0])
        return doc
    class Result(unittest.TextTestResult):
        def startTest(self,test):current[0]=test.id();super().startTest(test)
    with patch.object(driver,'compile_text',wrapped):
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=Result).run(suite)
    if not result.wasSuccessful():raise RuntimeError(f'Coverage run failed: {result.errors} {result.failures}')
    source,formal=corpus();rows=[]
    for ref in sorted(set(source)|set(formal)):
        evidence=sorted(exercised.get(ref,[]))
        rows.append(dict(id=ref,kind='source' if ref in source else 'formal',
            category=source[ref]['primary_category'] if ref in source else ref.split('-')[1],
            location=source[ref]['location'] if ref in source else 'formal rule family',
            implementation_status='partial' if evidence else 'not_implemented',
            test_status='exercised_by_passing_tests' if evidence else 'not_demonstrated',tests=evidence))
    doc=dict(language='CobaltC 1.0.3',compiler='0.1.0',tests_run=result.testsRun,
        interpretation='References observed in passing test compilations are exercise evidence, not proof that every clause of a rule is implemented or asserted. No full conformance claim.',rules=rows)
    (ROOT/'docs'/'coverage.json').write_text(json.dumps(doc,indent=2)+'\n')
    print(f'{result.testsRun} tests passed; {len(exercised)} rule IDs exercised; all {len(rows)} rule IDs accounted for.')

if __name__=='__main__':main()
