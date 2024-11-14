import os
import time
from functools import wraps


def file_lock(filename, timeout=3600):
    """
    Decorator to lock a function using a file semaphore.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            file_path = os.path.join("/tmp", filename)
            file_created = False
            try:
                # Check if the file exists and its age
                if os.path.exists(file_path):
                    file_age = time.time() - os.path.getmtime(file_path)
                    if file_age <= timeout:
                        # Lock file exists and is within the timeout period,
                        # do not execute the function
                        return None
                    else:
                        os.remove(file_path)

                # Create the file if it doesn't exist
                open(file_path, "w", encoding="utf-8").close()
                file_created = True

                # Call the wrapped function
                result = func(*args, **kwargs)
            finally:
                # Delete the file after the function call if it was created in this execution
                if file_created and os.path.exists(file_path):
                    os.remove(file_path)

            return result

        return wrapper

    return decorator
