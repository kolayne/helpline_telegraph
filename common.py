def does_raise(func, *, args=None, kwargs=None, expected=None, reraise_other=True):
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}
    if expected is None:
        expected = Exception

    try:
        func(*args, **kwargs)
        return False
    except expected:
        return True
    except Exception:
        if reraise_other:
            raise
        else:
            return False
