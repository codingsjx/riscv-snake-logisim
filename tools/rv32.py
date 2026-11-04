"""Small, strict assembler and instruction-level runner for this project.

No pseudoinstructions or implicit instruction expansion: ROM addresses are exact.
This runner verifies software; actual Logisim pipeline checks are separate.
"""
from pathlib import Path
import re

ALIASES = {'zero': 0, 'ra': 1, 'sp': 2, 'gp': 3, 'tp': 4,
           't0': 5, 't1': 6, 't2': 7, 's0': 8, 's1': 9,
           **{f'a{i}': 10+i for i in range(8)},
           **{f's{i}': 16+i for i in range(2, 12)},
           't3': 28, 't4': 29, 't5': 30, 't6': 31,
           **{f'x{i}': i for i in range(32)}}
R = {'add': (0, 0), 'sub': (0, 32), 'and': (7, 0), 'or': (6, 0),
     'slt': (2, 0), 'sltu': (3, 0)}
I = {'addi': 0, 'andi': 7, 'ori': 6, 'xori': 4, 'slti': 2, 'sltiu': 3}


def signed(n, bits=32):
    n &= (1 << bits)-1
    return n-(1 << bits) if n & (1 << (bits-1)) else n


def imm(n, bits):
    if not -(1 << (bits-1)) <= n < (1 << (bits-1)):
        raise ValueError(f'immediate {n} does not fit {bits} signed bits')
    return n & ((1 << bits)-1)


def assemble(path):
    labels, lines = {}, []
    for line_no, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            label = line[:-1]
            if label in labels:
                raise ValueError(f'duplicate label {label}')
            labels[label] = len(lines)*4
        else:
            lines.append((line_no, line))
    words = []
    for pc, (line_no, line) in enumerate(lines):
        try:
            op, *a = re.split(r'[\s,()]+', line.rstrip(')'))
            if op in R:
                rd, rs1, rs2 = map(ALIASES.__getitem__, a)
                f3, f7 = R[op]
                word = f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | 0x33
            elif op in I or op in ('slli', 'srli', 'srai'):
                rd, rs1 = map(ALIASES.__getitem__, a[:2])
                n = int(a[2], 0)
                if op in I:
                    f3, n = I[op], imm(n, 12)
                else:
                    if not 0 <= n < 32:
                        raise ValueError('invalid shift')
                    f3 = 1 if op == 'slli' else 5
                    n |= 0x400 if op == 'srai' else 0
                word = n << 20 | rs1 << 15 | f3 << 12 | rd << 7 | 0x13
            elif op in ('lw', 'sw', 'jalr'):
                reg, n, base = ALIASES[a[0]], imm(int(a[1], 0), 12), ALIASES[a[2]]
                if op == 'sw':
                    word = (n >> 5) << 25 | reg << 20 | base << 15 | 2 << 12 | (n & 31) << 7 | 0x23
                else:
                    word = n << 20 | base << 15 | (2 if op == 'lw' else 0) << 12 | reg << 7 | (3 if op == 'lw' else 0x67)
            elif op in ('beq', 'bne'):
                rs1, rs2 = map(ALIASES.__getitem__, a[:2])
                n = imm(labels[a[2]]-pc*4, 13)
                if n & 1:
                    raise ValueError('unaligned branch')
                word = ((n >> 12) << 31 | ((n >> 5) & 63) << 25 | rs2 << 20 |
                        rs1 << 15 | (op == 'bne') << 12 | ((n >> 1) & 15) << 8 |
                        ((n >> 11) & 1) << 7 | 0x63)
            elif op == 'jal':
                rd = ALIASES[a[0]]
                n = imm(labels[a[1]]-pc*4, 21)
                if n & 1:
                    raise ValueError('unaligned jump')
                word = ((n >> 20) << 31 | ((n >> 1) & 1023) << 21 |
                        ((n >> 11) & 1) << 20 | ((n >> 12) & 255) << 12 | rd << 7 | 0x6f)
            else:
                raise ValueError(f'unsupported instruction {op}')
            words.append(word)
        except Exception as e:
            raise ValueError(f'{path}:{line_no}: {line}: {e}') from e
    return words, labels, lines


class Machine:
    def __init__(self, words):
        self.words = words
        self.reg = [0]*32
        self.mem = {}
        self.pc = 0
        self.cycles = 0
        self.stores = []
        self.raw_keys = 0

    def set_keys(self, value):
        """Model edge-latched hardware: a held button creates one event."""
        value &= 255
        self.mem[0x700] = self.mem.get(0x700, 0) | (value & ~self.raw_keys)
        self.raw_keys = value

    def load(self, addr):
        if addr & 3:
            raise ValueError(f'unaligned load {addr:x}')
        if addr == 0x704:
            return self.cycles & 0xffffffff
        if addr == 0x708:
            return self.mem.get(addr, 4096)
        return self.mem.get(addr, 0)

    def store(self, addr, value):
        if addr & 3 or not 0 <= addr < 4096:
            raise ValueError(f'out of bounds/unaligned store {addr:x}')
        self.mem[addr] = value & 0xffffffff
        if addr == 0x70c:
            self.mem[0x700] = self.mem.get(0x700, 0) & ~value
        if addr >= 0x740:
            self.stores.append((addr, value & 0xffffffff))

    def step(self):
        if self.pc & 3 or not 0 <= self.pc//4 < len(self.words):
            raise ValueError(f'PC outside program: {self.pc:x}')
        w = self.words[self.pc//4]
        op, rd, f3, rs1, rs2, f7 = w & 127, (w >> 7) & 31, (w >> 12) & 7, (w >> 15) & 31, (w >> 20) & 31, w >> 25
        x, y = self.reg[rs1], self.reg[rs2]
        nxt, value = self.pc+4, None
        n = signed(w >> 20, 12)
        if op == 0x33:
            if f3 == 0: value = x-y if f7 == 32 else x+y
            elif f3 == 7: value = x & y
            elif f3 == 6: value = x | y
            elif f3 == 2: value = int(signed(x) < signed(y))
            elif f3 == 3: value = int(x < y)
            else: raise ValueError(f'unsupported R word {w:08x}')
        elif op == 0x13:
            if f3 == 0: value = x+n
            elif f3 == 7: value = x & n
            elif f3 == 6: value = x | n
            elif f3 == 4: value = x ^ n
            elif f3 == 2: value = int(signed(x) < n)
            elif f3 == 3: value = int(x < (n & 0xffffffff))
            elif f3 == 1: value = x << rs2
            elif f3 == 5: value = signed(x) >> rs2 if f7 == 32 else x >> rs2
        elif op == 3 and f3 == 2:
            value = self.load((x+n) & 0xffffffff)
        elif op == 0x23 and f3 == 2:
            n = signed(((w >> 25) << 5) | ((w >> 7) & 31), 12)
            self.store((x+n) & 0xffffffff, y)
        elif op == 0x63 and f3 in (0, 1):
            n = signed(((w >> 31) << 12) | (((w >> 7) & 1) << 11) | (((w >> 25) & 63) << 5) | (((w >> 8) & 15) << 1), 13)
            if (x == y) == (f3 == 0): nxt = self.pc+n
        elif op == 0x6f:
            n = signed(((w >> 31) << 20) | (((w >> 12) & 255) << 12) | (((w >> 20) & 1) << 11) | (((w >> 21) & 1023) << 1), 21)
            value, nxt = self.pc+4, self.pc+n
        elif op == 0x67 and f3 == 0:
            value, nxt = self.pc+4, (x+n) & 0xfffffffe
        else:
            raise ValueError(f'unsupported word {w:08x}')
        if value is not None and rd:
            self.reg[rd] = value & 0xffffffff
        self.reg[0], self.pc = 0, nxt
        self.cycles += 1

    def until(self, predicate, limit=200000):
        for _ in range(limit):
            if predicate(self): return
            self.step()
        raise TimeoutError(f'limit reached at PC {self.pc:x}')

    def call(self, addr):
        self.reg[1], self.pc = 0xfffffffc, addr
        self.until(lambda m: m.pc == 0xfffffffc)


def build(root):
    root = Path(root)
    words, labels, lines = assemble(root/'software/snake.s')
    if len(words) > 1024:
        raise ValueError('program exceeds supplied 1024-word ROM')
    (root/'build').mkdir(exist_ok=True)
    (root/'build/snake.hex').write_text('v2.0 raw\n'+'\n'.join(f'{w:08x}' for w in words)+'\n', encoding='ascii')
    (root/'build/snake.lst').write_text('\n'.join(f'{i*4:04x} {w:08x} {line}' for i, (w, (_, line)) in enumerate(zip(words, lines)))+'\n', encoding='utf-8')
    return words, labels


if __name__ == '__main__':
    words, _ = build(Path(__file__).resolve().parents[1])
    print(f'Assembled {len(words)} instructions; {len(words)*4}/4096 ROM bytes.')
