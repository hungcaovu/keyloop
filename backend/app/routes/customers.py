from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from app.services.customer_service import CustomerService
from app.services.vehicle_service import VehicleService
from app.schemas.customer_schema import (
    CustomerSchema,
    CustomerCreateSchema,
    CustomerUpdateSchema,
)
from app.exceptions import NotFoundError, ConflictError

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")

_svc = None


def get_service():
    global _svc
    if _svc is None:
        _svc = CustomerService()
    return _svc


@customers_bp.route("", methods=["GET"])
def search_customers():
    """
    GET /customers?phone=+1-555-0101
    GET /customers?q=smith&limit=10
    """
    phone = request.args.get("phone")
    q     = request.args.get("q")
    limit = int(request.args.get("limit", 10))

    if not phone and not q:
        return jsonify({"error": "Either 'phone' or 'q' query parameter is required."}), 400

    if q and len(q) < 2:
        return jsonify({"error": "Query 'q' must be at least 2 characters."}), 400

    customers = get_service().search(phone=phone, q=q, limit=limit)
    schema = CustomerSchema(many=True)
    return jsonify({"data": schema.dump(customers)}), 200


@customers_bp.route("", methods=["POST"])
def create_customer():
    """POST /customers"""
    try:
        data = CustomerCreateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    try:
        customer, warning = get_service().create(**data)
    except ConflictError as e:
        return jsonify({"error": e.message}), 409

    resp = {"customer": CustomerSchema().dump(customer)}
    if warning:
        resp["warning"] = warning
    return jsonify(resp), 201


@customers_bp.route("/<string:customer_id>", methods=["GET"])
def get_customer(customer_id):
    """
    GET /customers/{customer_id}
    GET /customers/{customer_id}?include=vehicles

    Optional query param `include=vehicles` embeds the customer's vehicle list
    directly in the response — saves a round-trip when the UI needs both.
    """
    include = {v.strip() for v in request.args.get("include", "").split(",") if v.strip()}

    try:
        customer = get_service().get_by_id(customer_id)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404

    customer_data = CustomerSchema().dump(customer)

    if "vehicles" in include:
        from app.schemas.vehicle_schema import VehicleSchema as VS
        vehicles = VehicleService().list_by_customer(customer_id)
        customer_data["vehicles"] = VS(many=True).dump(vehicles)

    return jsonify({"customer": customer_data}), 200


@customers_bp.route("/<string:customer_id>", methods=["PATCH"])
def update_customer(customer_id):
    """PATCH /customers/{customer_id}"""
    try:
        data = CustomerUpdateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    try:
        customer, warning = get_service().update(customer_id, data)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except ConflictError as e:
        return jsonify({"error": e.message}), 409

    resp = {"customer": CustomerSchema().dump(customer)}
    if warning:
        resp["warning"] = warning
    return jsonify(resp), 200
