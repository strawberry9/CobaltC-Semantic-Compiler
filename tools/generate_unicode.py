"""Generate pinned Unicode 17 tables from official downloaded text files.

Usage: python3 tools/generate_unicode.py DIRECTORY
DIRECTORY contains the eight inputs listed in the generated manifest.
"""
import hashlib
import json
from pathlib import Path
import sys

FILES = {'DerivedCoreProperties.txt': 'ucd', 'Scripts.txt': 'ucd',
         'ScriptExtensions.txt': 'ucd', 'PropertyValueAliases.txt': 'ucd',
         'UnicodeData.txt': 'ucd', 'confusables.txt': 'security',
         'IdentifierStatus.txt': 'security', 'CompositionExclusions.txt': 'ucd'}


def generate(directory):
    root = Path(__file__).resolve().parent.parent / 'cobalt' / 'unicode_data'
    manifest_path = root / 'manifest.json'
    pinned = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = {}
    def rows(name):
        data = (directory / name).read_bytes()
        manifest[name] = {'url': f'https://www.unicode.org/Public/17.0.0/{FILES[name]}/{name}',
                          'sha256': hashlib.sha256(data).hexdigest()}
        if pinned and manifest[name] != pinned.get(name):
            raise ValueError(f'{name}: input differs from the pinned Unicode 17 manifest')
        if name != 'UnicodeData.txt' and '17.0.0' not in data[:3000].decode('utf-8'):
            raise ValueError(f'{name}: expected Unicode 17.0.0')
        for line in data.decode('utf-8').splitlines():
            line = line.split('#')[0].strip()
            if line:
                yield [x.strip() for x in line.split(';')]
    def bounds(raw):
        ends = raw.split('..')
        return [int(ends[0], 16), int(ends[-1], 16)]
    out = {'version': '17.0.0'}
    core = list(rows('DerivedCoreProperties.txt'))
    for prop in ('XID_Start', 'XID_Continue', 'Default_Ignorable_Code_Point'):
        out[prop] = sorted(bounds(r[0]) for r in core if r[1] == prop)
    out['allowed'] = sorted(bounds(r[0]) for r in rows('IdentifierStatus.txt') if r[1] == 'Allowed')
    aliases = {r[2]: r[1] for r in rows('PropertyValueAliases.txt') if r[0] == 'sc'}
    out['scripts'] = sorted([*bounds(r[0]), [aliases[r[1]]]] for r in rows('Scripts.txt'))
    out['extensions'] = sorted([*bounds(r[0]), r[1].split()] for r in rows('ScriptExtensions.txt'))
    out['confusables'] = {str(int(r[0], 16)): [int(c, 16) for c in r[1].split()]
                          for r in rows('confusables.txt')}
    out['decomposition'], out['ccc'], out['bidi'] = {}, {}, {}
    for r in rows('UnicodeData.txt'):
        cp = str(int(r[0], 16))
        if r[5] and not r[5].startswith('<'):
            out['decomposition'][cp] = [int(c, 16) for c in r[5].split()]
        if int(r[3]): out['ccc'][cp] = int(r[3])
        if r[4] != 'L': out['bidi'][cp] = r[4]
    excluded = {int(r[0], 16) for r in rows('CompositionExclusions.txt')}
    out['composition'] = {','.join(map(str, parts)): int(cp)
                          for cp, parts in out['decomposition'].items()
                          if len(parts) == 2 and int(cp) not in excluded
                          and not out['ccc'].get(str(parts[0]), 0)}
    root.mkdir(exist_ok=True)
    (root / '17.0.0.json').write_text(json.dumps(out, sort_keys=True, separators=(',', ':'))+'\n')
    (root / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')


if __name__ == '__main__':
    generate(Path(sys.argv[1]))
