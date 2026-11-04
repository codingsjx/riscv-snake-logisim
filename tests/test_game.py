import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from rv32 import Machine, build
from game_map import OBSTACLES


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

    def obstacles(self):
        return {(x,y) for y in range(16) for x in range(16)
                if self.m.mem.get(0x540+4*y,0) & (1<<(15-x))}

    def obstacle_mode(self):
        self.m.mem[0x710]=1
        self.call('game_reset')

    def arrange(self, cells, direction, food, tail=0):
        m = self.m.mem
        m[0], m[4], m[8], m[12], m[16], m[24] = len(cells), tail, (tail+len(cells)-1)&255, direction, food, 1
        for i, cell in enumerate(cells): m[256+4*((tail+i)&255)] = cell

    def poll(self, keys):
        m = self.m
        m.set_keys(keys)
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
            self.assertEqual(self.m.mem[56], 1)
            self.assertEqual(self.head(), cell)

    def test_self_collision(self):
        self.arrange([0x45, 0x55, 0x56, 0x46], 2, 0x88)
        self.call('game_step')
        self.assertEqual(self.m.mem[24], 3)
        self.assertEqual(self.m.mem[56], 2)

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

    def test_short_click_latched_until_cpu_polls(self):
        self.m.set_keys(16)
        self.m.set_keys(0)
        self.poll(0)
        self.assertEqual(self.m.mem[24], 1)
        self.assertEqual(self.m.mem[0x700], 0)

    def test_manual_mode_never_auto_moves(self):
        self.m.mem[24] = 1
        self.m.mem[0x708] = 0
        self.m.cycles = 0x70000000
        self.poll(0)
        self.assertEqual(self.head(), 0x87)
        self.poll(128)
        self.assertEqual(self.head(), 0x88)
        self.poll(128)
        self.assertEqual(self.head(), 0x88)

    def test_second_click_while_previous_frame_busy(self):
        self.poll(16)
        self.poll(0)
        self.m.mem[0x708] = 0
        self.poll(128)
        self.m.set_keys(0)
        self.m.set_keys(128)
        self.m.set_keys(0)
        self.poll(0)
        self.assertEqual(self.head(), 0x89)

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

    def test_obstacle_map_safe_and_connected(self):
        self.obstacle_mode()
        walls=self.obstacles()
        self.assertEqual(walls,OBSTACLES)
        self.assertEqual((len(walls),self.m.mem[52]),(24,232))
        self.assertTrue(all((x,8) not in walls for x in range(16)))
        seen={(0,0)};todo=[(0,0)]
        while todo:
            x,y=todo.pop()
            for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0<=p[0]<16 and 0<=p[1]<16 and p not in walls and p not in seen:
                    seen.add(p);todo.append(p)
        self.assertEqual(len(seen),232)

    def test_obstacles_collide_from_four_directions(self):
        self.obstacle_mode()
        for pos,direction in [(0x42,1),(0x33,2),(0x73,0),(0x4e,3)]:
            self.arrange([pos],direction,0x8b)
            self.call('game_step')
            self.assertEqual((self.m.mem[24],self.m.mem[56],self.head()),(3,3,pos))

    def test_obstacle_opening_is_passable(self):
        self.obstacle_mode()
        self.arrange([0x83],0,0x8b)
        self.call('game_step')
        self.assertEqual((self.head(),self.m.mem[24]),(0x73,1))

    def test_food_never_spawns_on_obstacle(self):
        self.obstacle_mode()
        walls={y*16+x for x,y in OBSTACLES}
        for seed in range(256):
            self.m.mem[20]=seed
            self.call('spawn_food')
            self.assertNotIn(self.m.mem[16],walls|{0x85,0x86,0x87})

    def test_map_change_waits_for_restart(self):
        self.obstacle_mode()
        self.m.mem[0x710]=0
        self.assertEqual(self.m.mem[48],1)
        self.assertEqual(len(self.obstacles()),24)
        self.call('game_reset')
        self.assertEqual((self.m.mem[48],self.m.mem[52]),(0,256))
        self.assertFalse(self.obstacles())
        self.assertEqual(self.m.mem[56],0)

    def test_obstacle_last_free_cell_and_win(self):
        self.obstacle_mode()
        walls={y*16+x for x,y in OBSTACLES}
        free=[p for p in range(256) if p not in walls]
        cells=[p for p in free if p not in (0,1)]+[1]
        self.arrange(cells,3,0)
        self.m.mem[20]=51  # The next LCG candidate is the sole free cell, zero.
        self.call('spawn_food')
        self.assertEqual(self.m.mem[16],0)
        self.call('game_step')
        self.assertEqual((self.m.mem[0],self.m.mem[24],self.m.mem[16]),(232,4,0xffffffff))
        self.call('render')
        self.assertEqual(self.m.mem[0x79c],1)
        self.assertEqual(sum(self.m.mem[0x7a0+4*y].bit_count() for y in range(16)),24)


if __name__ == '__main__': unittest.main(verbosity=2)
