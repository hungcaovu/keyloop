import logging
from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from app.services.vehicle_service import VehicleService

logger = logging.getLogger(__name__)
from app.schemas.vehicle_schema import VehicleSchema, VehicleCreateSchema, VehicleUpdateSchema
from app.exceptions import NotFoundError, ConflictError, ValidationError
from app.utils.entity_ref import parse_id

vehicles_bp = Blueprint("vehicles", __name__, url_prefix="/vehicles")

_svc = None


def get_service():
    global _svc
    if _svc is None:
        _svc = VehicleService()
    return _svc


@vehicles_bp.route("/<string:identifier>", methods=["GET"])
def get_vehicle(identifier):
    """
    GET /vehicles/{identifier}
    Auto-detects: UUID → lookup by id, 17-char alphanumeric → lookup by VIN.
    """
    logger.info("Get vehicle: identifier=%s", identifier)
    try:
        vehicle = get_service().get_by_identifier(identifier)
    except NotFoundError as e:
        logger.warning("Vehicle not found: identifier=%s", identifier)
        return jsonify({"error": e.message}), 404
    except ValidationError as e:
        return jsonify({"error": e.message}), 400

    logger.info("Vehicle found: id=%s %s %s %s", vehicle.id, vehicle.year, vehicle.make, vehicle.model)
    return jsonify({"vehicle": VehicleSchema().dump(vehicle)}), 200


@vehicles_bp.route("", methods=["POST"])
def create_vehicle():
    """POST /vehicles"""
    try:
        data = VehicleCreateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    logger.info("Create vehicle: customer_id=%s %s %s %s", data.get("customer_id"), data.get("year"), data.get("make"), data.get("model"))
    try:
        vehicle = get_service().create(**data)
    except NotFoundError as e:
        logger.warning("Create vehicle: customer not found id=%s", data.get("customer_id"))
        return jsonify({"error": e.message}), 404
    except ConflictError as e:
        logger.warning("Create vehicle conflict: %s", e.message)
        resp = {"error": e.message}
        if e.existing:
            resp["existing_vehicle"] = VehicleSchema().dump(e.existing)
        return jsonify(resp), 409

    logger.info("Vehicle created: id=%s vin=%s", vehicle.id, vehicle.vin)
    return jsonify({"vehicle": VehicleSchema().dump(vehicle)}), 201


@vehicles_bp.route("/<string:vehicle_id>", methods=["PATCH"])
def update_vehicle(vehicle_id):
    """PATCH /vehicles/{vehicle_id}"""
    try:
        data = VehicleUpdateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    pk = parse_id("vehicle", vehicle_id)
    try:
        vehicle = get_service().update(pk, data)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except ConflictError as e:
        resp = {"error": e.message}
        if e.existing:
            resp["existing_vehicle"] = VehicleSchema().dump(e.existing)
        return jsonify(resp), 409

    return jsonify({"vehicle": VehicleSchema().dump(vehicle)}), 200
