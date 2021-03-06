# pylint: disable=E1101,E1103,W0232

from datetime import time
from itertools import izip

import numpy as np

from pandas.core.common import (adjoin as _adjoin, _stringify,
                                _is_bool_indexer, _asarray_tuplesafe)
from pandas.util.decorators import cache_readonly
import pandas._tseries as lib

__all__ = ['Index']

def _indexOp(opname):
    """
    Wrapper function for Series arithmetic operations, to avoid
    code duplication.
    """
    def wrapper(self, other):
        func = getattr(self.view(np.ndarray), opname)
        return func(other)
    return wrapper


class Index(np.ndarray):
    """
    Immutable ndarray implementing an ordered, sliceable set. The basic object
    storing axis labels for all pandas objects

    Parameters
    ----------
    data : array-like (1-dimensional)
    dtype : NumPy dtype (default: object)
    copy : bool
        Make a copy of input ndarray

    Note
    ----
    An Index instance can **only** contain hashable objects
    """
    _map_indices = lib.map_indices_object
    _is_monotonic = lib.is_monotonic_object
    _groupby = lib.groupby_object
    _arrmap = lib.arrmap_object

    name = None
    def __new__(cls, data, dtype=None, copy=False, name=None):
        if isinstance(data, np.ndarray):
            if dtype is None and issubclass(data.dtype.type, np.integer):
                return Int64Index(data, copy=copy, name=name)
            subarr = np.array(data, dtype=object, copy=copy)
        elif np.isscalar(data):
            raise ValueError('Index(...) must be called with a collection '
                             'of some kind, %s was passed' % repr(data))
        else:
            # other iterable of some kind
            subarr = _asarray_tuplesafe(data, dtype=object)

        subarr = subarr.view(cls)
        subarr.name = name
        return subarr

    def __array_finalize__(self, obj):
        self.name = getattr(obj, 'name', None)

    @property
    def dtype(self):
        return self.values.dtype

    @property
    def nlevels(self):
        return 1

    @property
    def _constructor(self):
        return Index

    def summary(self):
        if len(self) > 0:
            index_summary = ', %s to %s' % (str(self[0]), str(self[-1]))
        else:
            index_summary = ''

        name = type(self).__name__
        return '%s: %s entries%s' % (name, len(self), index_summary)

    @property
    def values(self):
        return np.asarray(self)

    @cache_readonly
    def is_monotonic(self):
        return self._is_monotonic(self)

    _indexMap = None
    _integrity = False

    @property
    def indexMap(self):
        "{label -> location}"
        if self._indexMap is None:
            self._indexMap = self._map_indices(self)
            self._integrity = len(self._indexMap) == len(self)

        if not self._integrity:
            raise Exception('Index cannot contain duplicate values!')
        return self._indexMap

    def _get_level_number(self, level):
        if not isinstance(level, int):
            assert(level == self.name)
            level = 0
        return level

    def _verify_integrity(self):
        if self._indexMap is None:
            try:
                self.indexMap
            except Exception:
                return False
        return len(self.indexMap) == len(self)

    def _get_duplicates(self):
        from collections import defaultdict
        counter = defaultdict(lambda: 0)
        for k in self.values:
            counter[k] += 1
        return sorted(k for k, v in counter.iteritems() if v > 1)

    _allDates = None
    def is_all_dates(self):
        """
        Checks that all the labels are datetime objects
        """
        if self._allDates is None:
            self._allDates = lib.isAllDates(self)

        return self._allDates

    def __iter__(self):
        return iter(self.view(np.ndarray))

    def __setstate__(self, state):
        """Necessary for making this object picklable"""
        np.ndarray.__setstate__(self, state)

    def __deepcopy__(self, memo={}):
        """
        Index is not mutable, so disabling deepcopy
        """
        return self

    def __contains__(self, key):
        return key in self.indexMap

    def __hash__(self):
        return hash(self.view(np.ndarray))

    def __setitem__(self, key, value):
        """Disable the setting of values."""
        raise Exception(str(self.__class__) + ' object is immutable' )

    def __getitem__(self, key):
        """Override numpy.ndarray's __getitem__ method to work as desired"""
        arr_idx = self.view(np.ndarray)
        if np.isscalar(key):
            return arr_idx[key]
        else:
            if _is_bool_indexer(key):
                key = np.asarray(key)

            return Index(arr_idx[key], name=self.name)

    def append(self, other):
        """
        Append a collection of Index options together

        Parameters
        ----------
        other : Index or list/tuple of indices

        Returns
        -------
        appended : Index
        """
        if isinstance(other, (list, tuple)):
            to_concat = (self.values,) + tuple(other)
        else:
            to_concat = self.values, other.values
        return Index(np.concatenate(to_concat))

    def take(self, *args, **kwargs):
        """
        Analogous to ndarray.take
        """
        taken = self.view(np.ndarray).take(*args, **kwargs)
        return self._constructor(taken, name=self.name)

    def format(self, name=False):
        """
        Render a string representation of the Index
        """
        result = []

        if name:
            result.append(self.name if self.name is not None else '')

        if self.is_all_dates():
            zero_time = time(0, 0)
            for dt in self:
                if dt.time() != zero_time or dt.tzinfo is not None:
                    return ['%s' % x for x in self]
                result.append(dt.strftime("%Y-%m-%d"))
            return result

        result.extend(_stringify(x) for x in self)

        return result

    def equals(self, other):
        """
        Determines if two Index objects contain the same elements.
        """
        if self is other:
            return True

        if not isinstance(other, Index):
            return False

        if type(other) != Index:
            return other.equals(self)

        return np.array_equal(self, other)

    def asof(self, label):
        """
        For a sorted index, return the most recent label up to and including
        the passed label. Return NaN if not found
        """
        if label not in self.indexMap:
            loc = self.searchsorted(label, side='left')
            if loc > 0:
                return self[loc-1]
            else:
                return np.nan

        return label

    def sort(self, *args, **kwargs):
        raise Exception('Cannot sort an Index object')

    def shift(self, periods, offset):
        """
        Shift Index containing datetime objects by input number of periods and
        DateOffset

        Returns
        -------
        shifted : Index
        """
        if periods == 0:
            # OK because immutable
            return self

        offset = periods * offset
        return Index([idx + offset for idx in self])

    def argsort(self, *args, **kwargs):
        """
        See docstring for ndarray.argsort
        """
        return self.view(np.ndarray).argsort(*args, **kwargs)

    def __add__(self, other):
        if isinstance(other, Index):
            return self.union(other)
        else:
            return Index(self.view(np.ndarray) + other)

    __eq__ = _indexOp('__eq__')
    __ne__ = _indexOp('__ne__')
    __lt__ = _indexOp('__lt__')
    __gt__ = _indexOp('__gt__')
    __le__ = _indexOp('__le__')
    __ge__ = _indexOp('__ge__')

    def __sub__(self, other):
        return self.diff(other)

    def __and__(self, other):
        return self.intersection(other)

    def __or__(self, other):
        return self.union(other)

    def union(self, other):
        """
        Form the union of two Index objects and sorts if possible

        Parameters
        ----------
        other : Index or array-like

        Returns
        -------
        union : Index
        """
        if not hasattr(other, '__iter__'):
            raise Exception('Input must be iterable!')

        if len(other) == 0 or self.equals(other):
            return self
        if len(self) == 0:
            return _ensure_index(other)

        if self.is_monotonic and other.is_monotonic:
            result = lib.outer_join_indexer_object(self, other.values)[0]
        else:
            indexer = self.get_indexer(other)
            indexer = (indexer == -1).nonzero()[0]

            if len(indexer) > 0:
                other_diff = other.values.take(indexer)
                result = list(self) + list(other_diff)
                # timsort wins
                try:
                    result.sort()
                except Exception:
                    pass
            else:
                # contained in
                result = sorted(self)

        # for subclasses
        return self._wrap_union_result(other, result)

    def _wrap_union_result(self, other, result):
        if type(self) == type(other):
            return type(self)(result)
        else:
            return Index(result)

    def intersection(self, other):
        """
        Form the intersection of two Index objects. Sortedness of the result is
        not guaranteed

        Parameters
        ----------
        other : Index or array-like

        Returns
        -------
        intersection : Index
        """
        if not hasattr(other, '__iter__'):
            raise Exception('Input must be iterable!')

        if self.equals(other):
            return self

        other = _ensure_index(other)

        if other.dtype != np.object_:
            other = other.astype(object)

        if self.is_monotonic and other.is_monotonic:
            return Index(lib.inner_join_indexer_object(self,
                                                       other.values)[0])
        else:
            indexer = self.get_indexer(other.values)
            indexer = indexer.take((indexer != -1).nonzero()[0])
            return self.take(indexer)

    def diff(self, other):
        """
        Compute sorted set difference of two Index objects

        Notes
        -----
        One can do either of these and achieve the same result

        >>> index - index2
        >>> index.diff(index2)

        Returns
        -------
        diff : Index
        """

        if not hasattr(other, '__iter__'):
            raise Exception('Input must be iterable!')

        if self.equals(other):
            return Index([])

        otherArr = np.asarray(other)
        theDiff = sorted(set(self) - set(otherArr))
        return Index(theDiff)

    def get_loc(self, key):
        """
        Get integer location for requested label

        Returns
        -------
        loc : int
        """
        return self.indexMap[key]

    def get_indexer(self, target, method=None):
        """
        Compute indexer and mask for new index given the current index. The
        indexer should be then used as an input to ndarray.take to align the
        current data to the new index. The mask determines whether labels are
        found or not in the current index

        Parameters
        ----------
        target : Index
        method : {'pad', 'ffill', 'backfill', 'bfill'}
            pad / ffill: propagate LAST valid observation forward to next valid
            backfill / bfill: use NEXT valid observation to fill gap

        Notes
        -----
        This is a low-level method and probably should be used at your own risk

        Examples
        --------
        >>> indexer, mask = index.get_indexer(new_index)
        >>> new_values = cur_values.take(indexer)
        >>> new_values[-mask] = np.nan

        Returns
        -------
        (indexer, mask) : (ndarray, ndarray)
        """
        method = self._get_method(method)

        target = _ensure_index(target)

        if self.dtype != target.dtype:
            target = Index(target, dtype=object)

        if method == 'pad':
            indexer = lib.pad_object(self, target, self.indexMap,
                                     target.indexMap)
        elif method == 'backfill':
            indexer = lib.backfill_object(self, target, self.indexMap,
                                          target.indexMap)
        elif method is None:
            indexer = lib.merge_indexer_object(target, self.indexMap)
        else:
            raise ValueError('unrecognized method: %s' % method)
        return indexer

    def groupby(self, to_groupby):
        return self._groupby(self.values, to_groupby)

    def map(self, mapper):
        return self._arrmap(self.values, mapper)

    def _get_method(self, method):
        if method:
            method = method.lower()

        aliases = {
            'ffill' : 'pad',
            'bfill' : 'backfill'
        }
        return aliases.get(method, method)

    def reindex(self, target, method=None):
        """
        For Index, simply returns the new index and the results of
        get_indexer. Provided here to enable an interface that is amenable for
        subclasses of Index whose internals are different (like MultiIndex)

        Returns
        -------
        (new_index, indexer, mask) : tuple
        """
        indexer = self.get_indexer(target, method=method)
        return target, indexer

    def join(self, other, how='left', return_indexers=False):
        if self.is_monotonic and other.is_monotonic:
            return self._join_monotonic(other, how=how,
                                        return_indexers=return_indexers)

        if how == 'left':
            join_index = self
        elif how == 'right':
            join_index = other
        elif how == 'inner':
            join_index = self.intersection(other)
        elif how == 'outer':
            join_index = self.union(other)
        else:
            raise Exception('do not recognize join method %s' % how)

        if return_indexers:
            if join_index is self:
                lindexer = None
            else:
                lindexer = self.get_indexer(join_index)
            if join_index is other:
                rindexer = None
            else:
                rindexer = other.get_indexer(join_index)
            return join_index, lindexer, rindexer
        else:
            return join_index

    def _join_monotonic(self, other, how='left', return_indexers=False):
        if how == 'left':
            join_index = self
            lidx = None
            ridx = lib.left_join_indexer_object(self, other)
        elif how == 'right':
            join_index = other
            lidx = lib.left_join_indexer_object(other, self)
            ridx = None
        elif how == 'inner':
            join_index, lidx, ridx = lib.inner_join_indexer_object(self, other)
            join_index = Index(join_index)
        elif how == 'outer':
            join_index, lidx, ridx = lib.outer_join_indexer_object(self, other)
            join_index = Index(join_index)
        else:  # pragma: no cover
            raise Exception('do not recognize join method %s' % how)

        if return_indexers:
            return join_index, lidx, ridx
        else:
            return join_index

    def slice_locs(self, start=None, end=None):
        """
        For an ordered Index, compute the slice locations for input labels

        Parameters
        ----------
        start : label, default None
            If None, defaults to the beginning
        end : label
            If None, defaults to the end

        Returns
        -------
        (begin, end) : (int, int)

        Notes
        -----
        This function assumes that the data is sorted, so use at your own peril
        """
        if start is None:
            beg_slice = 0
        elif start in self:
            beg_slice = self.indexMap[start]
        else:
            beg_slice = self.searchsorted(start, side='left')

        if end is None:
            end_slice = len(self)
        elif end in self.indexMap:
            end_slice = self.indexMap[end] + 1
        else:
            end_slice = self.searchsorted(end, side='right')

        return beg_slice, end_slice

    def delete(self, loc):
        """
        Make new Index with passed location deleted

        Returns
        -------
        new_index : Index
        """
        arr = np.delete(np.asarray(self), loc)
        return Index(arr)

    def insert(self, loc, item):
        """
        Make new Index inserting new item at location

        Parameters
        ----------
        loc : int
        item : object

        Returns
        -------
        new_index : Index
        """
        index = np.asarray(self)
        # because numpy is fussy with tuples
        item_idx = Index([item])
        new_index = np.concatenate((index[:loc], item_idx, index[loc:]))
        return Index(new_index)

    def drop(self, labels):
        """
        Make new Index with passed list of labels deleted

        Parameters
        ----------
        labels : array-like

        Returns
        -------
        dropped : Index
        """
        labels = np.asarray(list(labels), dtype=object)
        indexer = self.get_indexer(labels)
        mask = indexer == -1
        if mask.any():
            raise ValueError('labels %s not contained in axis' % labels[mask])
        return self.delete(indexer)

    def copy(self, order='C'):
        """
        Overridden ndarray.copy to copy over attributes
        """
        cp = self.view(np.ndarray).copy(order).view(type(self))
        cp.__dict__.update(self.__dict__)
        return cp


class Int64Index(Index):

    _map_indices = lib.map_indices_int64
    _is_monotonic = lib.is_monotonic_int64
    _groupby = lib.groupby_int64
    _arrmap = lib.arrmap_int64

    def __new__(cls, data, dtype=None, copy=False, name=None):
        if not isinstance(data, np.ndarray):
            if np.isscalar(data):
                raise ValueError('Index(...) must be called with a collection '
                                 'of some kind, %s was passed' % repr(data))

            # other iterable of some kind
            if not isinstance(data, (list, tuple)):
                data = list(data)
            data= np.asarray(data)

        if issubclass(data.dtype.type, basestring):
            raise TypeError('String dtype not supported, you may need '
                            'to explicitly cast to int')
        elif issubclass(data.dtype.type, np.integer):
            subarr = np.array(data, dtype=np.int64, copy=copy)
        else:
            subarr = np.array(data, dtype=np.int64, copy=copy)
            if len(data) > 0:
                if (subarr != data).any():
                    raise TypeError('Unsafe NumPy casting, you must explicitly '
                                    'cast')

        subarr = subarr.view(cls)
        subarr.name = name
        return subarr

    @property
    def _constructor(self):
        return Int64Index

    def astype(self, dtype):
        return Index(self.values.astype(dtype))

    @property
    def dtype(self):
        return np.dtype('int64')

    def is_all_dates(self):
        """
        Checks that all the labels are datetime objects
        """
        return False

    def equals(self, other):
        """
        Determines if two Index objects contain the same elements.
        """
        if self is other:
            return True

        # if not isinstance(other, Int64Index):
        #     return False

        return np.array_equal(self, other)

    def get_indexer(self, target, method=None):
        target = _ensure_index(target)

        if self.dtype != target.dtype:
            this = Index(self, dtype=object)
            target = Index(target, dtype=object)
            return this.get_indexer(target, method=method)

        method = self._get_method(method)

        if method == 'pad':
            indexer = lib.pad_int64(self, target, self.indexMap,
                                    target.indexMap)
        elif method == 'backfill':
            indexer = lib.backfill_int64(self, target, self.indexMap,
                                         target.indexMap)
        elif method is None:
            indexer = lib.merge_indexer_int64(target, self.indexMap)
        else:  # pragma: no cover
            raise ValueError('unrecognized method: %s' % method)
        return indexer
    get_indexer.__doc__ = Index.get_indexer.__doc__

    def join(self, other, how='left', return_indexers=False):
        if not isinstance(other, Int64Index):
            return Index.join(self.astype(object), other, how=how,
                              return_indexers=return_indexers)

        if self.is_monotonic and other.is_monotonic:
            return self._join_monotonic(other, how=how,
                                        return_indexers=return_indexers)
        else:
            return Index.join(self, other, how=how,
                              return_indexers=return_indexers)

    def _join_monotonic(self, other, how='left', return_indexers=False):
        if how == 'left':
            join_index = self
            lidx = None
            ridx = lib.left_join_indexer_int64(self, other)
        elif how == 'right':
            join_index = other
            lidx = lib.left_join_indexer_int64(other, self)
            ridx = None
        elif how == 'inner':
            join_index, lidx, ridx = lib.inner_join_indexer_int64(self, other)
            join_index = Int64Index(join_index)
        elif how == 'outer':
            join_index, lidx, ridx = lib.outer_join_indexer_int64(self, other)
            join_index = Int64Index(join_index)
        else:  # pragma: no cover
            raise Exception('do not recognize join method %s' % how)

        if return_indexers:
            return join_index, lidx, ridx
        else:
            return join_index

    def intersection(self, other):
        if not isinstance(other, Int64Index):
            return Index.intersection(self.astype(object), other)

        if self.is_monotonic and other.is_monotonic:
            result = lib.inner_join_indexer_int64(self, other)[0]
        else:
            indexer = self.get_indexer(other)
            indexer = indexer.take((indexer != -1).nonzero()[0])
            return self.take(indexer)
        return Int64Index(result)
    intersection.__doc__ = Index.intersection.__doc__

    def union(self, other):
        if not isinstance(other, Int64Index):
            return Index.union(self.astype(object), other)

        if self.is_monotonic and other.is_monotonic:
            result = lib.outer_join_indexer_int64(self, other)[0]
        else:
            result = np.unique(np.concatenate((self, other)))
        return Int64Index(result)
    union.__doc__ = Index.union.__doc__

class DateIndex(Index):
    pass


class Factor(np.ndarray):
    """
    Represents a categorical variable in classic R / S-plus fashion

    Parameters
    ----------
    data : array-like

    Returns
    -------
    **Attributes**
      * labels : ndarray
      * levels : ndarray
    """
    def __new__(cls, data):
        data = np.asarray(data, dtype=object)
        levels, factor = unique_with_labels(data)
        factor = factor.view(Factor)
        factor.levels = levels
        return factor

    levels = None

    def __array_finalize__(self, obj):
        self.levels = getattr(obj, 'levels', None)

    @property
    def labels(self):
        return self.view(np.ndarray)

    def asarray(self):
        return np.asarray(self.levels).take(self.labels)

    def __len__(self):
        return len(self.labels)

    def __repr__(self):
        temp = 'Factor:\n%s\nLevels (%d): %s'
        values = self.asarray()
        return temp % (repr(values), len(self.levels), self.levels)

    def __getitem__(self, key):
        if isinstance(key, (int, np.integer)):
            i = self.labels[key]
            return self.levels[i]
        else:
            return np.ndarray.__getitem__(self, key)

def unique_with_labels(values):
    uniques = Index(lib.fast_unique(values))
    labels = lib.get_unique_labels(values, uniques.indexMap)
    return uniques, labels

class MultiIndex(Index):
    """
    Implements multi-level, a.k.a. hierarchical, index object for pandas objects

    Parameters
    ----------
    levels : list or tuple of arrays
        The unique labels for each level
    labels : list or tuple of arrays
        Integers for each level designating which label at each location
    """
    def __new__(cls, levels=None, labels=None, sortorder=None, names=None):
        assert(len(levels) == len(labels))
        if len(levels) == 0:
            raise Exception('Must pass non-zero number of levels/labels')

        if len(levels) == 1:
            if names:
                name = names[0]
            else:
                name = None

            return Index(levels[0], name=name).take(labels[0])

        return np.arange(len(labels[0]), dtype=object).view(cls)

    def __init__(self, levels, labels, sortorder=None, names=None,
                 consistent=None):
        self.levels = [_ensure_index(lev) for lev in levels]
        self.labels = [np.asarray(labs, dtype=np.int32) for labs in labels]

        if names is None:
            self.names = [None] * self.nlevels
        else:
            assert(len(names) == self.nlevels)
            self.names = list(names)

        # set the name
        for i, name in enumerate(self.names):
            self.levels[i].name = name

        if sortorder is not None:
            self.sortorder = int(sortorder)
        else:
            self.sortorder = sortorder

    @property
    def dtype(self):
        return np.dtype('O')

    def __iter__(self):
        values = [np.asarray(lev).take(lab)
                  for lev, lab in zip(self.levels, self.labels)]
        return izip(*values)

    def _get_level_number(self, level):
        if not isinstance(level, int):
            count = self.names.count(level)
            if count > 1:
                raise Exception('The name %s occurs multiple times, use a '
                                'level number' % level)

            level = self.names.index(level)
        elif level < 0:
            level += self.nlevels
        return level

    @property
    def values(self):
        result = np.empty(len(self), dtype=object)
        result[:] = list(self)
        return result

    def get_level_values(self, level):
        """
        Return vector of label values for requested level, equal to the length
        of the index

        Parameters
        ----------
        level : int

        Returns
        -------
        values : ndarray
        """
        unique_vals = self.levels[level].values
        labels = self.labels[level]
        return unique_vals.take(labels)

    def __contains__(self, key):
        try:
            label_key = self._get_label_key(key)
            return label_key in self.indexMap
        except Exception:
            return False

    def format(self, space=2, sparsify=True, adjoin=True, names=False):
        if len(self) == 0:
            return []

        stringified_levels = [lev.format() for lev in self.levels]

        result_levels = []
        for lab, lev, name in zip(self.labels, stringified_levels, self.names):
            level = []

            if names:
                level.append(name if name is not None else '')

            level.extend(np.array(lev, dtype=object).take(lab))
            result_levels.append(level)

        if sparsify:
            result_levels = _sparsify(result_levels)

        if adjoin:
            return _adjoin(space, *result_levels).split('\n')
        else:
            return result_levels

    def is_all_dates(self):
        return False

    def is_lexsorted(self):
        """
        Return True if the labels are lexicographically sorted
        """
        return self.lexsort_depth == self.nlevels

    @cache_readonly
    def lexsort_depth(self):
        if self.sortorder is not None:
            if self.sortorder == 0:
                return self.nlevels
            else:
                return 0

        for k in range(self.nlevels, 0, -1):
            if lib.is_lexsorted(self.labels[:k]):
                return k

        return 0

    @classmethod
    def from_arrays(cls, arrays, sortorder=None, names=None):
        """
        Convert arrays to MultiIndex

        Parameters
        ----------
        arrays : list / sequence
        sortorder : int or None
            Level of sortedness (must be lexicographically sorted by that level)

        Returns
        -------
        index : MultiIndex
        """
        levels = []
        labels = []
        for arr in arrays:
            factor = Factor(arr)
            levels.append(factor.levels)
            labels.append(factor.labels)

        return MultiIndex(levels=levels, labels=labels, sortorder=sortorder,
                          names=names)

    @classmethod
    def from_tuples(cls, tuples, sortorder=None, names=None):
        """
        Convert list of tuples to MultiIndex

        Parameters
        ----------
        tuples : array-like
        sortorder : int or None
            Level of sortedness (must be lexicographically sorted by that level)

        Returns
        -------
        index : MultiIndex
        """
        if len(tuples) == 0:
            raise Exception('Cannot infer number of levels from empty list')
        arrays = zip(*tuples)
        return MultiIndex.from_arrays(arrays, sortorder=sortorder,
                                      names=names)

    @property
    def indexMap(self):
        if self._indexMap is None:
            zipped = zip(*self.labels)
            self._indexMap = lib.map_indices_list(zipped)
            self._integrity = len(self._indexMap) == len(self)

        if not self._integrity:
            raise Exception('Index cannot contain duplicate values!')

        return self._indexMap

    @property
    def nlevels(self):
        return len(self.levels)

    @property
    def levshape(self):
        return tuple(len(x) for x in self.levels)

    def __reduce__(self):
        """Necessary for making this object picklable"""
        object_state = list(np.ndarray.__reduce__(self))
        subclass_state = (self.levels, self.labels, self.sortorder, self.names)
        object_state[2] = (object_state[2], subclass_state)
        return tuple(object_state)

    def __setstate__(self, state):
        """Necessary for making this object picklable"""
        nd_state, own_state = state
        np.ndarray.__setstate__(self, nd_state)
        levels, labels, sortorder, names = own_state

        self.levels = [Index(x) for x in levels]
        self.labels = labels
        self.names = names
        self.sortorder = sortorder

    def __getitem__(self, key):
        arr_idx = self.view(np.ndarray)
        if np.isscalar(key):
            return tuple(lev[lab[key]]
                         for lev, lab in zip(self.levels, self.labels))
        else:
            if _is_bool_indexer(key):
                key = np.asarray(key)
                sortorder = self.sortorder
            else:
                # cannot be sure whether the result will be sorted
                sortorder = None

            new_tuples = arr_idx[key]
            new_labels = [lab[key] for lab in self.labels]

            # an optimization
            result = new_tuples.view(MultiIndex)
            result.levels = self.levels
            result.labels = new_labels
            result.sortorder = sortorder
            result.names = self.names

            return result

    def take(self, *args, **kwargs):
        """
        Analogous to ndarray.take
        """
        new_labels = [lab.take(*args, **kwargs) for lab in self.labels]
        return MultiIndex(levels=self.levels, labels=new_labels,
                          names=self.names)

    def append(self, other):
        """
        Append a collection of Index options together

        Parameters
        ----------
        other : Index or list/tuple of indices

        Returns
        -------
        appended : Index
        """
        if isinstance(other, (list, tuple)):
            for k in other:
                assert(isinstance(k, MultiIndex))

            to_concat = (self.values,) + tuple(k.values for k in other)
        else:
            to_concat = self.values, other.values
        new_tuples = np.concatenate(to_concat)
        return MultiIndex.from_tuples(new_tuples, names=self.names)

    def argsort(self, *args, **kwargs):
        return self.get_tuple_index().argsort()

    def drop(self, labels):
        """
        Make new MultiIndex with passed list of labels deleted

        Parameters
        ----------
        labels : array-like
            Must be a list of tuples

        Returns
        -------
        dropped : MultiIndex
        """
        try:
            if not isinstance(labels, np.ndarray):
                labels = _asarray_tuplesafe(labels)
            indexer = self.get_indexer(labels)
            mask = indexer == -1
            if mask.any():
                raise ValueError('labels %s not contained in axis'
                                 % labels[mask])
            return self.delete(indexer)
        except Exception:
            pass

        inds = []
        for label in labels:
            loc = self.get_loc(label)
            if isinstance(loc, int):
                inds.append(loc)
            else:
                inds.extend(range(loc.start, loc.stop))

        return self.delete(inds)

    def droplevel(self, level=0):
        """
        Return Index with requested level removed. If MultiIndex has only 2
        levels, the result will be of Index type not MultiIndex.

        Parameters
        ----------
        level : int

        Notes
        -----
        Does not check if result index is unique or not

        Returns
        -------
        index : Index or MultiIndex
        """
        new_levels = list(self.levels)
        new_levels.pop(level)
        new_labels = list(self.labels)
        new_labels.pop(level)

        if len(new_levels) == 1:
            return new_levels[0].take(new_labels[0])
        else:
            return MultiIndex(levels=new_levels, labels=new_labels)

    def swaplevel(self, i, j):
        """
        Swap level i with level j. Do not change the ordering of anything

        Returns
        -------
        swapped : MultiIndex
        """
        new_levels = list(self.levels)
        new_labels = list(self.labels)
        new_names = list(self.names)

        new_levels[i], new_levels[j] = new_levels[j], new_levels[i]
        new_labels[i], new_labels[j] = new_labels[j], new_labels[i]
        new_names[i], new_names[j] = new_names[j], new_names[i]

        return MultiIndex(levels=new_levels, labels=new_labels,
                          names=new_names)

    def __getslice__(self, i, j):
        return self.__getitem__(slice(i, j))

    def sortlevel(self, level=0, ascending=True):
        """
        Sort MultiIndex lexicographically by requested level

        Parameters
        ----------
        level : int or str, default 0
            If a string is given, must be a name of the level
        ascending : boolean, default True
            False to sort in descending order

        Returns
        -------
        sorted_index : MultiIndex
        """
        labels = list(self.labels)
        level = self._get_level_number(level)
        primary = labels.pop(level)

        # Lexsort starts from END
        indexer = np.lexsort(tuple(labels[::-1]) + (primary,))

        if not ascending:
            indexer = indexer[::-1]

        new_labels = [lab.take(indexer) for lab in self.labels]
        new_index = MultiIndex(levels=self.levels, labels=new_labels,
                               names=self.names, sortorder=level)

        return new_index, indexer

    def get_indexer(self, target, method=None):
        """
        Compute indexer and mask for new index given the current index. The
        indexer should be then used as an input to ndarray.take to align the
        current data to the new index. The mask determines whether labels are
        found or not in the current index

        Parameters
        ----------
        target : MultiIndex or Index (of tuples)
        method : {'pad', 'ffill', 'backfill', 'bfill'}
            pad / ffill: propagate LAST valid observation forward to next valid
            backfill / bfill: use NEXT valid observation to fill gap

        Notes
        -----
        This is a low-level method and probably should be used at your own risk

        Examples
        --------
        >>> indexer, mask = index.get_indexer(new_index)
        >>> new_values = cur_values.take(indexer)
        >>> new_values[-mask] = np.nan

        Returns
        -------
        (indexer, mask) : (ndarray, ndarray)
        """
        method = self._get_method(method)

        target_index = target
        if isinstance(target, MultiIndex):
            target_index = target.get_tuple_index()

        self_index = self.get_tuple_index()

        if method == 'pad':
            indexer = lib.pad_object(self_index, target_index,
                                     self_index.indexMap, target.indexMap)
        elif method == 'backfill':
            indexer = lib.backfill_object(self_index, target_index,
                                          self_index.indexMap, target.indexMap)
        else:
            indexer = lib.merge_indexer_object(target_index,
                                               self_index.indexMap)

        return indexer

    def reindex(self, target, method=None):
        """
        Performs any necessary conversion on the input index and calls
        get_indexer. This method is here so MultiIndex and an Index of
        like-labeled tuples can play nice together

        Returns
        -------
        (new_index, indexer, mask) : (MultiIndex, ndarray, ndarray)
        """
        indexer = self.get_indexer(target, method=method)

        # hopefully?
        if not isinstance(target, MultiIndex):
            target = MultiIndex.from_tuples(target)

        return target, indexer

    def get_tuple_index(self):
        """
        Convert MultiIndex to an Index of tuples

        Returns
        -------
        index : Index
        """
        return Index(list(self))

    def slice_locs(self, start=None, end=None):
        """
        For an ordered MultiIndex, compute the slice locations for input
        labels. They can tuples representing partial levels, e.g. for a
        MultiIndex with 3 levels, you can pass a single value (corresponding to
        the first level), or a 1-, 2-, or 3-tuple.

        Parameters
        ----------
        start : label or tuple, default None
            If None, defaults to the beginning
        end : label or tuple
            If None, defaults to the end

        Returns
        -------
        (begin, end) : (int, int)

        Notes
        -----
        This function assumes that the data is sorted by the first level
        """
        if start is None:
            start_slice = 0
        else:
            if not isinstance(start, tuple):
                start = start,
            start_slice = self._partial_tup_index(start, side='left')

        if end is None:
            end_slice = len(self)
        else:
            if not isinstance(end, tuple):
                end = end,
            end_slice = self._partial_tup_index(end, side='right')

        return start_slice, end_slice

    def _partial_tup_index(self, tup, side='left'):
        if len(tup) > self.lexsort_depth:
            raise Exception('MultiIndex lexsort depth %d, key was length %d' %
                            (self.lexsort_depth, len(tup)))

        n = len(tup)
        start, end = 0, len(self)
        zipped = izip(tup, self.levels, self.labels)
        for k, (lab, lev, labs) in enumerate(zipped):
            section = labs[start:end]

            if lab not in lev:
                # short circuit
                loc = lev.searchsorted(lab, side=side)
                if side == 'right' and loc > 0:
                    loc -= 1
                return start + section.searchsorted(loc, side=side)

            idx = lev.get_loc(lab)
            if k < n - 1:
                end = start + section.searchsorted(idx, side='right')
                start = start + section.searchsorted(idx, side='left')
            else:
                return start + section.searchsorted(idx, side=side)

    def get_loc(self, key):
        """
        Get integer location slice for requested label or tuple

        Parameters
        ----------
        key : label or tuple

        Returns
        -------
        loc : int or slice object
        """
        if isinstance(key, tuple):
            if len(key) == self.nlevels:
                return self._get_tuple_loc(key)
            else:
                result = slice(*self.slice_locs(key, key))
                if result.start == result.stop:
                    raise KeyError(key)
                return result
        else:
            level = self.levels[0]
            labels = self.labels[0]
            loc = level.get_loc(key)

            if self.lexsort_depth == 0:
                return labels == loc
            else:
                # sorted, so can return slice object -> view
                i = labels.searchsorted(loc, side='left')
                j = labels.searchsorted(loc, side='right')
                return slice(i, j)

    def _get_tuple_loc(self, tup):
        indexer = self._get_label_key(tup)
        try:
            return self.indexMap[indexer]
        except KeyError:
            raise KeyError(str(tup))

    def _get_label_key(self, tup):
        return tuple(lev.get_loc(v) for lev, v in zip(self.levels, tup))

    def truncate(self, before=None, after=None):
        """
        Slice index between two labels / tuples, return new MultiIndex

        Parameters
        ----------
        before : label or tuple, can be partial. Default None
            None defaults to start
        after : label or tuple, can be partial. Default None
            None defaults to end

        Returns
        -------
        truncated : MultiIndex
        """
        if after and before and after < before:
            raise ValueError('after < before')

        i, j = self.levels[0].slice_locs(before, after)
        left, right = self.slice_locs(before, after)

        new_levels = list(self.levels)
        new_levels[0] = new_levels[0][i:j]

        new_labels = [lab[left:right] for lab in self.labels]
        new_labels[0] = new_labels[0] - i

        return MultiIndex(levels=new_levels, labels=new_labels)

    def equals(self, other):
        """
        Determines if two MultiIndex objects have the same labeling information
        (the levels themselves do not necessarily have to be the same)

        See also
        --------
        equal_levels
        """
        if self is other:
            return True

        if not isinstance(other, MultiIndex):
            return False

        if self.nlevels != other.nlevels:
            return False

        if len(self) != len(other):
            return False

        for i in xrange(self.nlevels):
            svalues = np.asarray(self.levels[i]).take(self.labels[i])
            ovalues = np.asarray(other.levels[i]).take(other.labels[i])
            if not np.array_equal(svalues, ovalues):
                return False

        return True

    def equal_levels(self, other):
        """
        Return True if the levels of both MultiIndex objects are the same

        """
        if self.nlevels != other.nlevels:
            return False

        for i in xrange(self.nlevels):
            if not self.levels[i].equals(other.levels[i]):
                return False
        return True

    def union(self, other):
        """
        Form the union of two MultiIndex objects, sorting if possible

        Parameters
        ----------
        other : MultiIndex or array / Index of tuples

        Returns
        -------
        Index
        """
        self._assert_can_do_setop(other)

        if len(other) == 0 or self.equals(other):
            return self

        result_names = self.names if self.names == other.names else None

        self_tuples = self.get_tuple_index()
        other_tuples = other.get_tuple_index()

        uniq_tuples = lib.fast_unique_multiple([self_tuples, other_tuples])
        return MultiIndex.from_arrays(zip(*uniq_tuples), sortorder=0,
                                      names=result_names)

    def intersection(self, other):
        """
        Form the intersection of two MultiIndex objects, sorting if possible

        Parameters
        ----------
        other : MultiIndex or array / Index of tuples

        Returns
        -------
        Index
        """
        self._assert_can_do_setop(other)

        if self.equals(other):
            return self

        result_names = self.names if self.names == other.names else None

        self_tuples = self.get_tuple_index()
        other_tuples = other.get_tuple_index()
        uniq_tuples = sorted(set(self_tuples) & set(other_tuples))
        if len(uniq_tuples) == 0:
            return MultiIndex(levels=[[]]*self.nlevels,
                              labels=[[]]*self.nlevels,
                              names=result_names)
        else:
            return MultiIndex.from_arrays(zip(*uniq_tuples), sortorder=0,
                                          names=result_names)

    def diff(self, other):
        """
        Compute sorted set difference of two MultiIndex objects

        Returns
        -------
        diff : MultiIndex
        """
        self._assert_can_do_setop(other)

        result_names = self.names if self.names == other.names else None

        if self.equals(other):
            return MultiIndex(levels=[[]]*self.nlevels,
                              labels=[[]]*self.nlevels,
                              names=result_names)

        difference = sorted(set(self.values) - set(other.values))

        if len(difference) == 0:
            return MultiIndex(levels=[[]]*self.nlevels,
                              labels=[[]]*self.nlevels,
                              names=result_names)
        else:
            return MultiIndex.from_tuples(difference, sortorder=0,
                                          names=result_names)

    def _assert_can_do_setop(self, other):
        if not isinstance(other, MultiIndex):
            raise TypeError('can only call with other hierarchical '
                            'index objects')

        assert(self.nlevels == other.nlevels)

    def insert(self, loc, item):
        """
        Make new MultiIndex inserting new item at location

        Parameters
        ----------
        loc : int
        item : tuple
            Must be same length as number of levels in the MultiIndex

        Returns
        -------
        new_index : Index
        """
        if not isinstance(item, tuple) or len(item) != self.nlevels:
            raise Exception("%s cannot be inserted in this MultIndex"
                            % str(item))

        new_levels = []
        new_labels = []
        for k, level, labels in zip(item, self.levels, self.labels):
            if k not in level:
                # have to insert into level
                # must insert at end otherwise you have to recompute all the
                # other labels
                lev_loc = len(level)
                level = level.insert(lev_loc, k)
            else:
                lev_loc = level.get_loc(k)

            new_levels.append(level)
            new_labels.append(np.insert(labels, loc, lev_loc))

        return MultiIndex(levels=new_levels, labels=new_labels)

    def delete(self, loc):
        """
        Make new index with passed location deleted

        Returns
        -------
        new_index : MultiIndex
        """
        new_labels = [np.delete(lab, loc) for lab in self.labels]
        return MultiIndex(levels=self.levels, labels=new_labels)

    get_major_bounds = slice_locs

    __bounds = None
    @property
    def _bounds(self):
        """
        Return or compute and return slice points for level 0, assuming
        sortedness
        """
        if self.__bounds is None:
            inds = np.arange(len(self.levels[0]))
            self.__bounds = self.labels[0].searchsorted(inds)

        return self.__bounds

# For utility purposes

NULL_INDEX = Index([])

def _sparsify(label_list):
    pivoted = zip(*label_list)
    k = len(label_list)

    result = [pivoted[0]]
    prev = pivoted[0]

    for cur in pivoted[1:]:
        sparse_cur = []

        for i, (p, t) in enumerate(zip(prev, cur)):
            if i == k - 1:
                sparse_cur.append(t)
                result.append(sparse_cur)
                break

            if p == t:
                sparse_cur.append('')
            else:
                result.append(cur)
                break

        prev = cur

    return zip(*result)

def _ensure_index(index_like):
    if isinstance(index_like, Index):
        return index_like
    return Index(index_like)
