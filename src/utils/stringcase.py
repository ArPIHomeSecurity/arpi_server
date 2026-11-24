import re


def camelcase(string):
    value = re.sub(r"\w[\s\W]+\w", "", str(string))
    if not value:
        return value

    return value[0].lower() + re.sub(
        r"[\-_.\s]([a-z])", lambda match: match.group(1).upper(), value[1:]
    )


def snakecase(string):
    value = re.sub(r"[-.\s]", "_", str(string))
    if not value:
        return value

    return value[0].lower() + re.sub(
        r"[A-Z]", lambda match: "_" + match.group(0).lower(), value[1:]
    )
