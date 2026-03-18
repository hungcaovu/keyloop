import base64
import logging
from flask import Blueprint, request, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from app.services.dealership_service import DealershipService

logger = logging.getLogger(__name__)


def _encode_cursor(item_id: int) -> str:
    return base64.b64encode(str(item_id).encode()).decode()


def _decode_cursor(cursor: str) -> int | None:
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        return None
from app.services.availability_service import AvailabilityService
from app.schemas.dealership_schema import DealershipSchema
from app.schemas.technician_schema import TechnicianSchema
from app.schemas.availability_schema import (
    AvailabilityQuerySchema,
    SpotCheckResponseSchema,
)
from app.exceptions import NotFoundError
from app.utils.entity_ref import parse_id

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
    q      = request.args.get("q")
    limit  = int(request.args.get("limit", 10))
    cursor = request.args.get("cursor")

    if q is not None and len(q) < 2:
        return jsonify({"error": "Query 'q' must be at least 2 characters."}), 400

    after_id = _decode_cursor(cursor) if cursor else None

    if q:
        logger.info("List dealerships: q=%s limit=%s after_id=%s", q, limit, after_id)
    else:
        logger.info("List dealerships: all limit=%s after_id=%s", limit, after_id)

    items = get_service().search(q=q, limit=limit + 1, after_id=after_id)

    has_more    = len(items) > limit
    items       = items[:limit]
    next_cursor = _encode_cursor(items[-1].id) if has_more and items else None

    logger.info("List dealerships result: %d found has_more=%s", len(items), has_more)
    return jsonify({"data": DealershipSchema(many=True).dump(items), "next_cursor": next_cursor}), 200


@dealerships_bp.route("/<string:dealership_id>/technicians", methods=["GET"])
def list_technicians(dealership_id):
    """
    GET /dealerships/{dealership_id}/technicians?service_type_id=<id>

    Step 0c.5 — list qualified technicians so advisor/customer can pre-select one.
    """
    service_type_id = request.args.get("service_type_id")
    if not service_type_id:
        return jsonify({"error": "'service_type_id' query parameter is required."}), 400

    d_pk            = parse_id("dealership", dealership_id)
    service_type_id = int(service_type_id) if service_type_id.isdigit() else None
    logger.info("List technicians: dealership=%s service_type=%s", d_pk, service_type_id)
    try:
        techs = get_avail_service().list_qualified_technicians(d_pk, service_type_id)
    except NotFoundError as e:
        logger.warning("List technicians: not found %s", e.message)
        return jsonify({"error": e.message}), 404

    logger.info("List technicians result: %d found", len(techs))
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

    d_pk            = parse_id("dealership", dealership_id)
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
                dealership_id=d_pk,
                service_type_id=service_type_id,
                desired_start=desired_start,
                technician_id=technician_id,
            )
            return jsonify(SpotCheckResponseSchema().dump(result)), 200

        else:
            # ── Calendar mode ──────────────────────────────────────────────────
            result = get_avail_service().get_calendar_slots(
                dealership_id=d_pk,
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
                                "start": slot.start.isoformat() + "Z",
                                "end": slot.end.isoformat() + "Z",
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
