from pandas import *
from pandas.util.testing import rands

from la import larry

n = 100000
indices = Index([rands(10) for _ in xrange(n)])

def sample(values, k):
    from random import shuffle
    sampler = np.arange(len(values))
    shuffle(sampler)
    return values.take(sampler[:k])

subsample_size = 90000

# x = Series(np.random.randn(100000), indices)
# y = Series(np.random.randn(subsample_size),
#            index=sample(indices, subsample_size))


# lx = larry(np.random.randn(100000), [list(indices)])
# ly = larry(np.random.randn(subsample_size), [list(y.index)])

stamps = np.random.randint(1000000000, 1000000000000, 2000000)

idx1 = np.sort(sample(stamps, 1000000))
idx2 = np.sort(sample(stamps, 1000000))

ts1 = Series(np.random.randn(1000000), idx1)
ts2 = Series(np.random.randn(1000000), idx2)

# Benchmark 1: Two 1-million length time series (int64-based index) with
# randomly chosen timestamps

# Benchmark 2: Join two 5-variate time series DataFrames (outer and inner join)

df1 = DataFrame(np.random.randn(1000000, 5), idx1, columns=range(5))
df2 = DataFrame(np.random.randn(1000000, 5), idx2, columns=range(5, 10))

