import logging


class NotTooLongStringFormatter(logging.Formatter):
    """
    Formatter for truncating the message if it is too long.
    """

    def __init__(self, format_string, fields, max_length=10):
        super(NotTooLongStringFormatter, self).__init__(format_string)
        self._max_length = max_length
        self._fields = fields

    def format(self, record):
        for field in self._fields:
            value = getattr(record, field)
            if len(value) > self._max_length:
                setattr(record, field, value[:self._max_length])
            return super().format(record)
