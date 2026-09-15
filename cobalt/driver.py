from .source import Source, IDs, Diagnostics, StopCompilation
from .lexer import lex
from .syntax import Parser, normalize
from .semantic import Lowerer
from .dataflow import Analyzer
from .esir import build, validate


def compile_text(text,path='input.cb'):
    ids=IDs();d=Diagnostics(ids);source=Source(path,text);ast=graph=None
    try:
        # Reject surrogates everywhere, including comments, before hashing or lexing.
        for i,c in enumerate(text):
            if 0xD800<=ord(c)<=0xDFFF:
                d.add('invalid_scalar','Source must contain Unicode scalar values.',source.span(i,i+1),'P0')
                source=Source(path,'');raise StopCompilation()
        tokens=lex(source,ids,d)
        ast=normalize(Parser(tokens,ids,d).parse())
        graph=Lowerer(ast,ids,d).lower()
        Analyzer(graph).run()
    except StopCompilation:pass
    except RecursionError:
        d.add('unsupported_nesting_depth','Source nesting exceeds this implementation’s recursion limit.',source.span(0,0),'P2')
        graph=None
    doc=build(source,ids,d,ast,graph)
    validate(doc)
    return doc


def compile_bytes(data,path='input.cb'):
    try:text=data.decode('utf-8',errors='strict')
    except UnicodeDecodeError as error:
        import hashlib
        ids=IDs();d=Diagnostics(ids);source=Source(path,'')
        d.add('invalid_utf8',f'Malformed UTF-8 at byte offset {error.start}; bytes were not replaced.',source.span(0,0),'P0')
        doc=build(source,ids,d)
        digest=hashlib.sha256(data).hexdigest()
        doc['source_files'][0]['hash']=digest;doc['compilation']['source_hashes'][path]=digest
        validate(doc);return doc
    return compile_text(text,path)
