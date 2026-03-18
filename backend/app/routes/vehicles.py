from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from app.services.vehicle_service import VehicleService
from app.schemas.vehicle_schema import VehicleSchema, VehicleCreateSchema, VehicleUpdateSchema
from app.exceptions import NotFoundError, ConflictError, ValidationError

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
    try:
        vehicle = get_service().get_by_identifier(identifier)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except ValidationError as e:
        return jsonify({"error": e.message}), 400

    return jsonify({"vehicle": VehicleSchema().dump(vehicle)}), 200


@vehicles_bp.route("", methods=["POST"])
def create_vehicle():
    """POST /vehicles"""
    try:
        data = VehicleCreateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    try:
        vehicle = get_service().create(**data)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except ConflictError as e:
        resp = {"error": e.message}
        if e.existing:
            resp["existing_vehicle"] = VehicleSchema().dump(e.existing)
        return jsonify(resp), 409

    return jsonify({"vehicle": VehicleSchema().dump(vehicle)}), 201


@vehicles_bp.route("/<string:vehicle_id>", methods=["PATCH"])
def update_vehicle(vehicle_id):
    """PATCH /vehicles/{vehicle_id}"""
    try:
        data = VehicleUpdateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    try:
        vehicle = get_service().update(vehicle_id, data)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except ConflictError as e:
        resp = {"error": e.message}
        if e.existing:
            resp["existing_vehicle"] = VehicleSchema().dump(e.existing)
        return jsonify(resp), 409

    return jsonify({"vehicle": VehicleSchema().dump(vehicle)}), 200
