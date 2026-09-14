"""Ridge solver with an unpenalized intercept and a bounded dual path.

Uses centered normal equations and pivoted elimination. When the feature width
exceeds the number of rows, the algebraically equivalent dual system solves an
``n x n`` matrix and then reconstructs the feature weights. This keeps real
bounded connectome partitions from allocating a width-by-width matrix; large
or ill-conditioned experiments should still use a validated QR/SVD library
solver.
"""

import math


def fit_ridge(features, targets, l2):
    n = len(features)
    width = len(features[0]) if n else 0
    if not n or not width or len(targets) != n or l2 < 0 or not math.isfinite(l2):
        raise ValueError("invalid ridge dimensions or regularization")
    if any(len(row) != width for row in features):
        raise ValueError("feature widths must match")
    if not all(math.isfinite(x) for row in features for x in row) or not all(math.isfinite(y) for y in targets):
        raise ValueError("ridge inputs must be finite")
    means = [sum(row[j] for row in features) / n for j in range(width)]
    target_mean = sum(targets) / n
    centered = [[row[j] - means[j] for j in range(width)] for row in features]
    centered_targets = [y - target_mean for y in targets]
    if width > n:
        gram = [
            [
                sum(centered[i][j] * centered[k][j] for j in range(width))
                + (l2 if i == k else 0.0)
                for k in range(n)
            ]
            + [sum(centered[i][j] * centered_targets[i] for j in range(width))]
            for i in range(n)
        ]
        dual_weights = _solve(gram)
        weights = tuple(
            sum(centered[i][j] * dual_weights[i] for i in range(n))
            for j in range(width)
        )
    else:
        matrix = [
            [
                sum(row[j] * row[k] for row in centered) + (l2 if j == k else 0.0)
                for k in range(width)
            ]
            + [sum(row[j] * target for row, target in zip(centered, centered_targets))]
            for j in range(width)
        ]
        weights = _solve(matrix)
    intercept = target_mean - sum(w * mean for w, mean in zip(weights, means))
    if not all(math.isfinite(x) for x in (*weights, intercept)):
        raise ValueError("ridge solution is non-finite")
    return weights, intercept


def _solve(matrix: list[list[float]]) -> tuple[float, ...]:
    """Solve a square augmented system with pivoted Gauss-Jordan elimination."""

    width = len(matrix)
    if width == 0 or any(len(row) != width + 1 for row in matrix):
        raise ValueError("ridge system dimensions are invalid")
    for col in range(width):
        pivot = max(range(col, width), key=lambda i: abs(matrix[i][col]))
        if abs(matrix[pivot][col]) < 1e-12:
            raise ValueError("singular ridge system; use positive regularization or a rank-aware solver")
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        scale = matrix[col][col]
        matrix[col] = [value / scale for value in matrix[col]]
        for row in range(width):
            if row == col:
                continue
            scale = matrix[row][col]
            matrix[row] = [a - scale * b for a, b in zip(matrix[row], matrix[col])]
    return tuple(row[-1] for row in matrix)
