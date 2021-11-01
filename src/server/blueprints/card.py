from flask import jsonify, request
from flask.blueprints import Blueprint
from flask.helpers import make_response

from models import Card
from server.database import db
from server.decorators import authenticated, restrict_host

card_blueprint = Blueprint("card", __name__)


@card_blueprint.route("/api/cards", methods=["GET"])
@authenticated()
@restrict_host
def cards():
    return jsonify([i.serialize for i in db.session.query(Card).order_by(Card.description).all()])


@card_blueprint.route("/api/card/<int:card_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def card(card_id):
    if request.method == "GET":
        card = db.session.query(Card).get(card_id)
        if card:
            return jsonify(card.serialize)

        return make_response(jsonify({"error": "Card not found"}), 404)
    elif request.method == "PUT":
        card = db.session.query(Card).get(card_id)
        if card:
            if not card.update(request.json):
                return make_response("", 204)

            db.session.commit()
            return jsonify(None)
        return make_response(jsonify({"error": "Card not found"}), 404)
    elif request.method == "DELETE":
        card = db.session.query(Card).get(card_id)
        if card:
            db.session.delete(card)
            db.session.commit()
            return jsonify(None)
        else:
            return make_response(jsonify({"error": "Card not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)
