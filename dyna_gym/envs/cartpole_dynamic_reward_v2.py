"""
Cart-pole system with a dynamic reward function.
The objective is to keep the pole within a cone varying with time.
"""

import logging
import math
import gym
from gym import error, spaces, utils
from gym.utils import seeding
import numpy as np

logger = logging.getLogger(__name__)

class CartPoleDynamicRewardV2(gym.Env):
    metadata = {
        'render.modes': ['human', 'rgb_array'],
        'video.frames_per_second' : 50
    }

    def __init__(self):
        self.gravity = 9.8
        self.masscart = 1.0
        self.masspole = 0.1
        self.total_mass = (self.masspole + self.masscart)
        self.length = 0.5 # actually half the pole's length
        self.polemass_length = (self.masspole * self.length)
        self.force_mag = 10.0
        self.nb_actions = 3 # number of discrete actions in [-force_mag,+force_mag]
        self.tau = 0.02  # seconds between state updates

        # Angle at which to fail the episode
        self.x_threshold = 2.4

        # Dynamic parameters
        self.theta_magnitude = 12 * 2 * math.pi / 360 # Max theta magnitude
        self.oscillation_magnitude = 18 * 2 * math.pi / 360 # Oscillation magnitude
        self.oscillation_period = 2 # Oscillation period in seconds
        self.tol = 0.2 # Maximum allowed distance to center

        # Angle limit set to 2 * theta_magnitude so failing observation is still within bounds
        high = np.array([
            self.x_threshold * 2,
            np.finfo(np.float32).max,
            self.theta_magnitude * 2,
            np.finfo(np.float32).max])
        self.delta = 0

        self.action_space = spaces.Discrete(self.nb_actions)
        self.observation_space = spaces.Box(-high, high)

        self._seed()
        self.viewer = None
        self.state = None
        self.steps_beyond_done = None

    def equality_operator(self, s1, s2):
        '''
        Equality operator, return True if the two input states are equal.
        Only test the 4 first components (x, x_dot, theta, theta_dot)
        '''
        for i in range(4):
            if not math.isclose(s1[i], s2[i], rel_tol=1e-5):
                return False
        return True

    def reset(self):
        self.state = self.np_random.uniform(low=-0.05, high=0.05, size=(4,))
        self.state = np.append(self.state,0.0) # time
        self.steps_beyond_done = None
        return np.array(self.state)

    def _seed(self, seed=None):
        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def transition(self, state, action, is_model_dynamic):
        '''
        Transition operator, return the resulting state, reward and a boolean indicating
        whether the termination criterion is reached or not.
        The boolean is_model_dynamic indicates whether the temporal transition is applied
        to the state vector or not (increment of tau).
        '''
        x, x_dot, theta, theta_dot, time = state
        force = - self.force_mag + action * 2 * self.force_mag / (self.nb_actions - 1)
        costheta = math.cos(theta)
        sintheta = math.sin(theta)
        temp = (force + self.polemass_length * theta_dot * theta_dot * sintheta) / self.total_mass
        thetaacc = (self.gravity * sintheta - costheta* temp) / (self.length * (4.0/3.0 - self.masspole * costheta * costheta / self.total_mass))
        xacc  = temp - self.polemass_length * thetaacc * costheta / self.total_mass
        x  = x + self.tau * x_dot
        x_dot = x_dot + self.tau * xacc
        theta = theta + self.tau * theta_dot
        theta_dot = theta_dot + self.tau * thetaacc
        if is_model_dynamic:
            time = time + self.tau
        state_p = (x, x_dot, theta, theta_dot, time)
        # Termination criterion
        self.delta = self.oscillation_magnitude * math.sin(time * 6.28318530718 / self.oscillation_period)
        done =  x < -self.x_threshold \
                or x > self.x_threshold \
                or theta < -self.theta_magnitude + self.delta \
                or theta > self.theta_magnitude + self.delta
        done = bool(done)

        if not done:
            reward = 1.0
        else:
            reward = 0.0
        return state_p, reward, done

    def step(self, action):
        '''
        Step function equivalent to transition and reward function.
        Actually modifies the environment's state attribute.
        Return (observation, reward, termination criterion (boolean), informations)
        '''
        assert self.action_space.contains(action), "%r (%s) invalid"%(action, type(action))
        self.state, reward, done = self.transition(self.state, action, True)
        return np.array(self.state), reward, done, {}

    def print_state(self):
        print('x: {:.5f}; x_dot: {:.5f}; theta: {:.5f}; theta_dot: {:.5f}'.format(self.state[0],self.state[1],self.state[2],self.state[3]))

    def render(self, mode='human', close=False):
        if close:
            if self.viewer is not None:
                self.viewer.close()
                self.viewer = None
            return

        screen_width = 600
        screen_height = 400

        world_width = self.x_threshold*2
        scale = screen_width/world_width
        carty = 100 # TOP OF CART
        polewidth = 10.0
        polelen = scale * 1.0
        cartwidth = 50.0
        cartheight = 30.0

        if self.viewer is None:
            from gym.envs.classic_control import rendering
            self.viewer = rendering.Viewer(screen_width, screen_height)
            l,r,t,b = -cartwidth/2, cartwidth/2, cartheight/2, -cartheight/2
            axleoffset =cartheight/4.0
            cart = rendering.FilledPolygon([(l,b), (l,t), (r,t), (r,b)])
            self.carttrans = rendering.Transform()
            cart.add_attr(self.carttrans)
            self.viewer.add_geom(cart)
            l,r,t,b = -polewidth/2,polewidth/2,polelen-polewidth/2,-polewidth/2
            pole = rendering.FilledPolygon([(l,b), (l,t), (r,t), (r,b)])
            pole.set_color(.8,.6,.4)
            self.poletrans = rendering.Transform(translation=(0, axleoffset))
            pole.add_attr(self.poletrans)
            pole.add_attr(self.carttrans)
            self.viewer.add_geom(pole)

            self.axle = rendering.make_circle(polewidth/2)
            self.axle.add_attr(self.poletrans)
            self.axle.add_attr(self.carttrans)
            self.axle.set_color(.5,.5,.8)
            self.viewer.add_geom(self.axle)

            # Left bar
            l,r,t,b = -1,1,1000,0
            lbar = rendering.FilledPolygon([(l,b), (l,t), (r,t), (r,b)])
            lbar.set_color(0,0,0)
            self.lbartrans = rendering.Transform(translation=(0, axleoffset))
            lbar.add_attr(self.lbartrans)
            lbar.add_attr(self.carttrans)
            self.viewer.add_geom(lbar)

            # Right bar
            l,r,t,b = -1,1,1000,0
            rbar = rendering.FilledPolygon([(l,b), (l,t), (r,t), (r,b)])
            rbar.set_color(0,0,0)
            self.rbartrans = rendering.Transform(translation=(0, axleoffset))
            rbar.add_attr(self.rbartrans)
            rbar.add_attr(self.carttrans)
            self.viewer.add_geom(rbar)

            self.track = rendering.Line((0,carty), (screen_width,carty))
            self.track.set_color(0,0,0)
            self.viewer.add_geom(self.track)

        if self.state is None: return None

        x = self.state
        cartx = x[0]*scale+screen_width/2.0 # MIDDLE OF CART
        self.carttrans.set_translation(cartx, carty)
        self.poletrans.set_rotation(-x[2])
        self.rbartrans.set_rotation(-self.theta_magnitude - self.delta)
        self.lbartrans.set_rotation(self.theta_magnitude - self.delta)

        return self.viewer.render(return_rgb_array = mode=='rgb_array')
