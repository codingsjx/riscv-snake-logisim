import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from rv32 import Machine, build


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.words, cls.labels = build(ROOT)

    def setUp(self):
        self.m = Machine(self.words)
        self.m.until(lambda m: m.pc == self.labels['main'])

    def call(self, name):
        self.m.call(self.labels[name])

    def head(self):
        return self.m.mem[256+4*self.m.mem[8]]

    def arrange(self, cells, direction, food, tail=0):
        m = self.m.mem
        m[0], m[4], m[8], m[12], m[16], m[24] = len(cells), tail, (tail+len(cells)-1)&255, direction, food, 1
        for i, cell in enumerate(cells): m[256+4*((tail+i)&255)] = cell

    def poll(self, keys):
        m = self.m
        m.mem[0x700] = keys
        m.pc = self.labels['main']
        m.step()
        m.until(lambda x: x.pc == self.labels['main'])

    def test_initial_screen(self):
        self.assertEqual(self.head(), 0x87)
        self.assertEqual(self.m.mem[0x760], 0x0710)
        self.assertEqual(self.m.mem[0x784], 0)

    def test_straight_movement(self):
        self.call('game_step')
        self.assertEqual((self.head(), self.m.mem[0], self.m.mem[4]), (0x88, 3, 1))

    def test_growth_and_food_excludes_body(self):
        self.m.mem[16] = 0x88
        self.call('game_step')
        self.assertEqual((self.m.mem[0], self.m.mem[28], self.m.mem[44]), (4, 1, 1))
        cells = [self.m.mem[256+4*i] for i in range(4)]
        self.assertNotIn(self.m.mem[16], cells)

    def test_four_walls(self):
        for cell, direction in [(0x01, 0), (0x2f, 1), (0xf3, 2), (0x50, 3)]:
            self.arrange([cell], direction, 0x88)
            self.call('game_step')
            self.assertEqual(self.m.mem[24], 3)
            self.assertEqual(self.head(), cell)

    def test_self_collision(self):
        self.arrange([0x45, 0x55, 0x56, 0x46], 2, 0x88)
        self.call('game_step')
        self.assertEqual(self.m.mem[24], 3)

    def test_departing_tail_is_legal(self):
        self.arrange([0x45, 0x55, 0x56, 0x46], 3, 0x88)
        self.call('game_step')
        self.assertEqual(self.m.mem[24], 1)
        self.assertEqual(self.head(), 0x45)

    def test_queue_wrap(self):
        self.arrange([0x85, 0x86, 0x87], 1, 0x8b, 254)
        self.call('game_step')
        self.assertEqual((self.m.mem[4], self.m.mem[8], self.head()), (255, 1, 0x88))

    def test_start_pause_resume_and_button_edges(self):
        self.poll(16)
        self.assertEqual(self.m.mem[24], 1)
        self.poll(0)
        self.poll(32)
        self.assertEqual(self.m.mem[24], 2)
        self.poll(32)
        self.assertEqual(self.m.mem[24], 2)
        self.poll(0)
        self.poll(32)
        self.assertEqual(self.m.mem[24], 1)

    def test_reverse_and_fast_double_turn_blocked(self):
        self.m.mem[24] = 1
        self.poll(8)
        self.assertEqual(self.m.mem[40], 1)
        self.poll(1)
        self.assertEqual(self.m.mem[40], 0)
        self.poll(8)
        self.assertEqual(self.m.mem[40], 0)

    def test_restart_preserves_high_score(self):
        self.m.mem[44] = 10
        self.poll(64)
        self.assertEqual((self.m.mem[24], self.m.mem[28], self.m.mem[44]), (0, 0, 10))

    def test_timer_and_timer_wrap(self):
        self.m.mem[24] = 1
        self.m.mem[0x708] = 100
        self.m.cycles = 20
        self.m.mem[32] = 0xfffffff0
        self.poll(0)
        self.assertEqual(self.head(), 0x87)
        self.m.cycles = 200
        self.poll(0)
        self.assertEqual(self.head(), 0x88)

    def test_last_free_cell_and_full_board(self):
        self.arrange(list(range(1, 256)), 1, 0)
        self.call('spawn_food')
        self.assertEqual(self.m.mem[16], 0)
        # A Hamiltonian path with head at (1,0), next cell (0,0).
        cells = []
        for y in range(15, -1, -1):
            xs = range(15, -1, -1) if y % 2 == 0 else range(16)
            cells.extend(y*16+x for x in xs)
        self.assertEqual(cells[-2:], [1, 0])
        self.arrange(cells[:-1], 3, 0)
        self.call('game_step')
        self.assertEqual((self.m.mem[0], self.m.mem[24], self.m.mem[16]), (256, 4, 0xffffffff))
        self.call('render')
        self.assertTrue(all(self.m.mem[0x740+4*y] == 65535 for y in range(16)))


if __name__ == '__main__': unittest.main(verbosity=2)
