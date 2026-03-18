import base64
import logging
from flask import Blueprint, request, jsonify
from app.repositories.service_type_repository import ServiceTypeRepository
from app.schemas.service_type_schema import ServiceTypeSchema

logger = logging.getLogger(__name__)

service_types_bp = Blueprint("service_types", __name__, url_prefix="/service-types")


def _encode_cursor(item_id: int) -> str:
    return base64.b64encode(str(item_id).encode()).decode()


def _decode_cursor(cursor: str) -> int | None:
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        return None


@service_types_bp.route("", methods=["GET"])
def list_service_types():
    """
    GET /service-types
    GET /service-types?q=brake&limit=20&cursor=<cursor>
    """
    q      = request.args.get("q")
    limit  = int(request.args.get("limit", 20))
    cursor = request.args.get("cursor")

    if q is not None and len(q) < 2:
        return jsonify({"error": "Query 'q' must be at least 2 characters."}), 400

    after_id = _decode_cursor(cursor) if cursor else None

    if q:
        logger.info("List service types: q=%s limit=%s after_id=%s", q, limit, after_id)
    else:
        logger.info("List service types: all limit=%s after_id=%s", limit, after_id)

    repo  = ServiceTypeRepository()
    items = repo.search_by_name(q, limit=limit + 1, after_id=after_id) if q else repo.list_all(limit=limit + 1, after_id=after_id)

    has_more    = len(items) > limit
    items       = items[:limit]
    next_cursor = _encode_cursor(items[-1].id) if has_more and items else None

    logger.info("List service types result: %d found has_more=%s", len(items), has_more)
    return jsonify({"data": ServiceTypeSchema(many=True).dump(items), "next_cursor": next_cursor}), 200
