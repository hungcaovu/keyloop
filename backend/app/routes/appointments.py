from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from datetime import timezone
from app.services.appointment_service import AppointmentService
from app.schemas.appointment_schema import AppointmentCreateSchema, AppointmentSchema
from app.exceptions import NotFoundError, ResourceUnavailableError, ValidationError

appointments_bp = Blueprint("appointments", __name__, url_prefix="/appointments")

_svc = None


def get_service():
    global _svc
    if _svc is None:
        _svc = AppointmentService()
    return _svc


@appointments_bp.route("", methods=["POST"])
def create_appointment():
    """
    POST /appointments

    Validates, resolves resources, acquires advisory locks, and confirms the booking.
    Returns 201 with the full appointment on success, or 409 with next_available_slot
    if the slot was taken by a concurrent request.
    """
    try:
        data = AppointmentCreateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    # Strip timezone info from desired_start — treat as UTC
    desired_start = data["desired_start"]
    if desired_start.tzinfo is not None:
        desired_start = desired_start.astimezone(timezone.utc).replace(tzinfo=None)
    data["desired_start"] = desired_start

    try:
        appointment = get_service().create_appointment(**data)
    except ValidationError as e:
        return jsonify({"error": e.message, "field": e.field}), 400
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except ResourceUnavailableError as e:
        next_slot = e.next_available_slot
        return jsonify({
            "error": "ResourceUnavailable",
            "message": e.message,
            "next_available_slot": next_slot.isoformat() if next_slot else None,
        }), 409

    return jsonify({"appointment": AppointmentSchema().dump(appointment)}), 201
