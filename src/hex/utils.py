
def first(iterable, default=None):
    try:
        return next(iter(iterable))
    except StopIteration:
        return default

