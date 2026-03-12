"""
Wolfram AgentOne Blueprint for OntServe

Provides a web interface and JSON API for querying the Wolfram AgentOne API.
Conversation history is maintained in the Flask session.
"""

import logging

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    session,
)

logger = logging.getLogger(__name__)

wolfram_bp = Blueprint("wolfram", __name__, url_prefix="/wolfram")


def _get_service():
    """Retrieve the WolframService instance from the app."""
    return current_app.wolfram_service


@wolfram_bp.route("/")
def index():
    """Wolfram query interface."""
    service = _get_service()
    history = session.get("wolfram_history", [])
    return render_template(
        "wolfram/query.html",
        configured=service.is_configured,
        history=history,
    )


@wolfram_bp.route("/query", methods=["POST"])
def query():
    """
    Send a query to Wolfram AgentOne.

    Expects JSON: {"message": "..."}
    Returns JSON with the response.
    """
    service = _get_service()

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"success": False, "error": "No message provided."}), 400

    # Retrieve conversation history from session
    history = session.get("wolfram_history", [])

    # Build conversation context for the API (role/content pairs only)
    conversation = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in history
    ]

    result = service.query(message, conversation_history=conversation)

    # Persist to session on success
    if result["success"]:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": result["content"]})
        session["wolfram_history"] = history

    return jsonify(result)


@wolfram_bp.route("/clear", methods=["POST"])
def clear_history():
    """Clear the conversation history stored in the session."""
    session.pop("wolfram_history", None)
    return jsonify({"success": True})


@wolfram_bp.route("/status")
def status():
    """Return Wolfram service status as JSON."""
    service = _get_service()
    return jsonify(service.get_status())
