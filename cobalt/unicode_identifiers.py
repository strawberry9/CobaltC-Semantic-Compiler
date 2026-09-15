"""Appendix B: Unicode 17 classification and UTS #39 identifier security.

Identifier identity is never normalized. NFD is used only for security skeletons.
No Unicode property is taken from the Python host.
"""
from bisect import bisect_right
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def data():
    return json.loads((Path(__file__).parent / 'unicode_data/17.0.0.json').read_text())


@lru_cache(maxsize=None)
def starts(key):
    return [r[0] for r in data()[key]]


def property_at(key, cp, default=None):
    i = bisect_right(starts(key), cp) - 1
    if i >= 0:
        row = data()[key][i]
        if cp <= row[1]: return row[2] if len(row) > 2 else True
    return default


def identifier_start(c):
    return c == '_' or bool(property_at('XID_Start', ord(c)))


def identifier_continue(c):
    return c == '_' or bool(property_at('XID_Continue', ord(c)))


def moderately_restrictive(name):
    # UTS #39 3.1 tests profile membership under canonical equivalence.
    # Compose first (e.g. Japanese voiced kana), then decompose a restricted
    # composite if its equivalent constituent characters are allowed.
    def allowed(cp):
        if property_at('allowed', cp): return True
        parts = nfd([cp])
        return parts != [cp] and all(property_at('allowed', p) for p in parts)
    if not all(allowed(cp) for cp in nfc([ord(c) for c in name])): return False
    if name.isascii(): return True
    sets = []
    for c in name:
        scripts = set(property_at('extensions', ord(c),
                                 property_at('scripts', ord(c), ['Zzzz'])))
        if scripts & {'Zyyy', 'Zinh'}: continue
        if 'Hani' in scripts: scripts.update(('Jpan', 'Kore', 'Hanb'))
        if scripts & {'Hira', 'Kana'}: scripts.add('Jpan')
        if 'Hang' in scripts: scripts.add('Kore')
        if 'Bopo' in scripts: scripts.add('Hanb')
        sets.append(scripts)
    if not sets or set.intersection(*sets): return True
    recommended = set('Arab Armn Beng Deva Ethi Geor Gujr Guru Hang Hani Hebr Hira Kana Knda Khmr Laoo Mlym Mymr Orya Sinh Taml Telu Thaa Thai Tibt Jpan Kore Hanb'.split())
    return any(all(s & {'Latn', other} for s in sets) for other in recommended)


def nfd(points):
    decomposed = []
    def expand(cp):
        if 0xAC00 <= cp <= 0xD7A3:
            s = cp - 0xAC00
            decomposed.extend((0x1100 + s // 588, 0x1161 + s % 588 // 28))
            if s % 28: decomposed.append(0x11A7 + s % 28)
        elif str(cp) in data()['decomposition']:
            for part in data()['decomposition'][str(cp)]: expand(part)
        else: decomposed.append(cp)
    for cp in points: expand(cp)
    # Stable canonical ordering, without crossing a starter.
    for i in range(1, len(decomposed)):
        cls = data()['ccc'].get(str(decomposed[i]), 0)
        j = i
        while cls and j and data()['ccc'].get(str(decomposed[j-1]), 0) > cls:
            decomposed[j-1], decomposed[j] = decomposed[j], decomposed[j-1]
            j -= 1
    return decomposed


def nfc(points):
    points = nfd(points)
    if not points: return []
    out = [points[0]]; starter = 0; previous_class = data()['ccc'].get(str(points[0]), 0)
    for cp in points[1:]:
        cls = data()['ccc'].get(str(cp), 0)
        first = out[starter]
        composite = data()['composition'].get(f'{first},{cp}')
        if 0x1100 <= first < 0x1113 and 0x1161 <= cp < 0x1176:
            composite = 0xAC00 + (first-0x1100)*588 + (cp-0x1161)*28
        elif 0xAC00 <= first <= 0xD7A3 and (first-0xAC00) % 28 == 0 and 0x11A8 <= cp < 0x11C3:
            composite = first + cp-0x11A7
        if composite is not None and (previous_class == 0 or previous_class < cls):
            out[starter] = composite
        else:
            if cls == 0: starter = len(out)
            out.append(cp); previous_class = cls
    return out


def identifier_display_order(points):
    """LTR UAX #9 for profile-allowed identifier characters (no bidi controls).

    Allowed identifiers contain L/R/AL, EN/AN, NSM, and ON only. Thus explicit
    embeddings, isolates, brackets and mirrored characters cannot occur here.
    """
    original = [data()['bidi'].get(str(cp), 'L') for cp in points]
    if not any(t in ('R', 'AL') for t in original): return points
    kinds = list(original)
    previous = 'L'
    for i, kind in enumerate(kinds):  # W1
        if kind == 'NSM': kinds[i] = previous
        previous = kinds[i]
    strong = 'L'
    for i, kind in enumerate(kinds):  # W2, W3
        if kind == 'EN' and strong == 'AL': kinds[i] = 'AN'
        if kind in ('R', 'L', 'AL'): strong = kind
        if kind == 'AL': kinds[i] = 'R'
    strong = 'L'
    for i, kind in enumerate(kinds):  # W7
        if kind in ('R', 'L'): strong = kind
        elif kind == 'EN' and strong == 'L': kinds[i] = 'L'
    for i, kind in enumerate(kinds):  # N1, N2
        if kind != 'ON': continue
        left = next((k for k in reversed(kinds[:i]) if k != 'ON'), 'L')
        right = next((k for k in kinds[i+1:] if k != 'ON'), 'L')
        left = 'R' if left in ('EN', 'AN') else left
        right = 'R' if right in ('EN', 'AN') else right
        kinds[i] = left if left == right else 'L'
    levels = [1 if k == 'R' else 2 if k in ('EN', 'AN') else 0 for k in kinds]
    # L3: keep each original combining-mark sequence with its base during L2.
    groups = []
    for cp, kind, level in zip(points, original, levels):
        if kind == 'NSM' and groups: groups[-1][0].append(cp)
        else: groups.append(([cp], level))
    for level in (2, 1):
        i = 0
        while i < len(groups):
            if groups[i][1] < level:
                i += 1; continue
            end = i + 1
            while end < len(groups) and groups[end][1] >= level: end += 1
            groups[i:end] = reversed(groups[i:end]); i = end
    return [cp for group, _ in groups for cp in group]


@lru_cache(maxsize=4096)
def skeleton(name):
    points = nfd(identifier_display_order([ord(c) for c in name]))
    mapped = []
    for cp in points:
        if not property_at('Default_Ignorable_Code_Point', cp):
            mapped.extend(data()['confusables'].get(str(cp), [cp]))
    return ''.join(chr(cp) for cp in nfd(mapped))
