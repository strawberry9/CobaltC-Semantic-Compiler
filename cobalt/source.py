from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib


class IDs:
    def __init__(self):
        self.counts = defaultdict(int)

    def new(self, namespace):
        self.counts[namespace] += 1
        return f'{namespace}_{self.counts[namespace]}'


@dataclass
class Source:
    path: str
    text: str
    id: str = 'file_1'
    starts: list = field(init=False)

    def __post_init__(self):
        self.starts = [0]
        for i, c in enumerate(self.text):
            if c == '\n' or (c == '\r' and self.text[i:i+2] != '\r\n'):
                self.starts.append(i + 1)

    def span(self, start, end):
        a, b = bisect_right(self.starts, start), bisect_right(self.starts, end)
        return dict(file=self.path, start_line=a, start_col=start-self.starts[a-1]+1,
                    end_line=b, end_col=end-self.starts[b-1]+1)

    @property
    def hash(self):
        return hashlib.sha256(self.text.encode('utf-8')).hexdigest()


class Diagnostics:
    def __init__(self, ids):
        self.ids, self.items = ids, []

    def add(self, code, message, span, phase, rules=(), entities=()):
        d = dict(id=self.ids.new('diag'), severity='error', code=code,
                 message=message, source_span=span, phase=phase,
                 rule_refs=list(rules), related_entities=list(entities), notes=[])
        self.items.append(d)
        return d


class StopCompilation(Exception):
    """A diagnosed syntax/implementation boundary; never a successful node."""
