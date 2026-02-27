from fastmcp import FastMCP

from monitor.database import get_database_session
from server.services.card import CardService

card_mcp = FastMCP("ArPI - card service")


session = get_database_session()

@card_mcp.resource(
    uri="cards://user/{user_id}",
    name="user_cards",
    description="Retrieve all existing cards or cards for a specific user when user_id is provided",
    mime_type="application/json",
)
def get_cards(user_id=None):
    """
    Retrieve all or user-specific cards from the database.
    Args:
        user_id: Optional user ID to filter cards by owner
    """
    card_service = CardService(session)
    return [card.serialized for card in card_service.get_cards(user_id=user_id)]
