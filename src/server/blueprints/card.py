from flask import jsonify, request
from flask.blueprints import Blueprint

from server.database import db
from server.decorators import authenticated, restrict_host
from server.services.card import CardService
from utils.constants import ROLE_ADMIN, ROLE_USER
from utils.models import Card, User

card_blueprint = Blueprint("card", __name__)


@card_blueprint.route("/api/cards", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_cards():
    card_service = CardService(db.session)

    return jsonify(
        [card.serialized for card in card_service.get_cards(request.args.get("userId"))]
    )


@card_blueprint.route("/api/card/<int:card_id>", methods=["GET", "PUT", "DELETE"])
@authenticated(role=ROLE_USER)
@restrict_host
def manage_card(card_id, request_user_id):
    card = db.session.query(Card).get(card_id)
    if not card:
        return jsonify({"error": "Card not found"}), 404

    user = db.session.query(User).get(request_user_id)
    if card.user_id != request_user_id and user.role != ROLE_ADMIN:
        return jsonify({"error": "Not authorized"}), 403

    if request.method == "GET":
        return jsonify(card.serialized)

    if request.method == "PUT":
        if not card.update(request.json):
            return "", 204

        db.session.commit()
        return jsonify(card.serialized)

    if request.method == "DELETE":
        db.session.delete(card)
        db.session.commit()
        return jsonify(None)

    return jsonify({"error": "Unknown action"}), 405
