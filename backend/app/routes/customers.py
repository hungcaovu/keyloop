from __future__ import annotations
import base64
import logging
from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)


def _encode_cursor(item_id: int) -> str:
    return base64.b64encode(str(item_id).encode()).decode()


def _decode_cursor(cursor: str) -> int | None:
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        return None
from app.services.vehicle_service import VehicleService
from app.schemas.customer_schema import (
    CustomerSchema,
    CustomerCreateSchema,
    CustomerUpdateSchema,
)
from app.exceptions import NotFoundError, ConflictError
from app.utils.entity_ref import parse_id

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
    GET /customers?q=smith          — search across name + phone
    GET /customers?q=+1-555-0101    — same endpoint, phone is just another field
    """
    q      = request.args.get("q")
    limit  = int(request.args.get("limit", 10))
    cursor = request.args.get("cursor")

    if not q:
        return jsonify({"error": "Query parameter 'q' is required."}), 400

    if len(q) < 2:
        return jsonify({"error": "Query 'q' must be at least 2 characters."}), 400

    after_id = _decode_cursor(cursor) if cursor else None

    logger.info("Search customers: q=%s limit=%s after_id=%s", q, limit, after_id)
    items = get_service().search_any(q, limit=limit + 1, after_id=after_id)

    has_more    = len(items) > limit
    items       = items[:limit]
    next_cursor = _encode_cursor(items[-1].id) if has_more and items else None

    logger.info("Search customers result: %d found has_more=%s", len(items), has_more)
    return jsonify({"data": CustomerSchema(many=True).dump(items), "next_cursor": next_cursor}), 200


@customers_bp.route("", methods=["POST"])
def create_customer():
    """POST /customers"""
    try:
        data = CustomerCreateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    logger.info("Create customer: email=%s", data.get("email"))
    try:
        customer, warning = get_service().create(**data)
    except ConflictError as e:
        logger.warning("Create customer conflict: %s", e.message)
        return jsonify({"error": e.message}), 409

    logger.info("Customer created: id=%s", customer.id)
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

    pk = parse_id("customer", customer_id)
    logger.info("Get customer: id=%s include=%s", pk, include)
    try:
        customer = get_service().get_by_id(pk)
    except NotFoundError as e:
        logger.warning("Customer not found: id=%s", customer_id)
        return jsonify({"error": e.message}), 404

    customer_data = CustomerSchema().dump(customer)

    if "vehicles" in include:
        from app.schemas.vehicle_schema import VehicleSchema as VS
        from app.repositories.appointment_repository import AppointmentRepository
        vehicles = VehicleService().list_by_customer(pk)
        vehicle_data = VS(many=True).dump(vehicles)

        # Attach latest non-cancelled appointment per vehicle (1 batch query)
        vehicle_ids = [v.id for v in vehicles]
        latest_map  = AppointmentRepository().get_latest_by_vehicle_ids(vehicle_ids)
        for item, v in zip(vehicle_data, vehicles):
            appt = latest_map.get(v.id)
            if appt:
                item["recent_appointment"] = {
                    "id":              appt.id,
                    "status":          appt.status,
                    "scheduled_start": appt.scheduled_start.isoformat() + "Z",
                    "scheduled_end":   appt.scheduled_end.isoformat() + "Z",
                    "service_type":    {"name": appt.service_type.name},
                    "technician":      {"name": f"{appt.technician.first_name} {appt.technician.last_name}"} if appt.technician else None,
                }
            else:
                item["recent_appointment"] = None

        customer_data["vehicles"] = vehicle_data

    return jsonify({"customer": customer_data}), 200


@customers_bp.route("/<string:customer_id>", methods=["PATCH"])
def update_customer(customer_id):
    """PATCH /customers/{customer_id}"""
    try:
        data = CustomerUpdateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    pk = parse_id("customer", customer_id)
    logger.info("Update customer: id=%s fields=%s", pk, list(data.keys()))
    try:
        customer, warning = get_service().update(pk, data)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except ConflictError as e:
        return jsonify({"error": e.message}), 409

    resp = {"customer": CustomerSchema().dump(customer)}
    if warning:
        resp["warning"] = warning
    return jsonify(resp), 200
