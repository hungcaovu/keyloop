import logging
from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError

logger = logging.getLogger(__name__)
from datetime import timezone
from app.services.appointment_service import AppointmentService
from app.schemas.appointment_schema import AppointmentCreateSchema, AppointmentSchema
from app.exceptions import (
    NotFoundError, ResourceUnavailableError, ValidationError,
    HoldExpiredError, InvalidStateError,
)

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
    POST /appointments — Phase 1: create a PENDING soft hold.

    Validates, resolves resources, acquires advisory locks, and creates a
    PENDING appointment with expires_at = now + 10 minutes.
    Returns 202 Accepted. The advisor must call PATCH /{id}/confirm within the TTL.
    """
    try:
        data = AppointmentCreateSchema().load(request.get_json() or {})
    except MarshmallowValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 400

    desired_start = data["desired_start"]
    if desired_start.tzinfo is not None:
        desired_start = desired_start.astimezone(timezone.utc).replace(tzinfo=None)
    data["desired_start"] = desired_start

    logger.info(
        "Book appointment: dealership=%s customer=%s vehicle=%s service_type=%s start=%s",
        data.get("dealership_id"), data.get("customer_id"),
        data.get("vehicle_id"), data.get("service_type_id"), desired_start,
    )
    try:
        appointment = get_service().create_appointment(**data)
    except ValidationError as e:
        logger.warning("Appointment validation error: %s field=%s", e.message, e.field)
        return jsonify({"error": e.message, "field": e.field}), 400
    except NotFoundError as e:
        logger.warning("Appointment resource not found: %s", e.message)
        return jsonify({"error": e.message}), 404
    except ResourceUnavailableError as e:
        next_slot = e.next_available_slot
        logger.warning("Appointment conflict: %s next_slot=%s", e.message, next_slot)
        return jsonify({
            "error": "ResourceUnavailable",
            "message": e.message,
            "next_available_slot": next_slot.isoformat() + "Z" if next_slot else None,
        }), 409

    logger.info(
        "Appointment pending: id=%s expires_at=%s",
        appointment.id, appointment.expires_at,
    )
    return jsonify({"appointment": AppointmentSchema().dump(appointment)}), 202


@appointments_bp.route("/<int:appointment_id>/confirm", methods=["PATCH"])
def confirm_appointment(appointment_id):
    """
    PATCH /appointments/{id}/confirm — Phase 2: confirm PENDING → CONFIRMED.

    Must be called within the TTL (before expires_at).
    Returns 200 with the confirmed appointment.
    """
    try:
        appointment = get_service().confirm_appointment(appointment_id)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except HoldExpiredError as e:
        next_slot = e.next_available_slot
        return jsonify({
            "error": "HoldExpired",
            "message": e.message,
            "next_available_slot": next_slot.isoformat() + "Z" if next_slot else None,
        }), 409
    except InvalidStateError as e:
        return jsonify({"error": e.message}), 422

    logger.info("Appointment confirmed: id=%s", appointment.id)
    return jsonify({"appointment": AppointmentSchema().dump(appointment)}), 200


@appointments_bp.route("/<int:appointment_id>/cancel", methods=["PATCH"])
def cancel_appointment(appointment_id):
    """
    PATCH /appointments/{id}/cancel — cancel PENDING or CONFIRMED → CANCELLED.

    COMPLETED appointments cannot be cancelled (422).
    """
    try:
        appointment = get_service().cancel_appointment(appointment_id)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
    except InvalidStateError as e:
        return jsonify({"error": e.message}), 422

    logger.info("Appointment cancelled: id=%s", appointment.id)
    return jsonify({"appointment": AppointmentSchema().dump(appointment)}), 200
