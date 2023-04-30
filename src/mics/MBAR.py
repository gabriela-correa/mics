"""
.. module:: MBAR
   :platform: Unix, Windows
   :synopsis: a module for defining the class :class:`MBAR`.

.. moduleauthor:: Charlles R. A. Abreu <abreu@eq.ufrj.br>

"""

import numpy as np
from numpy.linalg import multi_dot
from pymbar import mbar

import mics
from mics.utils import info
from mics.utils import logsumexp


class MBAR:
    """
    Machinery for mixture-model analysis using the MBAR method :cite:`Shirts_2008`.

    Parameters
    ----------
        tol : real, optional, default = 1e-12
            A tolerance for determining convergence of the self-consistent
            solution of the MBAR equations.

    """

    # ======================================================================================
    def __init__(self, tol=1e-12):
        self.tol = tol

    # ======================================================================================
    def __initialize__(self, mixture):
        m = mixture.m
        n = mixture.n

        mb = self.MBAR = mbar.MBAR(np.hstack(mixture.u), n,
                                   relative_tolerance=self.tol,
                                   initial_f_k=mixture.f,
                                   verbose=mics.verbose)

        mixture.f = mb.f_k
        mics.verbose and info("Free energies after convergence:", mixture.f)

        flnpi = (mixture.f + np.log(n/sum(n)))[:, np.newaxis]
        mixture.u0 = [-logsumexp(flnpi - u) for u in mixture.u]
        self.P = [np.exp(flnpi - mixture.u[i] + mixture.u0[i]) for i in range(m)]

        Theta = mb._computeAsymptoticCovarianceMatrix(np.exp(mb.Log_W_nk), mb.N_k)
        mixture.Theta = np.array(Theta)
        mics.verbose and info("Free-energy covariance matrix:", mixture.Theta)

        mixture.Overlap = mb.N_k*np.matmul(mb.W_nk.T, mb.W_nk)
        mics.verbose and info("Overlap matrix:", mixture.Overlap)

    # ======================================================================================
    def __reweight__(self, mixture, u, y, ref=0):
        u_ln = np.stack([np.hstack(u).flatten(),                    # new state = 0
                         np.hstack(x[ref, :] for x in mixture.u)])  # reference state = 1

        A_n = np.hstack(y)  # properties
        n = A_n.shape[0]    # number of properties

        # Compute properties [0:n-1] at state 0 and property 0 at state 1:
        smap = np.arange(2) if n == 0 else np.block([[np.zeros(n, np.int32), 1],  # states
                                                     [np.arange(n), 0]])        # properties

        results = self.MBAR.computeExpectationsInner(A_n, u_ln, smap, return_theta=True)

        # Covariance matrix of x = log(c), whose size is 2*(n+1) x 2*(n+1):
        Theta = results['Theta']

        if n == 0:
            fu = results['f'][0] - results['f'][1]
            d2fu = Theta[0, 0] + Theta[1, 1] - 2*Theta[0, 1]
            return np.array([fu]), np.array([[d2fu]])

        # Functions, whose number is n+1:
        fu = np.array([results['f'][0] - results['f'][n]])
        yu = results['observables'][0:n]

        # Gradient:
        #     fu = -ln(c[n+1]/c[2*n+1]) = x[2*n+1] - x[n+1]
        #     yu[i] = c[i]/c[n+1+i] = exp(x[i] - x[n+1+i])
        G = np.zeros([2*(n+1), n+1])
        G[n+1, 0] = -1.0
        G[2*n+1, 0] = 1.0
        delta = yu - results['Amin'][0:n]
        for i in range(n):
            G[i, i+1] = delta[i]
            G[n+1+i, i+1] = -delta[i]

        return np.concatenate([fu, yu]), multi_dot([G.T, Theta, G])
