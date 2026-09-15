"""Sections 3–7 and Appendix B, using pinned Unicode 17 tables."""
from dataclasses import dataclass
import re
from .source import StopCompilation
from .unicode_identifiers import identifier_start, identifier_continue, moderately_restrictive

KEYWORDS = set('alias as break const continue defer else enum export extern fn for foreach if import in loop match module move mut return struct unsafe while'.split())
TYPES = set('bool char void i8 i16 i32 i64 i128 u8 u16 u32 u64 u128 isize usize f32 f64'.split())
LITERALS = {'true', 'false', 'null'}
OPS = sorted('... .. :: -> => << >> <= >= == != && || += -= *= /= %= &= |= ^= <<= >>= + - * / % & | ^ ! = < > ? : ; , . ( ) [ ] { }'.split(), key=lambda s: (-len(s), s))
INT = re.compile(r'(?:[0-9](?:_?[0-9])*|0x[0-9a-fA-F](?:_?[0-9a-fA-F])*|0b[01](?:_?[01])*|0o[0-7](?:_?[0-7])*)\Z')
FLOAT = re.compile(r'[0-9]+(?:\.[0-9]*(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)\Z')


@dataclass(frozen=True)
class Token:
    id: str
    kind: str
    text: str
    span: dict
    value: object = None


def lex(source, ids, diagnostics):
    s, i, tokens = source.text, 0, []

    def error(code, msg, start, end, rules=()):
        diagnostics.add(code, msg, source.span(start, end), 'P1', rules)
        raise StopCompilation()

    def emit(kind, start, end, value=None):
        tokens.append(Token(ids.new('token'), kind, s[start:end], source.span(start, end), value))

    while i < len(s):
        start, c = i, s[i]
        if c in ' \t\r\n\v\f':
            i += 1
        elif s.startswith('//', i):
            i += 2
            while i < len(s) and s[i] not in '\r\n': i += 1
        elif s.startswith('/*', i):
            i, depth = i + 2, 1
            while i < len(s) and depth:
                if s.startswith('/*', i): depth, i = depth+1, i+2
                elif s.startswith('*/', i): depth, i = depth-1, i+2
                else: i += 1
            if depth: error('unterminated_comment', 'Unterminated nested block comment.', start, i)
        elif c in '\"\'':
            quote, decoded = c, []
            i += 1
            escapes = {'n':'\n', 'r':'\r', 't':'\t', '0':'\0', '\\':'\\', quote:quote}
            while i < len(s) and s[i] != quote:
                if s[i] in '\r\n': error('unsupported_multiline_literal', 'Multiline literal syntax is not implemented.', start, i)
                if s[i] == '\\':
                    i += 1
                    if i == len(s): break
                    if s[i] not in escapes: error('unsupported_escape', 'Only the escapes explicitly listed in Section 7 are implemented.', i-1, i+1)
                    decoded.append(escapes[s[i]])
                else:
                    if 0xD800 <= ord(s[i]) <= 0xDFFF: error('invalid_scalar', 'Surrogate in source.', i, i+1)
                    decoded.append(s[i])
                i += 1
            if i == len(s): error('unterminated_literal', 'Unterminated literal.', start, i)
            i += 1
            value = ''.join(decoded)
            if quote == "'" and len(value) != 1: error('invalid_character_literal', 'A character denotes exactly one Unicode scalar.', start, i)
            emit('char' if quote == "'" else 'string', start, i, value)
        elif '0' <= c <= '9':
            i += 1
            # Maximal numeric candidate; malformed suffixes are errors, not split tokens.
            while i < len(s):
                d = s[i]
                if d.isascii() and (d.isalnum() or d == '_'): i += 1
                elif d == '.' and not s.startswith('..', i) and '.' not in s[start:i] and not s[start:i].startswith(('0x','0b','0o')): i += 1
                elif d in '+-' and s[i-1] in 'eE' and not s[start:i].startswith(('0x','0b','0o')): i += 1
                else: break
            raw = s[start:i]
            if INT.fullmatch(raw):
                clean = raw.replace('_','')
                try:
                    value = int(clean, 0) if clean.startswith(('0x','0o','0b')) else int(clean, 10)
                except ValueError:
                    error('unsupported_literal_size', 'Integer literal exceeds the host parsing resource limit.', start, i)
                emit('int', start, i, value)
            elif FLOAT.fullmatch(raw): emit('float', start, i, raw)
            else: error('invalid_number', f'Malformed numeric literal {raw!r}.', start, i, ['PARSE-015','PARSE-018'])
        elif identifier_start(c):
            i += 1
            while i < len(s) and identifier_continue(s[i]): i += 1
            raw = s[start:i]
            if not moderately_restrictive(raw):
                error('invalid_identifier_security', 'Identifier fails the Unicode 17 Moderately Restrictive profile.', start, i, ['PARSE-199','PARSE-200'])
            emit('keyword' if raw in KEYWORDS else 'type' if raw in TYPES else 'literal' if raw in LITERALS else 'identifier', start, i)
        elif ord(c) > 127:
            error('invalid_identifier_character', 'Character is not permitted by Unicode 17 identifier syntax.', i, i+1, ['PARSE-194','PARSE-201'])
        else:
            op = next((op for op in OPS if s.startswith(op, i)), None)
            if op is None: error('invalid_character', f'Unexpected character {c!r}.', i, i+1)
            i += len(op)
            emit('punctuation', start, i)
    emit('eof', len(s), len(s))
    return tokens
