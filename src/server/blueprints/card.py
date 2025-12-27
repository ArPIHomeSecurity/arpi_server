from flask import jsonify, request
from flask.blueprints import Blueprint
from flask.helpers import make_response

from utils.constants import ROLE_ADMIN, ROLE_USER

from utils.models import Card, User
from server.database import db
from server.decorators import authenticated, restrict_host

card_blueprint = Blueprint("card", __name__)


@card_blueprint.route("/api/cards", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_cards():
    # if body has userId
    if "userId" in request.args:
        user_id = request.args.get("userId")
        return jsonify(
            [
                i.serialized
                for i in db.session.query(Card)
                .filter(Card.user_id == user_id)
                .order_by(Card.description)
                .all()
            ]
        )
    return jsonify([i.serialized for i in db.session.query(Card).order_by(Card.description).all()])


@card_blueprint.route("/api/card/<int:card_id>", methods=["GET", "PUT", "DELETE"])
@authenticated(role=ROLE_USER)
@restrict_host
def manage_card(card_id, request_user_id):
    card = db.session.query(Card).get(card_id)
    if not card:
        return make_response(jsonify({"error": "Card not found"}), 404)

    user = db.session.query(User).get(request_user_id)
    if card.user_id != request_user_id and user.role != ROLE_ADMIN:
        return make_response(jsonify({"error": "Not authorized"}), 403)

    if request.method == "GET":
        return jsonify(card.serialized)

    if request.method == "PUT":
        if not card.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return jsonify(card.serialized)

    if request.method == "DELETE":
        db.session.delete(card)
        db.session.commit()
        return jsonify(None)

    return make_response(jsonify({"error": "Unknown action"}), 400)
