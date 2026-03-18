from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from app.services.dealership_service import DealershipService
from app.services.availability_service import AvailabilityService
from app.schemas.dealership_schema import DealershipSchema
from app.schemas.technician_schema import TechnicianSchema
from app.schemas.availability_schema import (
    AvailabilityQuerySchema,
    SpotCheckResponseSchema,
)
from app.exceptions import NotFoundError

dealerships_bp = Blueprint("dealerships", __name__, url_prefix="/dealerships")

_svc       = None
_avail_svc = None


def get_service():
    global _svc
    if _svc is None:
        _svc = DealershipService()
    return _svc


def get_avail_service():
    global _avail_svc
    if _avail_svc is None:
        _avail_svc = AvailabilityService()
    return _avail_svc


@dealerships_bp.route("", methods=["GET"])
def search_dealerships():
    """
    GET /dealerships
    GET /dealerships?q=metro&limit=10
    """
    q     = request.args.get("q")
    limit = int(request.args.get("limit", 10))

    if q is not None and len(q) < 2:
        return jsonify({"error": "Query 'q' must be at least 2 characters."}), 400

    dealerships = get_service().search(q=q, limit=limit)
    schema = DealershipSchema(many=True)
    return jsonify({"data": schema.dump(dealerships)}), 200


@dealerships_bp.route("/<string:dealership_id>/technicians", methods=["GET"])
def list_technicians(dealership_id):
    """
    GET /dealerships/{dealership_id}/technicians?service_type_id=<uuid>

    Step 0c.5 — list qualified technicians so advisor/customer can pre-select one.
    """
    service_type_id = request.args.get("service_type_id")
    if not service_type_id:
        return jsonify({"error": "'service_type_id' query parameter is required."}), 400

    try:
        techs = get_avail_service().list_qualified_technicians(dealership_id, service_type_id)
    except NotFoundError as e:
        return jsonify({"error": e.message}), 404

    schema = TechnicianSchema(many=True)
    return jsonify({"data": schema.dump(techs)}), 200


@dealerships_bp.route("/<string:dealership_id>/availability", methods=["GET"])
def get_availability(dealership_id):
    """
    GET /dealerships/{dealership_id}/availability

    Mode determined by query params:
      - desired_start present → Spot Check (returns available_technicians, bay_available)
      - desired_start absent  → Calendar View (returns slots grouped by date)

    Optional filter: technician_id restricts to a specific technician.
    """
    try:
        args = AvailabilityQuerySchema().load(request.args)
    except MarshmallowValidationError as e:
        return jsonify({"error": "Invalid query parameters", "details": e.messages}), 400

    service_type_id = args["service_type_id"]
    desired_start   = args.get("desired_start")
    technician_id   = args.get("technician_id")
    from_date       = args.get("from_date")
    days            = args.get("days", 15)

    try:
        if desired_start is not None:
            # ── Spot Check mode ────────────────────────────────────────────────
            # Strip timezone info (treat as UTC)
            if desired_start.tzinfo is not None:
                from datetime import timezone
                desired_start = desired_start.astimezone(timezone.utc).replace(tzinfo=None)

            result = get_avail_service().check_slot(
                dealership_id=dealership_id,
                service_type_id=service_type_id,
                desired_start=desired_start,
                technician_id=technician_id,
            )
            return jsonify(SpotCheckResponseSchema().dump(result)), 200

        else:
            # ── Calendar mode ──────────────────────────────────────────────────
            result = get_avail_service().get_calendar_slots(
                dealership_id=dealership_id,
                service_type_id=service_type_id,
                from_date=from_date,
                days=days,
                technician_id=technician_id,
            )
            # Build the response dict manually to match exact schema
            resp = {
                "service_type": {
                    "name": result.service_type_name,
                    "duration_minutes": result.duration_minutes,
                },
                "from_date": result.from_date,
                "to_date": result.to_date,
                "filtered_technician": result.filtered_technician,
                "slots": [
                    {
                        "date": day.date,
                        "available_times": [
                            {
                                "start": slot.start.isoformat(),
                                "end": slot.end.isoformat(),
                                "technician_count": slot.technician_count,
                            }
                            for slot in day.available_times
                        ],
                    }
                    for day in result.slots
                ],
            }
            return jsonify(resp), 200

    except NotFoundError as e:
        return jsonify({"error": e.message}), 404
