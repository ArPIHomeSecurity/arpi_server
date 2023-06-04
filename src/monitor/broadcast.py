
class Broadcaster(object):
    """Send message to registered queues."""

    def __init__(self):
        self._queues = {}

    def register_queue(self, client_id, queue):
        """Register queues to broadcast messages"""
        self._queues[client_id] = queue

    def send_message(self, message, sender_id=None):
        """Broadcast message"""
        for client_id, queue in self._queues.items():
            if client_id != sender_id:
                queue.put(message)
