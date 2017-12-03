import sys

import gym
from gym.envs.registration import register
from gym import spaces
from six import StringIO

from bitboard import WIDTH, HEIGHT, NUM_COLORS
from state import State, ACTIONS


MAX_CHAIN = 13


class PdPEndlessEnv(gym.Env):
    """
    Panel de Pon environment. Single player endless mode.
    """

    metadata = {"render.modes": ["human", "ansi"]}
    reward_range = (0, MAX_CHAIN)
    action_space = spaces.Discrete((WIDTH - 1) * HEIGHT + 2)
    observation_space = spaces.Tuple((
        spaces.Discrete(MAX_CHAIN),
        spaces.Box(0, 1, (NUM_COLORS + 3, HEIGHT, WIDTH)),
    ))

    def __init__(self):
        self.state = State()
        self._seed()

    def _seed(self, seed=None):
        seed = self.state.seed(seed)
        return [seed]

    def _reset(self):
        self.state.reset()
        return (self.state.chain_number, self.state.encode())

    def _render(self, mode="human", close=False):
        if close:
            return
        outfile = StringIO() if mode == "ansi" else sys.stdout
        self.state.render(outfile)
        return outfile

    def _step(self, action):
        action = ACTIONS[action]
        chain_size, combo_size = self.state.step(action)
        reward = min(chain_size, MAX_CHAIN)
        chain_number = min(self.state.chain_number, MAX_CHAIN - 1)
        observation = (chain_number, self.state.encode())
        return observation, reward, False, {"state": self.state}

    @property
    def _state(self):
        return self.state


register(
    id="PdPEndless-v0",
    entry_point="env:PdPEndlessEnv",
    max_episode_steps=200,
    reward_threshold=25.0,
)