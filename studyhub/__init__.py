import os
from flask import Flask, redirect, url_for, render_template, jsonify, request
from flask_login import current_user
from studyhub.config import config_by_name
from studyhub.extensions import db, migrate, login_manager, csrf, limiter

def create_app(config_name=None):
    """Application factory for StudyHub V2."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "production")

    app = Flask(__name__)
    app_config = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(app_config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Exempt public health check from CSRF
    from studyhub.blueprints.api import healthz
    csrf.exempt(healthz)

    # Register blueprints
    from studyhub.blueprints.auth import auth_bp
    from studyhub.blueprints.owner import owner_bp
    from studyhub.blueprints.admin import admin_bp
    from studyhub.blueprints.student import student_bp
    from studyhub.blueprints.api import api_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(owner_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(api_bp)

    # Root redirect
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.is_platform_owner():
                return redirect(url_for("owner.dashboard"))
            elif current_user.is_admin():
                return redirect(url_for("admin.dashboard"))
            else:
                return redirect(url_for("student.dashboard"))
        return redirect(url_for("auth.login"))

    # Direct healthz root alias for Render
    @app.route("/healthz")
    def root_healthz():
        return jsonify({"status": "ok", "app": "StudyHub V2"}), 200

    # Custom Jinja filters
    @app.template_filter("filesizeformat")
    def format_bytes(size):
        try:
            size = float(size)
        except (ValueError, TypeError):
            return "0 B"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    # Security Headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Error Handlers
    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Bad Request"}), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Access Denied"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def page_not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource Not Found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def request_entity_too_large(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "File size exceeds 100 MB limit"}), 413
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def ratelimit_handler(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Too Many Requests"}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal Server Error"}), 500
        return render_template("errors/500.html"), 500

    return app
