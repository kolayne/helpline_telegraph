import json
from datetime import datetime, timedelta

from typing import Dict, Any, Optional


# Callback data dict keys are converted to UPPERCASE abbreviations; values are converted to lowercase
callback_data_contractions = {'type': 'T',
                              'operator_ids': 'OIS', 'conversation_end_moment': 'CEM', 'mood': 'M',
                              'conversation_rate': 'cr', 'better': 'b', 'same': 's', 'worse': 'w',
                              'client_id': 'CID', 'conversation_acceptation': 'ca'}


def contract_callback_data(d: Dict[Any, Any], converter: Optional[Dict[Any, Any]] = None) -> Dict[Any, Any]:
    """
    Accepts a callback data dictionary and replaces its keys and values with their aliases from `converter`

    For each `x` which is a key or a value of `d`, if `x in converter.keys()`, `x` is replaced with `converter[x]` in
    the resulting dictionary, otherwise it remains unchanged

    :param d: Callback data to be contracted
    :param converter: (default `None`) Dictionary with replacements (keys of `converter` found in `d` are replaced with
        the corresponding values). If `None`, `callback_data_contractions` global variable is used
    :return: `d` dictionary with keys and values contracted with `converter`
    """
    if converter is None:
        converter = callback_data_contractions

    e = {}
    for key, value_ in d.items():
        try:
            value = converter.get(value_, value_)
        except TypeError:  # If `value_` is not hashable, it can't be a key of `converter`
            value = value_

        e[converter.get(key, key)] = value

    return e

def contract_callback_data_and_jdump(d: Dict[Any, Any], converter: Optional[Dict[Any, Any]] = None) -> str:
    """
    Calls `contract_callback_data` with the given arguments and `json.dumps` the result

    :param d: Callback data to be contracted with `contract_callback_data`
    :param converter: Converter to be used in `contract_callback_data`
    :return: Dictionary returned by `contract_callback_data` and dumped with json (`json.dumps` is called with an extra
        argument `separators=(',', ':')`)
    """
    return json.dumps(contract_callback_data(d, converter), separators=(',', ':'))

def decontract_callback_data(d: Dict[Any, Any], converter: Optional[Dict[Any, Any]] = None) -> Dict[Any, Any]:
    """
    The synonym for `contract_callback_data` with an exception that the `converter` parameter defaults to the reversed
    `callback_data_contractions` dictionary, not to the original one

    :param d: Callback data to be decontracted
    :param converter: (default `None`) Dictionary with replacements to be forwarded to `contract_callback_data`. If
        `None`, the <b>reversed</b> `callback_data_contractions` is used
    :return: `d` dictionary with keys and values decontracted with `converter`
    """
    if converter is None:
        # Use inverted `callback_data_contractions` by default
        converter = {v: k for k, v in callback_data_contractions.items()}
    return contract_callback_data(d, converter)

def jload_and_decontract_callback_data(d: str, converter: Optional[Dict[Any, Any]] = None) -> Dict[Any, Any]:
    """
    The synonym for `decontract_callback_data(json.loads(d), converter)`

    :param d: Callback data to be decontracted
    :param converter: (default `None`) Dictionary with replacements to be forwarded to `decontract_callback_data`.
        If `None`, the value is forwarded as is (`decontract_callback_data(<...>, None)` is called)
    :return: `d` dictionary with keys and values decontracted with `converter`
    """
    return decontract_callback_data(json.loads(d), converter)


# Used to reduce number of digits in the `total_seconds` sent as a callback
local_epoch = datetime(2020, 11, 1)

def seconds_since_local_epoch(dt):
    return int((dt - local_epoch).total_seconds())

def datetime_from_local_epoch_secs(secs):
    return local_epoch + timedelta(seconds=secs)
