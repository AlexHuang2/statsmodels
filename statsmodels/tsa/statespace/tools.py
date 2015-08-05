"""
Statespace Tools

Author: Chad Fulton
License: Simplified-BSD
"""
from __future__ import division, absolute_import, print_function

import numpy as np
from statsmodels.tools.data import _is_using_pandas
from . import _statespace

old_scipy_compat = False
try:
    from scipy.linalg.blas import find_best_blas_type
except ImportError:  # pragma: no cover
    old_scipy_compat = True
    # Shim for SciPy 0.11, derived from tag=0.11 scipy.linalg.blas
    _type_conv = {'f': 's', 'd': 'd', 'F': 'c', 'D': 'z', 'G': 'z'}

    def find_best_blas_type(arrays):
        dtype, index = max(
            [(ar.dtype, i) for i, ar in enumerate(arrays)])
        prefix = _type_conv.get(dtype.char, 'd')
        return prefix, dtype, None


prefix_dtype_map = {
    's': np.float32, 'd': np.float64, 'c': np.complex64, 'z': np.complex128
}
prefix_statespace_map = {
    's': _statespace.sStatespace, 'd': _statespace.dStatespace,
    'c': _statespace.cStatespace, 'z': _statespace.zStatespace
}
prefix_kalman_filter_map = {
    's': _statespace.sKalmanFilter, 'd': _statespace.dKalmanFilter,
    'c': _statespace.cKalmanFilter, 'z': _statespace.zKalmanFilter
}
prefix_pacf_map = {
    's': _statespace._scompute_coefficients_from_multivariate_pacf,
    'd': _statespace._dcompute_coefficients_from_multivariate_pacf,
    'c': _statespace._ccompute_coefficients_from_multivariate_pacf,
    'z': _statespace._zcompute_coefficients_from_multivariate_pacf
}
prefix_sv_map = {
    's': _statespace._sconstrain_sv_less_than_one,
    'd': _statespace._dconstrain_sv_less_than_one,
    'c': _statespace._cconstrain_sv_less_than_one,
    'z': _statespace._zconstrain_sv_less_than_one
}


def companion_matrix(polynomial):
    r"""
    Create a companion matrix

    Parameters
    ----------
    polynomial : array_like or list
        If an iterable, interpreted as the coefficients of the polynomial from
        which to form the companion matrix. Polynomial coefficients are in
        order of increasing degree, and may be either scalars (as in an AR(p)
        model) or coefficient matrices (as in a VAR(p) model). If an integer,
        it is interpereted as the size of a companion matrix of a scalar
        polynomial, where the polynomial coefficients are initialized to zeros.
        If a matrix polynomial is passed, :math:`C_0` may be set to the scalar
        value 1 to indicate an identity matrix (doing so will improve the speed
        of the companion matrix creation).

    Returns
    -------
    companion_matrix : array

    Notes
    -----
    Given coefficients of a lag polynomial of the form:

    .. math::
        c(L) = c_0 + c_1 L + \dots + c_p L^p

    returns a matrix of the form

    .. math::
        \begin{bmatrix}
            \phi_1 & 1      & 0 & \cdots & 0 \\
            \phi_2 & 0      & 1 &        & 0 \\
            \vdots &        &   & \ddots & 0 \\
                   &        &   &        & 1 \\
            \phi_n & 0      & 0 & \cdots & 0 \\
        \end{bmatrix}

    where some or all of the :math:`\phi_i` may be non-zero (if `polynomial` is
    None, then all are equal to zero).

    If the coefficients provided are scalars :math:`(c_0, c_1, \dots, c_p)`,
    then the companion matrix is an :math:`n \times n` matrix formed with the
    elements in the first column defined as
    :math:`\phi_i = -\frac{c_i}{c_0}, i \in 1, \dots, p`.

    If the coefficients provided are matrices :math:`(C_0, C_1, \dots, C_p)`,
    each of shape :math:`(m, m)`, then the companion matrix is an
    :math:`nm \times nm` matrix formed with the elements in the first column
    defined as :math:`\phi_i = -C_0^{-1} C_i', i \in 1, \dots, p`.

    It is important to understand the expected signs of the coefficients. A
    typical AR(p) model is written as:

    .. math::
        y_t = a_1 y_{t-1} + \dots + a_p y_{t-p} + \varepsilon_t

    This can be rewritten as:

    .. math::
        (1 - a_1 L - \dots - a_p L^p )y_t = \varepsilon_t \\
        (1 + c_1 L + \dots + c_p L^p )y_t = \varepsilon_t \\
        c(L) y_t = \varepsilon_t

    The coefficients from this form are defined to be :math:`c_i = - a_i`, and
    it is the :math:`c_i` coefficients that this function expects to be
    provided.

    """
    identity_matrix = False
    if isinstance(polynomial, int):
        n = polynomial
        m = 1
        polynomial = None
    else:
        n = len(polynomial) - 1

        if n < 1:
            raise ValueError("Companion matrix polynomials must include at"
                             " least two terms.")

        if isinstance(polynomial, list) or isinstance(polynomial, tuple):
            try:
                # Note: can't use polynomial[0] because of the special behavior
                # associated with matrix polynomials and the constant 1, see
                # below.
                m = len(polynomial[1])
            except TypeError:
                m = 1

            # Check if we just have a scalar polynomial
            if m == 1:
                polynomial = np.asanyarray(polynomial)
            # Check if 1 was passed as the first argument (indicating an
            # identity matrix)
            elif polynomial[0] == 1:
                polynomial[0] = np.eye(m)
                identity_matrix = True
        else:
            m = 1
            polynomial = np.asanyarray(polynomial)

    matrix = np.zeros((n * m, n * m))
    idx = np.diag_indices((n - 1) * m)
    idx = (idx[0], idx[1] + m)
    matrix[idx] = 1
    if polynomial is not None and n > 0:
        if m == 1:
            matrix[:, 0] = -polynomial[1:] / polynomial[0]
        elif identity_matrix:
            for i in range(n):
                matrix[i * m:(i + 1) * m, :m] = -polynomial[i+1].T
        else:
            inv = np.linalg.inv(polynomial[0])
            for i in range(n):
                matrix[i * m:(i + 1) * m, :m] = -np.dot(inv, polynomial[i+1]).T
    return matrix


def diff(series, k_diff=1, k_seasonal_diff=None, k_seasons=1):
    r"""
    Difference a series simply and/or seasonally along the zero-th axis.

    Given a series (denoted :math:`y_t`), performs the differencing operation

    .. math::

        \Delta^d \Delta_s^D y_t

    where :math:`d =` `diff`, :math:`s =` `k_seasons`,
    :math:`D =` `seasonal\_diff`, and :math:`\Delta` is the difference
    operator.

    Parameters
    ----------
    series : array_like
        The series to be differenced.
    diff : int, optional
        The number of simple differences to perform. Default is 1.
    seasonal_diff : int or None, optional
        The number of seasonal differences to perform. Default is no seasonal
        differencing.
    k_seasons : int, optional
        The seasonal lag. Default is 1. Unused if there is no seasonal
        differencing.

    Returns
    -------
    differenced : array
        The differenced array.
    """
    pandas = _is_using_pandas(series, None)
    differenced = np.asanyarray(series) if not pandas else series

    # Seasonal differencing
    if k_seasonal_diff is not None:
        while k_seasonal_diff > 0:
            if not pandas:
                differenced = (
                    differenced[k_seasons:] - differenced[:-k_seasons]
                )
            else:
                differenced = differenced.diff(k_seasons)[k_seasons:]
            k_seasonal_diff -= 1

    # Simple differencing
    if not pandas:
        differenced = np.diff(differenced, k_diff, axis=0)
    else:
        while k_diff > 0:
            differenced = differenced.diff()[1:]
            k_diff -= 1
    return differenced


def is_invertible(polynomial, threshold=1.):
    r"""
    Determine if a polynomial is invertible.

    Requires all roots of the polynomial lie inside the unit circle.

    Parameters
    ----------
    polynomial : array_like or tuple, list
        Coefficients of a polynomial, in order of increasing degree.
        For example, `polynomial=[1, -0.5]` corresponds to the polynomial
        :math:`1 - 0.5x` which has root :math:`2`. If it is a matrix
        polynomial (in which case the coefficients are coefficient matrices),
        a tuple or list of matrices should be passed.
    threshold : number
        Allowed threshold for `is_invertible` to return True. Default is 1.

    Notes
    -----

    If the coefficients provided are scalars :math:`(c_0, c_1, \dots, c_n)`,
    then the corresponding polynomial is :math:`c_0 + c_1 L + \dots + c_n L^n`.


    If the coefficients provided are matrices :math:`(C_0, C_1, \dots, C_n)`,
    then the corresponding polynomial is :math:`C_0 + C_1 L + \dots + C_n L^n`.

    There are three equivalent methods of determining if the polynomial
    represented by the coefficients is invertible:

    The first method factorizes the polynomial into:

    .. math::

        C(L) & = c_0 + c_1 L + \dots + c_n L^n \\
             & = constant (1 - \lambda_1 L)
                 (1 - \lambda_2 L) \dots (1 - \lambda_n L)

    In order for :math:`C(L)` to be invertible, it must be that each factor
    :math:`(1 - \lambda_i L)` is invertible; the condition is then that
    :math:`|\lambda_i| < 1`, where :math:`\lambda_i` is a root of the
    polynomial.

    The second method factorizes the polynomial into:

    .. math::

        C(L) & = c_0 + c_1 L + \dots + c_n L^n \\
             & = constant (L - \zeta_1) (L - \zeta_2) \dots (L - \zeta_3)

    The condition is now :math:`|\zeta_i| > 1`, where :math:`\zeta_i` is a root
    of the polynomial with reversed coefficients and
    :math:`\lambda_i = \frac{1}{\zeta_i}`.

    Finally, a companion matrix can be formed using the coefficients of the
    polynomial. Then the eigenvalues of that matrix give the roots of the
    polynomial. This last method is the one actually used.

    See Also
    --------
    companion_matrix
    """
    # First method:
    # np.all(np.abs(np.roots(np.r_[1, params])) < 1)
    # Second method:
    # np.all(np.abs(np.roots(np.r_[1, params][::-1])) > 1)
    # Final method:
    eigvals = np.linalg.eigvals(companion_matrix(polynomial))
    return np.all(np.abs(eigvals) < threshold)


def constrain_stationary_univariate(unconstrained):
    """
    Transform unconstrained parameters used by the optimizer to constrained
    parameters used in likelihood evaluation

    Parameters
    ----------
    unconstrained : array
        Unconstrained parameters used by the optimizer, to be transformed to
        stationary coefficients of, e.g., an autoregressive or moving average
        component.

    Returns
    -------
    constrained : array
        Constrained parameters of, e.g., an autoregressive or moving average
        component, to be transformed to arbitrary parameters used by the
        optimizer.

    References
    ----------

    Monahan, John F. 1984.
    "A Note on Enforcing Stationarity in
    Autoregressive-moving Average Models."
    Biometrika 71 (2) (August 1): 403-404.
    """

    n = unconstrained.shape[0]
    y = np.zeros((n, n), dtype=unconstrained.dtype)
    r = unconstrained/((1 + unconstrained**2)**0.5)
    for k in range(n):
        for i in range(k):
            y[k, i] = y[k - 1, i] + r[k] * y[k - 1, k - i - 1]
        y[k, k] = r[k]
    return -y[n - 1, :]


def unconstrain_stationary_univariate(constrained):
    """
    Transform constrained parameters used in likelihood evaluation
    to unconstrained parameters used by the optimizer

    Parameters
    ----------
    constrained : array
        Constrained parameters of, e.g., an autoregressive or moving average
        component, to be transformed to arbitrary parameters used by the
        optimizer.

    Returns
    -------
    unconstrained : array
        Unconstrained parameters used by the optimizer, to be transformed to
        stationary coefficients of, e.g., an autoregressive or moving average
        component.

    References
    ----------

    Monahan, John F. 1984.
    "A Note on Enforcing Stationarity in
    Autoregressive-moving Average Models."
    Biometrika 71 (2) (August 1): 403-404.
    """
    n = constrained.shape[0]
    y = np.zeros((n, n), dtype=constrained.dtype)
    y[n-1:] = -constrained
    for k in range(n-1, 0, -1):
        for i in range(k):
            y[k-1, i] = (y[k, i] - y[k, k]*y[k, k-i-1]) / (1 - y[k, k]**2)
    r = y.diagonal()
    x = r / ((1 - r**2)**0.5)
    return x


def _constrain_sv_less_than_one_python(unconstrained, order=None,
                                       k_endog=None):
    """
    Transform arbitrary matrices to matrices with singular values less than
    one.

    Corresponds to Lemma 2.2 in Ansley and Kohn (1986). See
    `constrain_stationary_multivariate` for more details.
    """
    from scipy import linalg

    constrained = []  # P_s,  s = 1, ..., p
    if order is None:
        order = len(unconstrained)
    if k_endog is None:
        k_endog = unconstrained[0].shape[0]

    eye = np.eye(k_endog)
    for i in range(order):
        A = unconstrained[i]
        B, lower = linalg.cho_factor(eye + np.dot(A, A.T), lower=True)
        constrained.append(linalg.solve_triangular(B, A, lower=lower))
    return constrained


def _compute_coefficients_from_multivariate_pacf_python(
    partial_autocorrelations, error_variance, order, k_endog,
    transform_variance=False):
    """
    Transform matrices with singular values less than one to matrices
    corresponding to a stationary (or invertible) process.

    Corresponds to Lemma 2.1 in Ansley and Kohn (1986). See
    `constrain_stationary_multivariate` for more details.
    """
    from scipy import linalg

    partial_autocorrelations = np.concatenate(partial_autocorrelations, axis=1)

    # If we want to keep the provided variance but with the constrained
    # coefficient matrices, we need to make a copy here, and then after the
    # main loop we will transform the coefficients to match the passed variance
    if not transform_variance:
        initial_variance = error_variance
        # Need to make the input variance large enough that the recursions
        # don't lead to zero-matrices due to roundoff error, which would case
        # exceptions from the Cholesky decompositions.
        # Note that this will still not always ensure positive definiteness,
        # and for k_endog, order large enough an exception may still be raised
        error_variance = np.eye(k_endog) * (order + k_endog)**10

    forward_variance = error_variance   # \Sigma_s
    backward_variance = error_variance  # \Sigma_s^*,  s = 0, ..., p
    autocovariances = np.zeros((k_endog, k_endog * (order+1)))     # \Gamma_s
    autocovariances[:, :k_endog] = error_variance
    # \phi_{s,k}, s = 1, ..., p
    #             k = 1, ..., s+1
    forwards = np.zeros((k_endog, k_endog * order))
    prev_forwards = np.zeros((k_endog, k_endog * order))
    # \phi_{s,k}^*
    backwards = np.zeros((k_endog, k_endog * order))
    prev_backwards = np.zeros((k_endog, k_endog * order))

    error_variance_factor = linalg.cholesky(error_variance, lower=True)

    forward_factors = error_variance_factor
    backward_factors = error_variance_factor

    tmp = np.zeros((k_endog, k_endog))

    # We fill in the entries as follows:
    # [1,1]
    # [2,2], [2,1]
    # [3,3], [3,1], [3,2]
    # ...
    # [p,p], [p,1], ..., [p,p-1]
    # the last row, correctly ordered, is then used as the coefficients
    for s in range(order):  # s = 0, ..., p-1
        prev_forwards = forwards.copy()
        prev_backwards = backwards.copy()

        # Create the "last" (k = s+1) matrix
        # Note: this is for k = s+1. However, below we then have to fill
        # in for k = 1, ..., s in order.
        # P L*^{-1} = x
        # x L* = P
        # L*' x' = P'
        forwards[:, s*k_endog:(s+1)*k_endog] = np.dot(
            forward_factors,
            linalg.solve_triangular(
                backward_factors, partial_autocorrelations[:, s*k_endog:(s+1)*k_endog].T,
                lower=True, trans='T').T
        )

        # P' L^{-1} = x
        # x L = P'
        # L' x' = P
        backwards[:, s*k_endog:(s+1)*k_endog] = np.dot(
            backward_factors,
            linalg.solve_triangular(
                forward_factors, partial_autocorrelations[:, s*k_endog:(s+1)*k_endog],
                lower=True, trans='T').T
        )

        # Update the variance
        # Note: if s >= 1, this will be further updated in the for loop
        # below
        # Also, this calculation will be re-used in the forward variance
        tmp = np.dot(forwards[:, s*k_endog:(s+1)*k_endog], backward_variance)
        autocovariances[:, (s+1)*k_endog:(s+2)*k_endog] = tmp.copy().T

        # Create the remaining k = 1, ..., s matrices,
        # only has an effect if s >= 1
        for k in range(s):
            forwards[:, k*k_endog:(k+1)*k_endog] = (
                prev_forwards[:, k*k_endog:(k+1)*k_endog] -
                np.dot(
                    forwards[:, s*k_endog:(s+1)*k_endog],
                    prev_backwards[:, (s-k-1)*k_endog:(s-k)*k_endog]
                )
            )

            backwards[:, k*k_endog:(k+1)*k_endog] = (
                prev_backwards[:, k*k_endog:(k+1)*k_endog] -
                np.dot(
                    backwards[:, s*k_endog:(s+1)*k_endog],
                    prev_forwards[:, (s-k-1)*k_endog:(s-k)*k_endog]
                )
            )

            autocovariances[:, (s+1)*k_endog:(s+2)*k_endog] += np.dot(
                autocovariances[:, (k+1)*k_endog:(k+2)*k_endog],
                prev_forwards[:, (s-k-1)*k_endog:(s-k)*k_endog].T
            )

        # Create forward and backwards variances
        backward_variance = (
            backward_variance -
            np.dot(
                np.dot(backwards[:, s*k_endog:(s+1)*k_endog], forward_variance),
                backwards[:, s*k_endog:(s+1)*k_endog].T
            )
        )
        forward_variance = (
            forward_variance -
            np.dot(tmp, forwards[:, s*k_endog:(s+1)*k_endog].T)
        )

        # Cholesky factors
        forward_factors = linalg.cholesky(forward_variance, lower=True)
        backward_factors =  linalg.cholesky(backward_variance, lower=True)

    # If we do not want to use the transformed variance, we need to
    # adjust the constrained matrices, as presented in Lemma 2.3, see above
    variance = forward_variance
    if not transform_variance:
        # Here, we need to construct T such that:
        # variance = T * initial_variance * T'
        # To do that, consider the Cholesky of variance (L) and
        # input_variance (M) to get:
        # L L' = T M M' T' = (TM) (TM)'
        # => L = T M
        # => L M^{-1} = T
        initial_variance_factor = np.linalg.cholesky(initial_variance)
        transformed_variance_factor = np.linalg.cholesky(variance)
        transform = np.dot(initial_variance_factor,
                           np.linalg.inv(transformed_variance_factor))
        inv_transform = np.linalg.inv(transform)

        for s in range(order):
            forwards[:, s*k_endog:(s+1)*k_endog] = (
                np.dot(np.dot(transform, forwards[:, s*k_endog:(s+1)*k_endog]), inv_transform)
            )

    return forwards, variance


def _compute_coefficients_from_multivariate_pacf_python2(
    partial_autocorrelations, error_variance, order=None, k_endog=None,
    transform_variance=False):
    """
    Transform matrices with singular values less than one to matrices
    corresponding to a stationary (or invertible) process.

    Corresponds to Lemma 2.1 in Ansley and Kohn (1986). See
    `constrain_stationary_multivariate` for more details.
    """
    from scipy import linalg

    if order is None:
        order = len(partial_autocorrelations)
    if k_endog is None:
        k_endog = partial_autocorrelations[0].shape[0]

    # If we want to keep the provided variance but with the constrained
    # coefficient matrices, we need to make a copy here, and then after the
    # main loop we will transform the coefficients to match the passed variance
    if not transform_variance:
        initial_variance = error_variance
        # Need to make the input variance large enough that the recursions
        # don't lead to zero-matrices due to roundoff error, which would case
        # exceptions from the Cholesky decompositions.
        # Note that this will still not always ensure positive definiteness,
        # and for k_endog, order large enough an exception may still be raised
        error_variance = np.eye(k_endog) * (order + k_endog)**10

    forward_variances = [error_variance]   # \Sigma_s
    backward_variances = [error_variance]  # \Sigma_s^*,  s = 0, ..., p
    autocovariances = [error_variance]     # \Gamma_s
    # \phi_{s,k}, s = 1, ..., p
    #             k = 1, ..., s+1
    forwards = []
    # \phi_{s,k}^*
    backwards = []

    error_variance_factor = linalg.cholesky(error_variance, lower=True)

    forward_factors = [error_variance_factor]
    backward_factors = [error_variance_factor]

    # We fill in the entries as follows:
    # [1,1]
    # [2,2], [2,1]
    # [3,3], [3,1], [3,2]
    # ...
    # [p,p], [p,1], ..., [p,p-1]
    # the last row, correctly ordered, is then used as the coefficients
    for s in range(order):  # s = 0, ..., p-1
        prev_forwards = forwards
        prev_backwards = backwards
        forwards = []
        backwards = []

        # Create the "last" (k = s+1) matrix
        # Note: this is for k = s+1. However, below we then have to fill
        # in for k = 1, ..., s in order.
        # P L*^{-1} = x
        # x L* = P
        # L*' x' = P'
        forwards.append(
            linalg.solve_triangular(
                backward_factors[s], partial_autocorrelations[s].T,
                lower=True, trans='T'))
        forwards[0] = np.dot(forward_factors[s], forwards[0].T)

        # P' L^{-1} = x
        # x L = P'
        # L' x' = P
        backwards.append(
            linalg.solve_triangular(
                forward_factors[s], partial_autocorrelations[s],
                lower=True, trans='T'))
        backwards[0] = np.dot(backward_factors[s], backwards[0].T)

        # Update the variance
        # Note: if s >= 1, this will be further updated in the for loop
        # below
        # Also, this calculation will be re-used in the forward variance
        tmp = np.dot(forwards[0], backward_variances[s])
        autocovariances.append(tmp.copy().T)

        # Create the remaining k = 1, ..., s matrices,
        # only has an effect if s >= 1
        for k in range(s):
            forwards.insert(k, prev_forwards[k] - np.dot(
                forwards[-1], prev_backwards[s-(k+1)]))

            backwards.insert(k, prev_backwards[k] - np.dot(
                backwards[-1], prev_forwards[s-(k+1)]))

            autocovariances[s+1] += np.dot(autocovariances[k+1],
                                           prev_forwards[s-(k+1)].T)

        # Create forward and backwards variances
        forward_variances.append(
            forward_variances[s] - np.dot(tmp, forwards[s].T)
        )
        backward_variances.append(
            backward_variances[s] -
            np.dot(
                np.dot(backwards[s], forward_variances[s]),
                backwards[s].T
            )
        )

        # Cholesky factors
        forward_factors.append(
            linalg.cholesky(forward_variances[s+1], lower=True)
        )
        backward_factors.append(
            linalg.cholesky(backward_variances[s+1], lower=True)
        )

    # If we do not want to use the transformed variance, we need to
    # adjust the constrained matrices, as presented in Lemma 2.3, see above
    variance = forward_variances[-1]
    if not transform_variance:
        # Here, we need to construct T such that:
        # variance = T * initial_variance * T'
        # To do that, consider the Cholesky of variance (L) and
        # input_variance (M) to get:
        # L L' = T M M' T' = (TM) (TM)'
        # => L = T M
        # => L M^{-1} = T
        initial_variance_factor = np.linalg.cholesky(initial_variance)
        transformed_variance_factor = np.linalg.cholesky(variance)
        transform = np.dot(initial_variance_factor,
                           np.linalg.inv(transformed_variance_factor))
        inv_transform = np.linalg.inv(transform)

        for i in range(order):
            forwards[i] = (
                np.dot(np.dot(transform, forwards[i]), inv_transform)
            )

    return forwards, variance


if not old_scipy_compat:

    def constrain_stationary_multivariate(unconstrained, variance,
                                          transform_variance=False,
                                          prefix=None):

        use_list = type(unconstrained) == list
        if use_list:
            unconstrained = np.concatenate(unconstrained, axis=1)
        
        unconstrained = np.asfortranarray(unconstrained)
        variance = np.asfortranarray(variance)

        k_endog, order = unconstrained.shape
        order //= k_endog

        if prefix is None:
            prefix, dtype, _ = find_best_blas_type(
                [unconstrained, variance])

        # Step 1: convert from arbitrary matrices to those with singular values
        # less than one.
        # sv_constrained = _constrain_sv_less_than_one(unconstrained, order,
        #                                              k_endog, prefix)
        sv_constrained = prefix_sv_map[prefix](unconstrained, order, k_endog)

        # Step 2: convert matrices from our "partial autocorrelation matrix" space
        # (matrices with singular values less than one) to the space of stationary
        # coefficient matrices
        constrained, variance = prefix_pacf_map[prefix](
            sv_constrained, variance, order, k_endog, transform_variance)

        constrained = np.array(constrained)
        variance = np.array(variance)

        if use_list:
            constrained = [
                constrained[:k_endog, i*k_endog:(i+1)*k_endog]
                for i in range(order)
            ]

        return constrained, variance

else:
    _compute_coefficients_from_multivariate_pacf = (
        _compute_coefficients_from_multivariate_pacf_python)
    _constrain_sv_less_than_one = _constrain_sv_less_than_one_python
    constrain_stationary_multivariate = constrain_stationary_multivariate_python


def constrain_stationary_multivariate_python(unconstrained, variance,
                                             transform_variance=False,
                                             prefix=None):
    """
    Transform unconstrained parameters used by the optimizer to constrained
    parameters used in likelihood evaluation for a vector autoregression.

    Parameters
    ----------
    unconstrained : iterable
        Arbitrary matrices to be transformed to stationary coefficient matrices
        of the VAR.
    variance : array, 2-dim
        Variance matrix corresponding to the error term. This is used as
        input in the algorithm even if is not transformed by it (when
        `transform_variance` is False. The error term variance is required
        input when transformation is used either to force an autoregressive
        component to be stationary or to force  a moving average component to
        be invertible.
    transform_variance : boolean, optional
        Whether or not to transform the error variance term. This option is
        not typically used, and the default is False.

    Returns
    -------
    constrained : list
        A list of coefficient matrices which lead to a stationary VAR.

    Notes
    -----
    In the notation of [1]_, the arguments `(variance, unconstrained)` are
    written as :math:`(\Sigma, A_1, \dots, A_p)`, where :math:`p` is the order
    of the vector autoregression, and is here determined by the length of
    the `unconstrained` argument.

    There are two steps in the constraining algorithm.

    First, :math:`(A_1, \dots, A_p)` are transformed into
    :math:`(P_1, \dots, P_p)` via Lemma 2.2 of [1]_.

    Second, :math:`(\Sigma, P_1, \dots, P_p)` are transformed into
    :math:`(\Sigma, \phi_1, \dots, \phi_p)` via Lemmas 2.1 and 2.3 of [1]_.

    If `transform_variance=True`, then only Lemma 2.1 is applied in the second
    step.

    While this function can be used even in the univariate case, it is much
    slower, so in that case `constrain_stationary_univariate` is preferred.

    References
    ----------
    Ansley, Craig F., and Robert Kohn. 1986.
    "A Note on Reparameterizing a Vector Autoregressive Moving Average Model to
    Enforce Stationarity."
    Journal of Statistical Computation and Simulation 24 (2): 99-106.

    """
    from scipy import linalg

    use_list = type(unconstrained) == list
    if not use_list:
        k_endog, order = unconstrained.shape
        order //= k_endog

        unconstrained = [
            unconstrained[:k_endog, i*k_endog:(i+1)*k_endog]
            for i in range(order)
        ]

    order = len(unconstrained)
    k_endog = unconstrained[0].shape[0]

    # Step 1: convert from arbitrary matrices to those with singular values
    # less than one.
    sv_constrained = _constrain_sv_less_than_one(unconstrained, order, k_endog)

    # Step 2: convert matrices from our "partial autocorrelation matrix" space
    # (matrices with singular values less than one) to the space of stationary
    # coefficient matrices
    constrained, variance = _compute_coefficients_from_multivariate_pacf(
        sv_constrained, variance, order, k_endog, transform_variance)

    if not use_list:
        constrained = np.concatenate(constrained, axis=1)

    return constrained, variance


def _unconstrain_sv_less_than_one(constrained, order=None, k_endog=None):
    """
    Transform matrices with singular values less than one to arbitrary
    matrices.

    Corresponds to the inverse of Lemma 2.2 in Ansley and Kohn (1986). See
    `unconstrain_stationary_multivariate` for more details.
    """
    from scipy import linalg

    unconstrained = []  # A_s,  s = 1, ..., p
    if order is None:
        order = len(constrained)
    if k_endog is None:
        k_endog = constrained[0].shape[0]

    eye = np.eye(k_endog)
    for i in range(order):
        P = constrained[i]
        # B^{-1} B^{-1}' = I - P P'
        B_inv, lower = linalg.cho_factor(eye - np.dot(P, P.T), lower=True)
        # A = BP
        # B^{-1} A = P
        unconstrained.append(linalg.solve_triangular(B_inv, P, lower=lower))
    return unconstrained


def _compute_multivariate_acovf_from_coefficients(coefficients, error_variance,
                                                  order=None, k_endog=None,
                                                  maxlag=None):
    """
    Notes
    -----

    Coefficients are assumed to be provided from the VAR model:

    .. math::
        y_t = A_1 y_{t-1} + \dots + A_p y_{t-p} + \varepsilon_t
    """
    from scipy import linalg

    if order is None:
        order = len(coefficients)
    if k_endog is None:
        k_endog = coefficients[0].shape[0]
    if maxlag is None:
        maxlag = order-1

    # Start with VAR(p): w_{t+1} = phi_1 w_t + ... + phi_p w_{t-p+1} + u_{t+1}
    # Then stack the VAR(p) into a VAR(1) in companion matrix form:
    # z_{t+1} = F z_t + v_t
    companion = companion_matrix(
        [1] + [-coefficients[i] for i in range(order)]
    ).T

    # Compute the error variance matrix for the stacked form: E v_t v_t'
    selected_variance = np.zeros(companion.shape)
    selected_variance[:k_endog, :k_endog] = error_variance

    # Compute the unconditional variance of z_t: E z_t z_t'
    stacked_cov = linalg.solve_discrete_lyapunov(companion, selected_variance)

    # The first (block) row of the variance of z_t gives the first p-1
    # autocovariances of w_t: \Gamma_i = E w_t w_t+i with \Gamma_0 = Var(w_t)
    # Note: these are okay, checked against ArmaProcess
    autocovariances = [
        stacked_cov[:k_endog, i*k_endog:(i+1)*k_endog]
        for i in range(min(order, maxlag+1))
    ]

    for i in range(maxlag - (order-1)):
        stacked_cov = np.dot(companion, stacked_cov)
        autocovariances += [
            stacked_cov[:k_endog, -k_endog:]
        ]

    return autocovariances


def _compute_multivariate_pacf_from_coefficients(constrained, error_variance,
                                                order=None, k_endog=None):
    """
    Transform matrices corresponding to a stationary (or invertible) process
    to matrices with singular values less than one.

    Note that this computes multivariate partial autocorrelations.

    Corresponds to the inverse of Lemma 2.1 in Ansley and Kohn (1986). See
    `unconstrain_stationary_multivariate` for more details.

    Notes
    -----

    Coefficients are assumed to be provided from the VAR model:

    .. math::
        y_t = A_1 y_{t-1} + \dots + A_p y_{t-p} + \varepsilon_t
    """
    from scipy import linalg

    if order is None:
        order = len(constrained)
    if k_endog is None:
        k_endog = constrained[0].shape[0]

    # Get autocovariances for the process; these are defined to be
    # E z_t z_{t-j}'
    # However, we want E z_t z_{t+j}' = (E z_t z_{t-j}')'
    _acovf = _compute_multivariate_acovf_from_coefficients
    autocovariances = [autocovariance.T for autocovariance in
        _acovf(constrained, error_variance, order, k_endog, maxlag=order)]

    # Now apply the Ansley and Kohn (1986) algorithm, except that instead of
    # calculating phi_{s+1, s+1} = L_s P_{s+1} {L_s^*}^{-1} (which requires
    # the partial autocorrelation P_{s+1} which is what we're trying to
    # calculate here), we calculate it as in Ansley and Newbold (1979), using
    # the autocovariances \Gamma_s and the forwards and backwards residual
    # variances \Sigma_s, \Sigma_s^*:
    # phi_{s+1, s+1} = [ \Gamma_{s+1}' - \phi_{s,1} \Gamma_s' - ... -
    #                    \phi_{s,s} \Gamma_1' ] {\Sigma_s^*}^{-1}

    # Forward and backward variances
    forward_variances = []   # \Sigma_s
    backward_variances = []  # \Sigma_s^*,  s = 0, ..., p
    # \phi_{s,k}, s = 1, ..., p
    #             k = 1, ..., s+1
    forwards = []
    # \phi_{s,k}^*
    backwards = []

    forward_factors = []   # L_s
    backward_factors = []  # L_s^*,  s = 0, ..., p

    # Ultimately we want to construct the partial autocorrelation matrices
    # Note that this is "1-indexed" in the sense that it stores P_1, ... P_p
    # rather than starting with P_0.
    partial_autocorrelations = []

    # We fill in the entries of phi_{s,k} as follows:
    # [1,1]
    # [2,2], [2,1]
    # [3,3], [3,1], [3,2]
    # ...
    # [p,p], [p,1], ..., [p,p-1]
    # the last row, correctly ordered, should be the same as the coefficient
    # matrices provided in the argument `constrained`
    for s in range(order):  # s = 0, ..., p-1
        prev_forwards = list(forwards)
        prev_backwards = list(backwards)
        forwards = []
        backwards = []

        # Create forward and backwards variances Sigma_s, Sigma*_s
        forward_variance = autocovariances[0].copy()
        backward_variance = autocovariances[0].T.copy()

        for k in range(s):
            forward_variance -= np.dot(prev_forwards[k],
                                       autocovariances[k+1])
            backward_variance -= np.dot(prev_backwards[k],
                                        autocovariances[k+1].T)

        forward_variances.append(forward_variance)
        backward_variances.append(backward_variance)

        # Cholesky factors
        forward_factors.append(
            linalg.cholesky(forward_variances[s], lower=True)
        )
        backward_factors.append(
            linalg.cholesky(backward_variances[s], lower=True)
        )

        if False and s == order-1:
            forwards = constrained
        else:
            # Create the intermediate sum term
            if s == 0:
                # phi_11 = \Gamma_1' \Gamma_0^{-1}
                # phi_11 \Gamma_0 = \Gamma_1'
                # \Gamma_0 phi_11' = \Gamma_1
                forwards.append(linalg.cho_solve(
                    (forward_factors[0], True), autocovariances[1]).T)
                # backwards.append(forwards[-1])
                # phi_11_star = \Gamma_1 \Gamma_0^{-1}
                # phi_11_star \Gamma_0 = \Gamma_1
                # \Gamma_0 phi_11_star' = \Gamma_1'
                backwards.append(linalg.cho_solve(
                    (backward_factors[0], True), autocovariances[1].T).T)
            else:
                # G := \Gamma_{s+1}' -
                #      \phi_{s,1} \Gamma_s' - .. - \phi_{s,s} \Gamma_1'
                tmp_sum = autocovariances[s+1].T.copy()

                for k in range(s):
                    tmp_sum -= np.dot(prev_forwards[k], autocovariances[s-k].T)

                # Create the "last" (k = s+1) matrix
                # Note: this is for k = s+1. However, below we then have to
                # fill in for k = 1, ..., s in order.
                # phi = G Sigma*^{-1}
                # phi Sigma* = G
                # Sigma*' phi' = G'
                # Sigma* phi' = G'
                # (because Sigma* is symmetric)
                forwards.append(linalg.cho_solve(
                    (backward_factors[s], True), tmp_sum.T).T)

                # phi = G' Sigma^{-1}
                # phi Sigma = G'
                # Sigma' phi' = G
                # Sigma phi' = G
                # (because Sigma is symmetric)
                backwards.append(linalg.cho_solve(
                    (forward_factors[s], True), tmp_sum).T)

            # Create the remaining k = 1, ..., s matrices,
            # only has an effect if s >= 1
            for k in range(s):
                forwards.insert(k, prev_forwards[k] - np.dot(
                    forwards[-1], prev_backwards[s-(k+1)]))
                backwards.insert(k, prev_backwards[k] - np.dot(
                    backwards[-1], prev_forwards[s-(k+1)]))

        # Partial autocorrelation matrix: P_{s+1}
        # P = L^{-1} phi L*
        # L P = (phi L*)
        partial_autocorrelations.append(linalg.solve_triangular(
            forward_factors[s], np.dot(forwards[s], backward_factors[s]),
            lower=True))

    return partial_autocorrelations


def unconstrain_stationary_multivariate(constrained, error_variance,
                                        transform_variance=False):
    """
    Transform constrained parameters used in likelihood evaluation
    to unconstrained parameters used by the optimizer

    Parameters
    ----------
    constrained : array
        Constrained parameters of, e.g., an autoregressive or moving average
        component, to be transformed to arbitrary parameters used by the
        optimizer.

    Returns
    -------
    unconstrained : array
        Unconstrained parameters used by the optimizer, to be transformed to
        stationary coefficients of, e.g., an autoregressive or moving average
        component.

    References
    ----------
    Ansley, Craig F., and Robert Kohn. 1986.
    "A Note on Reparameterizing a Vector Autoregressive Moving Average Model to
    Enforce Stationarity."
    Journal of Statistical Computation and Simulation 24 (2): 99-106.

    """
    
    from scipy import linalg

    use_list = type(constrained) == list
    if not use_list:
        k_endog, order = constrained.shape
        order //= k_endog

        constrained = [
            constrained[:k_endog, i*k_endog:(i+1)*k_endog]
            for i in range(order)
        ]

    order = len(constrained)
    k_endog = constrained[0].shape[0]

    # Step 1: convert matrices from the space of stationary
    # coefficient matrices to our "partial autocorrelation matrix" space
    # (matrices with singular values less than one)
    partial_autocorrelations = _compute_multivariate_pacf_from_coefficients(
        constrained, error_variance, order, k_endog)

    # Step 2: convert from arbitrary matrices to those with singular values
    # less than one.
    unconstrained = _unconstrain_sv_less_than_one(partial_autocorrelations, order, k_endog)

    if not use_list:
        unconstrained = np.concatenate(unconstrained, axis=1)

    return unconstrained, error_variance


def validate_matrix_shape(name, shape, nrows, ncols, nobs):
    """
    Validate the shape of a possibly time-varying matrix, or raise an exception

    Parameters
    ----------
    name : str
        The name of the matrix being validated (used in exception messages)
    shape : array_like
        The shape of the matrix to be validated. May be of size 2 or (if
        the matrix is time-varying) 3.
    nrows : int
        The expected number of rows.
    ncols : int
        The expected number of columns.
    nobs : int
        The number of observations (used to validate the last dimension of a
        time-varying matrix)

    Raises
    ------
    ValueError
        If the matrix is not of the desired shape.
    """
    ndim = len(shape)

    # Enforce dimension
    if ndim not in [2, 3]:
        raise ValueError('Invalid value for %s matrix. Requires a'
                         ' 2- or 3-dimensional array, got %d dimensions' %
                         (name, ndim))
    # Enforce the shape of the matrix
    if not shape[0] == nrows:
        raise ValueError('Invalid dimensions for %s matrix: requires %d'
                         ' rows, got %d' % (name, nrows, shape[0]))
    if not shape[1] == ncols:
        raise ValueError('Invalid dimensions for %s matrix: requires %d'
                         ' columns, got %d' % (name, ncols, shape[1]))

    # If we don't yet know `nobs`, don't allow time-varying arrays
    if nobs is None and not (ndim == 2 or shape[-1] == 1):
        raise ValueError('Invalid dimensions for %s matrix: time-varying'
                         ' matrices cannot be given unless `nobs` is specified'
                         ' (implicitly when a dataset is bound or else set'
                         ' explicity)' % name)

    # Enforce time-varying array size
    if ndim == 3 and nobs is not None and not shape[-1] in [1, nobs]:
        raise ValueError('Invalid dimensions for time-varying %s'
                         ' matrix. Requires shape (*,*,%d), got %s' %
                         (name, nobs, str(shape)))


def validate_vector_shape(name, shape, nrows, nobs):
    """
    Validate the shape of a possibly time-varying vector, or raise an exception

    Parameters
    ----------
    name : str
        The name of the vector being validated (used in exception messages)
    shape : array_like
        The shape of the vector to be validated. May be of size 1 or (if
        the vector is time-varying) 2.
    nrows : int
        The expected number of rows (elements of the vector).
    nobs : int
        The number of observations (used to validate the last dimension of a
        time-varying vector)

    Raises
    ------
    ValueError
        If the vector is not of the desired shape.
    """
    ndim = len(shape)
    # Enforce dimension
    if ndim not in [1, 2]:
        raise ValueError('Invalid value for %s vector. Requires a'
                         ' 1- or 2-dimensional array, got %d dimensions' %
                         (name, ndim))
    # Enforce the shape of the vector
    if not shape[0] == nrows:
        raise ValueError('Invalid dimensions for %s vector: requires %d'
                         ' rows, got %d' % (name, nrows, shape[0]))

    # If we don't yet know `nobs`, don't allow time-varying arrays
    if nobs is None and not (ndim == 1 or shape[-1] == 1):
        raise ValueError('Invalid dimensions for %s vector: time-varying'
                         ' vectors cannot be given unless `nobs` is specified'
                         ' (implicitly when a dataset is bound or else set'
                         ' explicity)' % name)

    # Enforce time-varying array size
    if ndim == 2 and not shape[1] in [1, nobs]:
        raise ValueError('Invalid dimensions for time-varying %s'
                         ' vector. Requires shape (*,%d), got %s' %
                         (name, nobs, str(shape)))
