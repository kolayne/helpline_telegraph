from typing import Callable, Optional, List, Dict, Union


def does_raise(func: Callable, *, args: Optional[List] = None, kwargs: Optional[Dict] = None,
               expected: Optional[Union[type, List[type]]] = None, reraise_other: bool = True) -> bool:
    """
    Checks if the call `func(*args, **kwargs)` raises the expected exception

    :param func: Object to be called
    :param args: (default `None`) Positional arguments to call `func` with. If `None`, an empty tuple (`()`) is used
    :param kwargs: (default `None`) Keyword arguments to call `func` with. If `None`, an empty dict (`{}`) is used
    :param expected: (default `None`) The exception type call to `func` is expected to raise
        (or a list of exception types). If `None`, `Exception` is used
    :param reraise_other: (default `True`) whether or not to raise exceptions (not instances of `expected`) if they
        occur
    :return: `True` if the expected exception occurred, `False` otherwise
    :raise: Not expected exceptions occurred during the call, unless `reraise_other` is `False`
    """
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
