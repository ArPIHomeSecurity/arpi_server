"""
Card service module to handle card-related operations.
"""

from server.services.base import BaseService
from utils.models import Card


class CardService(BaseService):
    """
    Service for RFID card management operations.
    """

    def get_cards(self, user_id=None):
        """
        Get all cards or cards for a specific user.

        Args:
            user_id: Optional user ID to filter cards by owner

        Returns:
            List of Card objects

        """
        query = self._db_session.query(Card)

        if user_id is not None:
            query = query.filter(Card.user_id == user_id)

        return query.order_by(Card.description).all()
