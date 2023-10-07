# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:04:38
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:04:39
import copy


def merge_dicts(target, source):
    if source is None:
        return
    if target is None:
        target = source
        return

    for k, v in source.items():
        if type(v) == list:
            if k not in target:
                target[k] = copy.deepcopy(v)
            else:
                target[k].extend(v)
        elif type(v) == dict:
            if k not in target:
                target[k] = copy.deepcopy(v)
            else:
                merge_dicts(target[k], v)
        elif type(v) == set:
            if k not in target:
                target[k] = v.copy()
            else:
                target[k].update(v.copy())
        else:
            target[k] = copy.copy(v)


def filter_keys(data, keys=[]):
    """
    Exclude keys from dictionary recursively.
    """
    # filter key
    for filter_key in keys:
        if filter_key in data:
            del data[filter_key]

    # filter sub dictionaries
    for _, value in data.items():
        if type(value) == dict:
            filter_keys(value, keys)


def replace_keys(data, replacers={}):
    """
    Replace keys in dictionary recursively.
    """
    # filter key
    for filter_key in replacers.keys():
        if filter_key in data:
            if replacers["replace_empty"] or not replacers["replace_empty"] and data[filter_key] != "":
                data[filter_key] = replacers[filter_key]

    # filter sub dictionaries
    for _, value in data.items():
        if type(value) == dict:
            replace_keys(value, replacers)

