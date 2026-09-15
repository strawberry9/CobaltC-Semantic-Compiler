import argparse
from pathlib import Path
import sys
from .driver import compile_bytes
from .esir import dumps


def main():
    parser=argparse.ArgumentParser(description='CobaltC 1.0.3 scalar milestone: source to validated ESIR (no backend).')
    parser.add_argument('source',type=Path)
    parser.add_argument('-o','--output',type=Path)
    args=parser.parse_args()
    try:
        output=args.output or args.source.with_suffix('.esir.json')
        if output.resolve()==args.source.resolve():parser.error('Output must differ from the source file.')
        doc=compile_bytes(args.source.read_bytes(),args.source.as_posix())
        output.write_text(dumps(doc),encoding='utf-8')
    except (OSError,ValueError) as error:
        print(f'cobalt: {error}',file=sys.stderr);return 2
    for d in doc['diagnostics']:
        s=d['source_span'];print(f'{s["file"]}:{s["start_line"]}:{s["start_col"]}: {d["code"]}: {d["message"]}',file=sys.stderr)
    return {'valid':0,'invalid':1,'incomplete':2}[doc['compilation']['result']]

if __name__=='__main__':sys.exit(main())
