"""
Registry for config options.
"""

registry = set()


def register_config_option(config_option_class):
    """
    Register a config option class in the registry.

    Args:
        config_option_class: The config option class to register
    """
    registry.add(config_option_class)


def get_registered_config_names():
    """
    Get the names of all registered config options.

    Returns:
        A list of all registered config option names
    """
    return [config_class.OPTION_NAME for config_class in registry]


def get_registered_config_sections():
    """
    Get the sections of all registered config options.

    Returns:
        A list of all registered config option sections
    """
    return [config_class.SECTION_NAME for config_class in registry]
