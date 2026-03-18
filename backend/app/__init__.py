import logging
from flask import Flask, jsonify, render_template_string
from pythonjsonlogger import jsonlogger
from app.extensions import db
from app.config import Config


def create_app(config_object=None):
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config_object if config_object is not None else Config)

    # Structured JSON logging
    _configure_logging(app)

    # Extensions
    db.init_app(app)

    # Blueprints
    from app.routes.customers     import customers_bp
    from app.routes.vehicles      import vehicles_bp
    from app.routes.dealerships   import dealerships_bp
    from app.routes.appointments  import appointments_bp
    from app.routes.service_types import service_types_bp

    app.register_blueprint(customers_bp)
    app.register_blueprint(vehicles_bp)
    app.register_blueprint(dealerships_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(service_types_bp)

    # Health check
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "unified-service-scheduler"}), 200

    # OpenAPI spec + Swagger UI
    _register_swagger(app)

    # Global error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.exception("Unhandled exception")
        return jsonify({"error": "Internal server error"}), 500

    # CLI commands
    _register_cli(app)

    return app


_SWAGGER_UI_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Unified Service Scheduler – API Docs</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" type="text/css"
        href="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js"></script>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-standalone-preset.js"></script>
<script>
window.onload = function() {
  SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: '#swagger-ui',
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
    layout: "StandaloneLayout",
    deepLinking: true,
    tryItOutEnabled: true,
  })
}
</script>
</body>
</html>"""


def _register_swagger(app: Flask):
    from app.openapi_spec import SPEC

    @app.get("/openapi.json")
    def openapi_json():
        return jsonify(SPEC)

    @app.get("/swagger-ui")
    @app.get("/swagger-ui/")
    def swagger_ui():
        return render_template_string(_SWAGGER_UI_HTML)


def _configure_logging(app: Flask):
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO)


def _register_cli(app: Flask):
    @app.cli.command("create-db")
    def create_db():
        """Create all database tables (dev convenience — use Alembic in production)."""
        db.create_all()
        print("Database tables created.")

    @app.cli.command("seed-db")
    def seed_db():
        """Populate the database with sample data."""
        from seeds.seed_data import run_seed
        run_seed()
        print("Seed data inserted.")

    @app.cli.command("drop-db")
    def drop_db():
        """Drop all database tables (DANGER: only use in development)."""
        db.drop_all()
        print("All tables dropped.")
