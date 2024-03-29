import functools
import pickle, json, csv, os, shutil
from typing import Any, Callable


class PersistentDict(dict):
    ''' Persistent dictionary with an API compatible with shelve and anydbm.

    The dict is kept in memory, so the dictionary operations run as fast as
    a regular dictionary.

    Write to disk is delayed until close or sync (similar to gdbm's fast mode).

    Input file format is automatically discovered.
    Output file format is selectable between pickle, json, and csv.
    All three serialization formats are backed by fast C implementations.

    Source: https://code.activestate.com/recipes/576642/
    '''

    def __init__(self, filename, flag='c', mode=None, format='pickle', *args, **kwds):
        self.flag = flag                    # r=readonly, c=create, or n=new
        self.mode = mode                    # None or an octal triple like 0644
        self.format = format                # 'csv', 'json', or 'pickle'
        self.filename = filename
        if flag != 'n' and os.access(filename, os.R_OK):
            fileobj = open(filename, 'rb' if format=='pickle' else 'r')
            with fileobj:
                self.load(fileobj)
        dict.__init__(self, *args, **kwds)

    def sync(self):
        'Write dict to disk'
        if self.flag == 'r':
            return
        filename = self.filename
        tempname = filename + '.tmp'
        fileobj = open(tempname, 'wb' if self.format=='pickle' else 'w')
        try:
            self.dump(fileobj)
        except Exception:
            os.remove(tempname)
            raise
        finally:
            fileobj.close()
        shutil.move(tempname, self.filename)    # atomic commit
        if self.mode is not None:
            os.chmod(self.filename, self.mode)

    def close(self):
        self.sync()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def dump(self, fileobj):
        if self.format == 'csv':
            csv.writer(fileobj).writerows(self.items())
        elif self.format == 'json':
            json.dump(self, fileobj, separators=(',', ':'))
        elif self.format == 'pickle':
            pickle.dump(dict(self), fileobj, 2)
        else:
            raise NotImplementedError('Unknown format: ' + repr(self.format))

    def load(self, fileobj):
        # try formats from most restrictive to least restrictive
        for loader in (pickle.load, json.load, csv.reader):
            fileobj.seek(0)
            try:
                return self.update(loader(fileobj))
            except Exception:
                pass
        raise ValueError('File not in a supported format')

def _shelve_cache_wrapper(func: Callable, cache_file: str) -> Callable:
    """
    Generates a wrapper that applies the cache to the function.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            # print(f"Loading cache from {cache_file}")
            cache = PersistentDict(cache_file)
        except FileNotFoundError:
            # print(f"Cache file {cache_file} not found, creating new cache")
            cache = PersistentDict(cache_file, flag='n')
        # key = (args, frozenset(kwargs.items()))
        key = (func.__name__, args, frozenset(kwargs.items()))
        # print(cache)
        try:
            return cache[key]
        except KeyError:
            result = func(*args, **kwargs)
            cache[key] = result
            cache.sync()
            return result
    return wrapper

def simple_cache(cache_file: str) -> Callable:
    """
    A decorator that applies a shelve cache to a function.
    """
    def decorator(func: Callable) -> Callable:
        # cache_file = func.__name__ + '.cache'
        return _shelve_cache_wrapper(func, cache_file)
    return decorator

def test_shelve_cache():
    @simple_cache('test.cache')
    def test_func(a, b):
        print('test_func called', a, b)
        return a + b
    assert test_func(1, 2) == 3
    assert test_func(1, 3) == 4
    assert test_func(1, 2) == 3
# test_shelve_cache()
