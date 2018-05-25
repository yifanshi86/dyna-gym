"""
Inferred Q-values UCT Algorithm
"""

import gym
import random
import itertools
import numpy as np
from math import sqrt, log
from copy import copy
from sklearn.linear_model import Ridge

def poly_feature(x, deg):
    result = np.array([],float)
    for i in range(deg+1):
        result = np.append(result, [x**i])
    return result

def poly_reg(data, x):
    '''
    Perform Linear Regression with Polynomial features and returns the predictor.
    Data should have the form [[x,y], ...].
    Return the prediction at the value specified by x
    '''
    reg = 1 # Regularization
    deg = 1 # Degree of the polynomial
    X = []
    y = []
    for d in data:
        X = np.append(X, poly_feature(d[0], deg))
        y = np.append(y, d[1])
    X = X.reshape((len(data), deg+1))
    clf = Ridge(alpha=reg)
    clf.fit(X, y)
    return clf.predict(poly_feature(x, deg).reshape(1,-1))

def snapshot_value(node):
    '''
    Value estimate of a chance node wrt current snapshot model of the MDP
    '''
    return sum(node.sampled_returns) / len(node.sampled_returns)

def inferred_value(node):
    '''
    Value estimate of a chance node wrt selected predictor
    No inference is performed in the three following cases:
    - the node has depth 0;
    - the node has no history;
    - the history has too few data points.
    @TODO maybe consider inferring only with a higher number of data points
    '''
    if node.depth > 0 and node.history and (len(node.history[2]) > 1):
        return poly_reg(node.history[2], 0)
    else:
        return snapshot_value(node)

def combinations(space):
    if isinstance(space, gym.spaces.Discrete):
        return range(space.n)
    elif isinstance(space, gym.spaces.Tuple):
        return itertools.product(*[combinations(s) for s in space.spaces])
    else:
        raise NotImplementedError

def update_histories(histories, node, env):
    '''
    Update the collected histories.
    Recursive method.
    @TODO discard the elements once their duration is 0
    '''
    for child in node.children:
        if child.sampled_returns: # Ensure there are sampled returns
            # Update history of child
            match = False
            duration = child.depth * env.tau
            for h in histories:
                if (h[1] == child.action) and env.equality_operator(h[0],child.parent.state): # The child's state-action pair matches an already built history
                    h[2].append([snapshot_value(child),duration])
                    match = True
                    break
            if not match: # No match occured, add a new history
                    histories.append([
                        child.parent.state,
                        child.action,
                        [[snapshot_value(child),duration]]
                    ])
            # Recursive call
            for grandchild in child.children:
                update_histories(histories,grandchild,env)

class DecisionNode:
    '''
    Decision node class, labelled by a state
    '''
    def __init__(self, parent, state):
        self.parent = parent
        self.state = state
        if self.parent is None: # Root node
            self.depth = 0
        else: # Non root node
            self.depth = parent.depth + 1
        self.children = []
        self.explored_children = 0
        self.visits = 0

class ChanceNode:
    '''
    Chance node class, labelled by a state-action pair
    The state is accessed via the parent attribute
    '''
    def __init__(self, parent, action, env, histories):
        self.parent = parent
        self.action = action
        self.depth = parent.depth
        self.children = []
        self.sampled_returns = []

        self.history = []
        for h in histories:
            if (h[1] == self.action) and env.equality_operator(h[0],self.parent.state):
                self.history = h

class IQUCT(object):
    '''
    IQUCT agent
    '''
    def __init__(self, action_space, gamma, rollouts, max_depth, is_model_dynamic):
        self.action_space = action_space
        self.gamma = gamma
        self.rollouts = rollouts
        self.max_depth = max_depth
        self.is_model_dynamic = is_model_dynamic

        self.histories = [] # saved histories

    def act(self, env, done):
        '''
        Compute the entire UCT procedure
        '''
        root = DecisionNode(None, env.get_state())
        for _ in range(self.rollouts):
            rewards = [] # Rewards collected along the tree for the current rollout
            node = root # Current node
            terminal = done

            # Selection
            select = True
            expand_chance_node = False
            while select and (len(root.children) != 0):
                if (type(node) == DecisionNode): # Decision node
                    if node.explored_children < len(node.children): # Go to unexplored chance node
                        child = node.children[node.explored_children]
                        node.explored_children += 1
                        node = child
                        select = False
                    else: # Go to chance node maximizing UCB
                        node = max(node.children, key=inferred_value)
                else: # Chance Node
                    state_p, reward, terminal = env.transition(node.parent.state,node.action,self.is_model_dynamic)
                    rewards.append(reward)
                    if (len(node.children) == 0): # No child
                        expand_chance_node = True
                        select = False
                    else: # Already has children
                        for i in range(len(node.children)):
                            if env.equality_operator(node.children[i].state,state_p): # State already sampled
                                node = node.children[i]
                                break
                            else: # New state sampled
                                expand_chance_node = True
                                select = False
                                break

            # Expansion
            if expand_chance_node and (type(node) == ChanceNode): # Expand a chance node
                node.children.append(DecisionNode(node,state_p))
                node = node.children[-1]
            if (type(node) == DecisionNode): # Expand a decision node
                if terminal:
                    node = node.parent
                else:
                    node.children = [ChanceNode(node,a,env,self.histories) for a in combinations(env.action_space)]
                    random.shuffle(node.children)
                    child = node.children[0]
                    node.explored_children += 1
                    node = child

            # Evaluation
            t = 0
            estimate = 0
            state = node.parent.state
            while not terminal:
                action = env.action_space.sample() # default policy
                state, reward, terminal = env.transition(state,action,self.is_model_dynamic)
                estimate += reward * (self.gamma**t)
                t += 1
                if node.depth + t > self.max_depth:
                    break

            # Backpropagation
            while node:
                node.sampled_returns.append(estimate)
                if len(rewards) != 0:
                    estimate = rewards.pop() + self.gamma * estimate
                node.parent.visits += 1
                node = node.parent.parent
        update_histories(self.histories, root, env)
        return max(root.children, key=inferred_value).action