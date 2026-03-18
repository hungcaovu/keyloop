from flask import Blueprint, request, jsonify
from app.repositories.service_type_repository import ServiceTypeRepository
from app.schemas.service_type_schema import ServiceTypeSchema

service_types_bp = Blueprint("service_types", __name__, url_prefix="/service-types")


@service_types_bp.route("", methods=["GET"])
def list_service_types():
    """
    GET /service-types
    GET /service-types?q=brake&limit=20
    """
    q     = request.args.get("q")
    limit = int(request.args.get("limit", 20))

    if q is not None and len(q) < 2:
        return jsonify({"error": "Query 'q' must be at least 2 characters."}), 400

    repo = ServiceTypeRepository()
    service_types = repo.search_by_name(q, limit=limit) if q else repo.list_all()

    schema = ServiceTypeSchema(many=True)
    return jsonify({"data": schema.dump(service_types)}), 200
