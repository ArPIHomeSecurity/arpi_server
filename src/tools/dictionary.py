"""
Dictionary tools.
"""
import copy


def merge_dicts(target, source):
    """
    Merge two dictionaries recursively.
    """
    if source is None:
        return
    if target is None:
        target = source
        return

    for k, v in source.items():
        if isinstance(v, list):
            if k not in target:
                target[k] = copy.deepcopy(v)
            else:
                target[k].extend(v)
        elif isinstance(v, dict):
            if k not in target:
                target[k] = copy.deepcopy(v)
            else:
                merge_dicts(target[k], v)
        elif isinstance(v, set):
            if k not in target:
                target[k] = v.copy()
            else:
                target[k].update(v.copy())
        else:
            target[k] = copy.copy(v)


def filter_keys(data, keys=None):
    """
    Exclude keys from dictionary recursively.
    """
    if keys is None:
        return

    # filter key
    for filter_key in keys:
        if filter_key in data:
            del data[filter_key]

    # filter sub dictionaries
    for _, value in data.items():
        if isinstance(value, dict):
            filter_keys(value, keys)


def replace_keys(data, replacers=None):
    """
    Replace keys in dictionary recursively.
    """
    if replacers is None:
        return

    # filter key
    for filter_key in replacers.keys():
        if filter_key in data:
            if (
                replacers["replace_empty"]
                or not replacers["replace_empty"]
                and data[filter_key] not in [None, ""]
            ):
                data[filter_key] = replacers[filter_key]

    # filter sub dictionaries
    for _, value in data.items():
        if isinstance(value, dict):
            replace_keys(value, replacers)
