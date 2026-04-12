from flask import Blueprint, jsonify, session

bp = Blueprint("myapp", __name__)

# Auth is handled by the platform — all routes here are already protected.
# Users have a valid @twilio.com session by the time they reach these endpoints.
# session.get("user_email") gives you their email if needed.


@bp.route("/api/myapp/hello")
def hello():
    return jsonify({"message": f"Hello {session.get('user_email')}"})
