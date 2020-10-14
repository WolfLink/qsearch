"""
This module defines solvers that use multiple starting points in order to have a higher chance at finding the global minimum.
"""
from . import utils, logging
from .solvers import Solver, default_solver
import numpy as np
import scipy as sp
import scipy.optimize
from qsrs import native_from_object
import time
from math import pi, gamma, sqrt

from multiprocessing import Queue, Process
from .persistent_aposmm import initialize_APOSMM, decide_where_to_start_localopt, update_history_dist, add_to_local_H

def distance_for_x(x, options, circuit):
    """Calculate the distance between circuit and the target for input x based on the distance metric"""
    if options.inner_solver.distance_metric == "Frobenius":
        return options.error_func(options.target, circuit.matrix(x))
    elif options.inner_solver.distance_metric == "Residuals":
        return np.sum(options.error_residuals(options.target, circuit.matrix(x), np.eye(options.target.shape[0]))**2)

def optimize_worker(circuit, options, q, x0):
    """Worker function used to run the inner solver in parallel"""
    _, xopt = options.inner_solver.solve_for_unitary(circuit, options, x0)
    q.put((distance_for_x(xopt, options, circuit), xopt))

class MultiStart_Solver(Solver):
    """A higher accuracy solver based on APOSMM https://www.mcs.anl.gov/~jlarson/APOSMM/

    MultiStart_Solver generally gets better results than other optimizers due to the advanced algorithm
    to start multiple local optimizers ("inner solvers") and find the global optimum more often.
    """

    def __init__(self, num_threads):
        """Create a MultiStart_Solver instance. Pass num_threads to set how many threads to use in parallel optimization runs"""
        self.num_threads = num_threads

    def solve_for_unitary(self, circuit, options, x0=None):
        """Optimize the given circuit based on the provided options with initial point x0 (optional).
        
        This uses the "inner_solver" options attribute to set which optimizer to use for local optimization runs.
        """
        if 'inner_solver' not in options:
            options.inner_solver = default_solver(options)
        U = options.target
        logger = options.logger if "logger" in options else logging.Logger(verbosity=options.verbosity, stdout_enabled=options.stdout_enabled, output_file=options.log_file)

        #np.random.seed(4) # usually we do not want fixed seeds, but it can be useful for some debugging
        n = circuit.num_inputs # the number of parameters to optimize (the length that v should be when passed to one of the lambdas created above)
        initial_sample_size = 100  # How many points do you want to sample before deciding where to start runs.
        num_localopt_runs = self.num_threads  # How many localopt runs to start?

        specs = {'lb': np.zeros(n),
                 'ub': np.ones(n),
                 'standalone': True,
                 'initial_sample_size':initial_sample_size}

        _, _, rk_const, ld, mu, nu, _, H = initialize_APOSMM([],specs,None)

        initial_sample = np.random.uniform(0, 1, (initial_sample_size, n))

        add_to_local_H(H, initial_sample, specs, on_cube=True)

        for i, x in enumerate(initial_sample):
            H['f'][i] = distance_for_x(2*np.pi*x, options, circuit)

        H[['returned']] = True

        update_history_dist(H, n)
        starting_inds = decide_where_to_start_localopt(H, n, initial_sample_size, rk_const, ld, mu, nu)

        starting_points = H['x'][starting_inds[:num_localopt_runs]]

        start = time.time()
        q = Queue()
        processes = []
        rets = []
        for x0 in starting_points:
            p = Process(target=optimize_worker, args=(circuit, options, q, 2*np.pi*x0))
            processes.append(p)
            p.start()
        for p in processes:
            ret = q.get() # will block
            rets.append(ret)
        for p in processes:
            p.join()
        end = time.time()

        best_found = np.argmin([r[0] for r in rets])
        best_val = rets[best_found][0]

        xopt = rets[best_found][1]

        return (circuit.matrix(xopt), xopt)

class NaiveMultiStart_Solver(Solver):
    """A naive but effective multi-start solver which tries to cover as much of the optimization space at once"""
    def __init__(self, num_threads):
        """Create a NaiveMultiStart_Solver instance. Pass num_threads to set how many threads to use in parallel optimization runs"""
        self.threads = num_threads if num_threads else 1

    def solve_for_unitary(self, circuit, options, x0=None):
        if 'inner_solver' not in options:
            options.inner_solver = default_solver(options)
        U = options.target
        logger = options.logger if "logger" in options else logging.Logger(verbosity=options.verbosity, stdout_enabled=options.stdout_enabled, output_file=options.log_file)
        n = circuit.num_inputs
        initial_samples = [np.random.uniform((i - 1)/self.threads, i/self.threads, (circuit.num_inputs,)) for i in range(1, self.threads+1)]
        q = Queue()
        processes = []
        rets = []
        for x0 in initial_samples:
            p = Process(target=optimize_worker, args=(circuit, options, q, x0))
            processes.append(p)
            p.start()
        for p in processes:
            ret = q.get() # will block
            rets.append(ret)
        for p in processes:
            p.join()

        best_found = np.argmin([r[0] for r in rets])
        best_val = rets[best_found][0]

        xopt = rets[best_found][1]

        return (circuit.matrix(xopt), xopt)
