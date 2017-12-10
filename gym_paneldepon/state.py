from __future__ import unicode_literals

import sys

import numpy as np
from gym.utils import seeding

from gym_paneldepon.bitboard import FULL, HEIGHT, NUM_COLORS, TOP, WIDTH  # noqa: I001
from gym_paneldepon.bitboard import down, get_matches, left, panels_from_list, popcount, right, up  # noqa: I001
from gym_paneldepon.util import print_color, print_reset

RAISE_STACK = object()
ACTIONS = [RAISE_STACK]
for i in range(HEIGHT):
    for j in range(WIDTH - 1):
        ACTIONS.append(j + i * WIDTH)
ACTIONS.append(None)


class State(object):
    def __init__(self, scoring_method=None, height=HEIGHT):
        if height > HEIGHT:
            raise ValueError("The maximum height is {}".format(HEIGHT))
        self.reset()
        self.seed()
        self.scoring_method = scoring_method
        self.height = height

    def reset(self):
        self.colors = [0] * NUM_COLORS
        self.falling = 0
        self.swapping = 0
        self.chaining = 0
        self.chain_number = 0

    @classmethod
    def from_list(cls, stack):
        if len(stack) % WIDTH != 0:
            raise ValueError("Panels must form complete rows")
        if len(stack) > WIDTH * HEIGHT:
            raise ValueError("Too many panels")
        colors = []
        for _ in range(NUM_COLORS):
            colors.append([])
        for panel in stack:
            for i in range(NUM_COLORS):
                colors[i].append(panel == i)
        instance = cls()
        instance.colors = list(map(panels_from_list, colors))
        instance.height = len(stack) // WIDTH
        return instance

    def sanitize(self):
        for i in range(NUM_COLORS - 1):
            self.colors[i] &= FULL
            for j in range(i + 1, NUM_COLORS):
                self.colors[j] &= ~self.colors[i]

    def seed(self, seed=None):
        self.np_random, seed = seeding.np_random(seed)
        return seed

    def clone(self):
        other = State()
        other.scoring_method = self.scoring_method
        other.height = self.height
        other.colors = self.colors[:]
        other.falling = self.falling
        other.swapping = self.swapping
        other.chaining = self.chaining
        other.chain_number = self.chain_number
        return other

    def render(self, outfile=sys.stdout):
        for i in range(self.height):
            for j in range(WIDTH):
                p = 1 << (j + i * WIDTH)
                empty = True
                for k, panels in enumerate(self.colors):
                    if p & panels:
                        print_color(
                            k + 1,
                            bright=bool(p & self.chaining),
                            outfile=outfile
                        )
                        empty = False
                if empty:
                    if p & self.swapping:
                        outfile.write("\u2015")
                    else:
                        outfile.write("\u00b7")
                elif p & self.falling:
                    if p & self.swapping:
                        outfile.write("\u25a5")
                    else:
                        outfile.write("\u25a1")
                elif p & self.swapping:
                    outfile.write("\u25a4")
                else:
                    outfile.write("\u25a3")
                outfile.write(" ")
                print_reset(outfile=outfile)
            outfile.write("\n")
        outfile.write("chain={}\n".format(self.chain_number))

    def swap(self, index):
        self.swapping = 0
        if index is None:
            return
        if index % WIDTH == WIDTH - 1:
            raise ValueError("Cannot swap off screen")
        if index >= self.height * WIDTH:
            raise ValueError("Cannot swap off screen")
        p = 1 << index
        mask = ~(p | right(p))
        for i in range(NUM_COLORS):
            swapping_left = left(self.colors[i]) & p
            swapping_right = right(self.colors[i] & p)
            swapping = swapping_left | swapping_right
            self.colors[i] &= mask
            self.colors[i] |= swapping
            self.swapping |= swapping
        c = self.chaining
        self.chaining &= mask
        self.chaining |= (left(c) & p) | right(c & p)
        # Air support needed for lateslips
        if self.swapping:
            self.swapping = ~mask

    def drop_one(self):
        self.falling = 0
        empty = FULL
        for panels in self.colors:
            empty ^= panels
        row = TOP << (WIDTH * (self.height - 1))
        protected = self.swapping
        empty &= ~self.swapping  # Air support needed for lateslips
        for i in range(self.height - 1):
            falling = down(self.chaining & ~protected) & row & empty
            self.chaining |= falling
            self.chaining ^= up(falling)
            for j in range(NUM_COLORS):
                panels = self.colors[j]
                falling = down(panels & ~protected) & row & empty
                self.falling |= falling
                panels |= falling
                falling = up(falling)
                panels ^= falling
                empty ^= falling
                self.colors[j] = panels
            row = up(row)

    def clear_matches(self):
        score = 0
        chain_beam = 0
        protected = self.falling | self.swapping
        panels = 0
        for i in range(NUM_COLORS):
            matches = get_matches(self.colors[i] & ~protected)
            chain_beam |= matches
            self.colors[i] ^= matches
            panels |= self.colors[i]
        combo_size = popcount(chain_beam)
        if self.chaining & chain_beam:
            self.chain_number += 1
        if chain_beam:
            score = self.chain_number + 1
        chain_beam = up(chain_beam) & panels
        for i in range(self.height):
            chain_beam |= up(chain_beam) & panels
        protected |= up(self.swapping)
        self.chaining &= protected
        self.chaining |= panels & chain_beam
        if not self.chaining:
            self.chain_number = 0
        return score, combo_size

    def _insert_row(self, row):
        self.falling = up(self.falling)
        self.chaining = up(self.chaining)
        self.swapping = up(self.swapping)
        for i in range(NUM_COLORS):
            self.colors[i] = up(self.colors[i])
            for j in range(WIDTH):
                if row[j] == i:
                    self.colors[i] |= 1 << (j + WIDTH * (self.height - 1))

    def raise_stack(self):
        for panels in self.colors:
            if panels & TOP:
                return
        while True:
            row = [self.np_random.randint(0, NUM_COLORS) for i in range(WIDTH)]
            temp = self.clone()
            temp._insert_row(row)
            if not temp.clear_matches()[0]:
                break
        self._insert_row(row)

    def step(self, action):
        if action is not RAISE_STACK:
            self.swap(action)
        self.drop_one()
        result = self.clear_matches()
        if action is RAISE_STACK:
            self.raise_stack()
        return self.calculate_score(result)

    def encode(self):
        np_state = np.zeros((NUM_COLORS + 3, self.height, WIDTH))
        features = self.colors[:]
        features.append(self.falling)
        features.append(self.chaining)
        features.append(self.swapping)
        for i, feature in enumerate(features):
            p = 1
            for j in range(self.height):
                for k in range(WIDTH):
                    np_state[i][j][k] = bool(p & feature)
                    p <<= 1
        return np_state

    def calculate_score(self, result):
        if self.scoring_method is None:
            return result
        chain, combo = result
        if self.scoring_method == "endless":
            if chain:
                return chain
            elif combo:
                return self.chain_number
            return 0
