"""Spanned AST and normalized syntax for the first scalar milestone."""
from dataclasses import dataclass, field
from .source import StopCompilation
from .lexer import KEYWORDS, TYPES, LITERALS
from .unicode_identifiers import skeleton


@dataclass
class Node:
    id: str
    kind: str
    span: dict
    data: dict = field(default_factory=dict)


# Section 26: numeric precedence increases with binding strength.
PRECEDENCE = {'=':1, '||':2, '&&':3, '|':4, '^':5, '&':6,
              '==':7, '!=':7, '<':8, '<=':8, '>':8, '>=':8,
              '<<':9, '>>':9, '+':10, '-':10, '*':11, '/':11, '%':11}


class Parser:
    def __init__(self, tokens, ids, diagnostics):
        self.tokens, self.ids, self.diagnostics, self.i = tokens, ids, diagnostics, 0
        self.struct_names = {tokens[i+1].text for i, t in enumerate(tokens[:-1]) if t.text == 'struct'}

    @property
    def current(self): return self.tokens[self.i]

    def take(self):
        t = self.current
        if t.kind != 'eof': self.i += 1
        return t

    def accept(self, text):
        if self.current.text == text: return self.take()
        return None

    def error(self, message, code='syntax_error', rules=()):
        self.diagnostics.add(code, message, self.current.span, 'P2', rules)
        raise StopCompilation()

    def expect(self, text):
        if self.current.text != text: self.error(f'Expected {text!r}, found {self.current.text!r}.')
        return self.take()

    def name(self):
        if self.current.kind != 'identifier': self.error('Expected a user-defined identifier; protected names cannot be declared.', rules=['PARSE-010'])
        if any(skeleton(self.current.text) == skeleton(n) for n in KEYWORDS | TYPES | LITERALS):
            self.error('Identifier is confusable with a protected name.', 'confusable_identifier', ['PARSE-203','PARSE-205'])
        return self.take()

    def node(self, kind, first, **data):
        a = first.span
        b = self.tokens[max(0,self.i-1)].span
        return Node(self.ids.new('ast'), kind, dict(a, end_line=b['end_line'], end_col=b['end_col']), data)

    def type_name(self, mutable=False):
        mutable = bool(self.accept('mut')) or mutable
        t = self.current
        if t.kind not in ('identifier','type'): self.error('Expected a type.')
        self.take()
        array_suffix=''
        while self.accept('['):
            length=self.take()
            if length.kind != 'int' or length.value < 0:
                self.error('Array length requires a nonnegative integer literal.', 'unsupported_array_length')
            self.expect(']')
            array_suffix+='['+str(length.value)+']'
        pointer = bool(self.accept('*'))
        if self.current.text in ('*','?','<','::') or t.text == 'raw':
            self.error('Compound, pointer and generic types are not implemented.', 'unsupported_type')
        if mutable and not pointer: self.error('Type-level mut requires a managed pointer.', 'unsupported_type')
        return ('mut ' if mutable else '') + t.text + array_suffix + ('*' if pointer else '')

    def parse(self):
        first, module, functions, exports, structs = self.current, None, [], [], []
        while self.current.kind != 'eof':
            if self.accept('module'):
                if module is not None: self.error('A translation unit must define exactly one module.', rules=['PARSE-001'])
                parts = [self.name().text]
                while self.accept('.'): parts.append(self.name().text)
                self.expect(';'); module = '.'.join(parts)
            elif self.accept('export'):
                self.expect('{')
                while not self.accept('}'):
                    exports.append(self.name()); self.expect(';')
            elif self.current.text == 'fn': functions.append(self.function())
            elif self.current.text == 'struct': structs.append(self.struct())
            elif self.current.text in ('enum','alias','const','import','extern','unsafe'):
                self.error('This top-level declaration is not implemented.', 'unsupported_declaration')
            else: self.error('Expected module, export block, or function declaration.')
        if module is None: self.error('A translation unit must define exactly one module.', rules=['PARSE-001'])
        return self.node('module', first, name=module, functions=functions, exports=exports, structs=structs)

    def struct(self):
        first = self.expect('struct'); name = self.name()
        if self.current.text == '<': self.error('Generic structs are not implemented.', 'unsupported_struct')
        self.expect('{'); fields = []
        while self.current.text != '}':
            start = self.current; typ = self.type_name(); field_name = self.name()
            self.expect(';')
            fields.append(self.node('field', start, name=field_name.text, type=typ))
        self.expect('}')
        return self.node('struct', first, name=name.text, fields=fields)

    def function(self):
        first = self.expect('fn'); name = self.name()
        if self.current.text in ('<','::'): self.error('Generic/associated functions are not implemented.', 'unsupported_function')
        self.expect('('); params = []
        if self.current.text != ')':
            while True:
                p = self.current; mutable = bool(self.accept('mut'))
                if mutable and self.current.text == 'mut': self.error('Repeated mut qualifier.')
                typ = self.type_name()
                if mutable and typ.endswith('*'): typ = 'mut '+typ; mutable = False
                binding_mutable=bool(self.accept('mut'))
                n=self.name()
                params.append(self.node('param', p, name=n.text, type=typ, mutable=mutable or binding_mutable))
                if not self.accept(','): break
        self.expect(')')
        result = self.type_name() if self.accept(':') else 'void'
        body = self.block()
        return self.node('function', first, name=name.text, params=params, result=result, body=body)

    def block(self):
        first = self.expect('{'); statements = []
        while self.current.text != '}':
            if self.current.kind == 'eof': self.error('Unterminated block.')
            statements.append(self.statement())
        self.expect('}')
        return self.node('block', first, statements=statements)

    def statement(self):
        first = self.current
        if first.text == '{': return self.block()
        if self.accept('return'):
            e = None if self.current.text == ';' else self.expression()
            self.expect(';'); return self.node('return', first, value=e)
        if self.accept('if'):
            cond = self.expression(); yes = self.block(); no = None
            if self.accept('else'): no = self.statement() if self.current.text == 'if' else self.block()
            return self.node('if', first, condition=cond, yes=yes, no=no)
        if self.accept('defer'):
            body = self.block(); self.expect(';')
            return self.node('defer', first, body=body)
        if first.text in ('while','for','foreach','loop','match','break','continue','unsafe'):
            self.error(f'{first.text} is not implemented in this milestone.', 'unsupported_statement')
        # Typed declarations; unknown type names remain AST types for resolution.
        is_decl = first.text in ('mut','const') or first.kind == 'type' or (
            first.kind == 'identifier' and (self.tokens[self.i+1].kind == 'identifier' or
                (first.text in self.struct_names and self.tokens[self.i+1].text in ('*','['))))
        if is_decl:
            const = bool(self.accept('const')); mutable = bool(self.accept('mut'))
            if const and mutable: self.error('A constant cannot be mutable.')
            if mutable and self.current.text == 'mut': self.error('Repeated mut qualifier.')
            typ = self.type_name()
            binding_mutable=bool(self.accept('mut'))
            if mutable and typ.endswith('*'): typ = 'mut '+typ; mutable = False
            if const and binding_mutable: self.error('A constant cannot have a mutable binding.')
            if mutable and binding_mutable: self.error('Repeated binding mut qualifier.')
            mutable=mutable or binding_mutable
            name = self.name()
            value = self.expression() if self.accept('=') else None
            if const and value is None: self.error('A constant requires an initializer.')
            self.expect(';')
            return self.node('decl', first, name=name.text, type=typ, mutable=mutable, const=const, value=value)
        expr = self.expression(); self.expect(';')
        return self.node('expr', first, value=expr)

    def expression(self, minimum=1):
        first = self.take()
        if first.text == '&':
            mutable = bool(self.accept('mut'))
            left = self.node('borrow', first, mutable=mutable, value=self.expression(12))
        elif first.text == '*':
            left = self.node('deref', first, value=self.expression(12))
        elif first.text in ('!','+','-','move'):
            left = self.node('unary', first, operator=first.text, value=self.expression(12))
        elif first.text in ('match','null'):
            self.error('Borrowing, dereference, match and null expressions are not implemented.', 'unsupported_expression')
        elif first.text == '[':
            values=[]
            if self.current.text != ']':
                while True:
                    values.append(self.expression())
                    if not self.accept(',') or self.current.text == ']': break
            self.expect(']')
            left=self.node('array_literal',first,values=values)
        elif first.text == '(':
            left = self.expression(); self.expect(')')
        elif first.kind in ('int','float','char','string') or first.text in ('true','false'):
            left = self.node('literal', first, literal_kind=first.kind if first.kind != 'literal' else 'bool', value=first.value if first.kind != 'literal' else first.text == 'true')
        elif first.kind == 'identifier': left = self.node('name', first, name=first.text)
        else: self.error('Expected an expression.')
        while True:
            if self.current.text == '{' and left.kind == 'name' and left.data['name'] in self.struct_names:
                self.take(); fields = []
                if self.current.text != '}':
                    while True:
                        name = self.name(); self.expect('='); value = self.expression()
                        fields.append(self.node('field_initializer', name, name=name.text, value=value))
                        if not self.accept(',') or self.current.text == '}': break
                self.expect('}')
                left = self.node('construct', left, type=left.data['name'], fields=fields)
            elif self.current.text == '(':
                self.take(); args = []
                if self.current.text != ')':
                    while True:
                        args.append(self.expression())
                        if not self.accept(','): break
                self.expect(')'); left = self.node('call', left, callee=left, args=args)
            elif self.accept('.'):
                name = self.name()
                left = self.node('member', left, value=left, name=name.text)
            elif self.accept('->'):
                base = self.node('deref', left, value=left)
                name = self.name()
                left = self.node('member', left, value=base, name=name.text)
            elif self.accept('['):
                index=self.expression(); self.expect(']')
                left=self.node('index',left,value=left,index=index)
            elif self.current.text in ('::','?'):
                self.error('Qualified/member/index/propagation expressions are not implemented.', 'unsupported_expression')
            else:
                op = self.current.text; prec = PRECEDENCE.get(op,0)
                if prec < minimum: break
                self.take(); right = self.expression(prec if op == '=' else prec+1)
                left = self.node('binary', left, operator=op, left=left, right=right)
        return left


def normalize(node):
    """Explicit normalization boundary; parser already makes precedence and void explicit."""
    return node
