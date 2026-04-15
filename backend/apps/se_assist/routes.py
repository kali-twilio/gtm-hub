from __future__ import annotations

import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from .database import get_db
from .models import AIAnalysis, GongEmail, Transcript, TranscriptAnalysis
from .services.claude_analysis import analyze_gong_email, analyze_transcript
from .services.email_parser import parse_call_date, parse_eml

bp = Blueprint("se_assist", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email_to_dict(e: GongEmail) -> dict:
    return {
        "id": e.id,
        "gmail_message_id": e.gmail_message_id,
        "subject": e.subject,
        "company_name": e.company_name,
        "call_date": e.call_date.isoformat() if e.call_date else None,
        "duration": e.duration,
        "parsed_data": e.parsed_data,
        "status": e.status,
        "received_at": e.received_at.isoformat() if e.received_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "uploaded_by_name": e.user_email,
        "user_email": e.user_email,
    }


def _analysis_to_dict(a: AIAnalysis) -> dict:
    return {
        "id": a.id,
        "gong_email_id": a.gong_email_id,
        "use_case_category": a.use_case_category,
        "presales_stage": a.presales_stage,
        "sfdc_use_case_description": a.sfdc_use_case_description,
        "sfdc_solutions_notes": a.sfdc_solutions_notes,
        "sfdc_technical_risks": a.sfdc_technical_risks,
        "raw_response": a.raw_response,
        "model_used": a.model_used,
        "input_tokens": a.input_tokens,
        "output_tokens": a.output_tokens,
        "cost_usd": a.cost_usd,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _transcript_to_dict(t: Transcript) -> dict:
    return {
        "id": t.id,
        "company_name": t.company_name,
        "call_date": t.call_date.isoformat() if t.call_date else None,
        "duration": t.duration,
        "transcript_text": t.transcript_text,
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "uploaded_by_name": t.user_email,
        "user_email": t.user_email,
    }


def _transcript_analysis_to_dict(a: TranscriptAnalysis) -> dict:
    return {
        "id": a.id,
        "transcript_id": a.transcript_id,
        "use_case_category": a.use_case_category,
        "presales_stage": a.presales_stage,
        "sfdc_use_case_description": a.sfdc_use_case_description,
        "sfdc_solutions_notes": a.sfdc_solutions_notes,
        "sfdc_technical_risks": a.sfdc_technical_risks,
        "raw_response": a.raw_response,
        "model_used": a.model_used,
        "input_tokens": a.input_tokens,
        "output_tokens": a.output_tokens,
        "cost_usd": a.cost_usd,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ===========================================================================
# Email routes
# ===========================================================================

@bp.route("/api/se-assist/emails")
def list_emails():
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 20, type=int)
    uploaded_by = request.args.get("uploaded_by", None)

    with get_db() as db:
        query = db.query(GongEmail)
        if uploaded_by:
            query = query.filter(GongEmail.user_email == uploaded_by)
        total = query.count()
        emails = query.order_by(GongEmail.received_at.desc()).offset(skip).limit(limit).all()
        return jsonify({"emails": [_email_to_dict(e) for e in emails], "total": total})


@bp.route("/api/se-assist/emails/uploaders")
def list_email_uploaders():
    with get_db() as db:
        rows = (
            db.query(GongEmail.user_email)
            .distinct()
            .order_by(GongEmail.user_email)
            .all()
        )
        return jsonify([{"id": r.user_email, "name": r.user_email} for r in rows])


@bp.route("/api/se-assist/emails/<int:email_id>")
def get_email(email_id: int):
    with get_db() as db:
        email_obj = db.query(GongEmail).filter(GongEmail.id == email_id).first()
        if not email_obj:
            return jsonify({"error": "Email not found"}), 404
        return jsonify(_email_to_dict(email_obj))


@bp.route("/api/se-assist/emails/upload", methods=["POST"])
def upload_eml():
    user_email = session["user_email"]
    file = request.files.get("file")
    if not file or not file.filename or not file.filename.endswith(".eml"):
        return jsonify({"error": "Please upload a .eml file"}), 400

    raw_bytes = file.read()
    result = parse_eml(raw_bytes)
    parsed = result["parsed_data"]
    call_date = parse_call_date(parsed.get("call_date"))

    msg_id = result.get("message_id") or f"upload-{uuid.uuid4().hex[:12]}"
    msg_id = f"{msg_id}-{uuid.uuid4().hex[:8]}"

    with get_db() as db:
        gong_email = GongEmail(
            user_email=user_email,
            gmail_message_id=msg_id,
            subject=result["subject"],
            company_name=parsed.get("company_name"),
            call_date=call_date,
            duration=parsed.get("duration"),
            parsed_data=parsed,
            status="uploaded",
            received_at=datetime.utcnow(),
        )
        db.add(gong_email)
        db.flush()
        email_id = gong_email.id
    return jsonify({"message": "Email uploaded", "email_id": email_id})


@bp.route("/api/se-assist/emails/<int:email_id>", methods=["DELETE"])
def delete_email(email_id: int):
    user_email = session["user_email"]
    with get_db() as db:
        email_obj = db.query(GongEmail).filter(GongEmail.id == email_id).first()
        if not email_obj:
            return jsonify({"error": "Email not found"}), 404
        if email_obj.user_email != user_email:
            return jsonify({"error": "Only the uploader can delete this email"}), 403
        db.delete(email_obj)
    return jsonify({"message": "Email deleted"})


# ===========================================================================
# Email analysis routes
# ===========================================================================

@bp.route("/api/se-assist/analysis/<int:email_id>", methods=["POST"])
def run_analysis(email_id: int):
    with get_db() as db:
        gong_email = db.query(GongEmail).filter(GongEmail.id == email_id).first()
        if not gong_email:
            return jsonify({"error": "Email not found"}), 404
        if gong_email.analysis:
            return jsonify({"error": "Analysis already exists. Use rerun endpoint."}), 409

        result = analyze_gong_email(gong_email.parsed_data, gong_email.subject)

        analysis = AIAnalysis(
            gong_email_id=gong_email.id,
            raw_response=result["raw_response"],
            use_case_category=result.get("use_case_category"),
            presales_stage=result.get("presales_stage"),
            sfdc_use_case_description=result.get("sfdc_use_case_description"),
            sfdc_solutions_notes=result.get("sfdc_solutions_notes"),
            sfdc_technical_risks=result.get("sfdc_technical_risks"),
            model_used=result.get("model_used"),
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            cost_usd=result.get("cost_usd"),
        )
        db.add(analysis)
        gong_email.status = "analyzed"
        db.flush()
        return jsonify(_analysis_to_dict(analysis))


@bp.route("/api/se-assist/analysis/<int:email_id>")
def get_analysis(email_id: int):
    with get_db() as db:
        analysis = db.query(AIAnalysis).filter(AIAnalysis.gong_email_id == email_id).first()
        if not analysis:
            return jsonify({"error": "Analysis not found"}), 404
        return jsonify(_analysis_to_dict(analysis))


@bp.route("/api/se-assist/analysis/<int:analysis_id>", methods=["PUT"])
def update_analysis(analysis_id: int):
    with get_db() as db:
        analysis = db.query(AIAnalysis).filter(AIAnalysis.id == analysis_id).first()
        if not analysis:
            return jsonify({"error": "Analysis not found"}), 404

        data = request.get_json() or {}
        for field in ("use_case_category", "presales_stage", "sfdc_use_case_description",
                      "sfdc_solutions_notes", "sfdc_technical_risks"):
            if field in data:
                setattr(analysis, field, data[field])
        db.flush()
        return jsonify(_analysis_to_dict(analysis))


@bp.route("/api/se-assist/analysis/<int:email_id>/rerun", methods=["POST"])
def rerun_analysis(email_id: int):
    with get_db() as db:
        gong_email = db.query(GongEmail).filter(GongEmail.id == email_id).first()
        if not gong_email:
            return jsonify({"error": "Email not found"}), 404

        if gong_email.analysis:
            db.delete(gong_email.analysis)
            db.flush()

        result = analyze_gong_email(gong_email.parsed_data, gong_email.subject)

        analysis = AIAnalysis(
            gong_email_id=gong_email.id,
            raw_response=result["raw_response"],
            use_case_category=result.get("use_case_category"),
            presales_stage=result.get("presales_stage"),
            sfdc_use_case_description=result.get("sfdc_use_case_description"),
            sfdc_solutions_notes=result.get("sfdc_solutions_notes"),
            sfdc_technical_risks=result.get("sfdc_technical_risks"),
            model_used=result.get("model_used"),
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            cost_usd=result.get("cost_usd"),
        )
        db.add(analysis)
        gong_email.status = "analyzed"
        db.flush()
        return jsonify(_analysis_to_dict(analysis))


# ===========================================================================
# Transcript routes
# ===========================================================================

@bp.route("/api/se-assist/transcripts")
def list_transcripts():
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 20, type=int)
    uploaded_by = request.args.get("uploaded_by", None)

    with get_db() as db:
        query = db.query(Transcript)
        if uploaded_by:
            query = query.filter(Transcript.user_email == uploaded_by)
        total = query.count()
        transcripts = query.order_by(Transcript.created_at.desc()).offset(skip).limit(limit).all()
        return jsonify({"transcripts": [_transcript_to_dict(t) for t in transcripts], "total": total})


@bp.route("/api/se-assist/transcripts/uploaders")
def list_transcript_uploaders():
    with get_db() as db:
        rows = (
            db.query(Transcript.user_email)
            .distinct()
            .order_by(Transcript.user_email)
            .all()
        )
        return jsonify([{"id": r.user_email, "name": r.user_email} for r in rows])


@bp.route("/api/se-assist/transcripts/<int:transcript_id>")
def get_transcript(transcript_id: int):
    with get_db() as db:
        obj = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not obj:
            return jsonify({"error": "Transcript not found"}), 404
        return jsonify(_transcript_to_dict(obj))


@bp.route("/api/se-assist/transcripts", methods=["POST"])
def create_transcript():
    user_email = session["user_email"]
    data = request.get_json()
    if not data or not data.get("company_name") or not data.get("transcript_text"):
        return jsonify({"error": "company_name and transcript_text are required"}), 400

    call_date = parse_call_date(data.get("call_date")) if data.get("call_date") else None

    with get_db() as db:
        transcript = Transcript(
            user_email=user_email,
            company_name=data["company_name"],
            call_date=call_date,
            duration=data.get("duration"),
            transcript_text=data["transcript_text"],
            status="uploaded",
        )
        db.add(transcript)
        db.flush()
        return jsonify(_transcript_to_dict(transcript))


@bp.route("/api/se-assist/transcripts/<int:transcript_id>", methods=["DELETE"])
def delete_transcript(transcript_id: int):
    user_email = session["user_email"]
    with get_db() as db:
        obj = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not obj:
            return jsonify({"error": "Transcript not found"}), 404
        if obj.user_email != user_email:
            return jsonify({"error": "Only the uploader can delete this transcript"}), 403
        db.delete(obj)
    return jsonify({"message": "Transcript deleted"})


# ===========================================================================
# Transcript analysis routes
# ===========================================================================

@bp.route("/api/se-assist/transcripts/<int:transcript_id>/analyze", methods=["POST"])
def run_transcript_analysis(transcript_id: int):
    with get_db() as db:
        transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not transcript:
            return jsonify({"error": "Transcript not found"}), 404
        if transcript.analysis:
            return jsonify({"error": "Analysis already exists. Use rerun endpoint."}), 409

        result = analyze_transcript(
            transcript.company_name,
            transcript.transcript_text,
            call_date=transcript.call_date.strftime("%b %d, %Y") if transcript.call_date else None,
            duration=transcript.duration,
        )

        analysis = TranscriptAnalysis(
            transcript_id=transcript.id,
            raw_response=result["raw_response"],
            use_case_category=result.get("use_case_category"),
            presales_stage=result.get("presales_stage"),
            sfdc_use_case_description=result.get("sfdc_use_case_description"),
            sfdc_solutions_notes=result.get("sfdc_solutions_notes"),
            sfdc_technical_risks=result.get("sfdc_technical_risks"),
            model_used=result.get("model_used"),
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            cost_usd=result.get("cost_usd"),
        )
        db.add(analysis)
        transcript.status = "analyzed"
        db.flush()
        return jsonify(_transcript_analysis_to_dict(analysis))


@bp.route("/api/se-assist/transcripts/<int:transcript_id>/analysis")
def get_transcript_analysis(transcript_id: int):
    with get_db() as db:
        analysis = db.query(TranscriptAnalysis).filter(TranscriptAnalysis.transcript_id == transcript_id).first()
        if not analysis:
            return jsonify({"error": "Analysis not found"}), 404
        return jsonify(_transcript_analysis_to_dict(analysis))


@bp.route("/api/se-assist/transcripts/analysis/<int:analysis_id>", methods=["PUT"])
def update_transcript_analysis(analysis_id: int):
    with get_db() as db:
        analysis = db.query(TranscriptAnalysis).filter(TranscriptAnalysis.id == analysis_id).first()
        if not analysis:
            return jsonify({"error": "Analysis not found"}), 404

        data = request.get_json() or {}
        for field in ("use_case_category", "presales_stage", "sfdc_use_case_description",
                      "sfdc_solutions_notes", "sfdc_technical_risks"):
            if field in data:
                setattr(analysis, field, data[field])
        db.flush()
        return jsonify(_transcript_analysis_to_dict(analysis))


@bp.route("/api/se-assist/transcripts/<int:transcript_id>/rerun", methods=["POST"])
def rerun_transcript_analysis(transcript_id: int):
    with get_db() as db:
        transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not transcript:
            return jsonify({"error": "Transcript not found"}), 404

        if transcript.analysis:
            db.delete(transcript.analysis)
            db.flush()

        result = analyze_transcript(
            transcript.company_name,
            transcript.transcript_text,
            call_date=transcript.call_date.strftime("%b %d, %Y") if transcript.call_date else None,
            duration=transcript.duration,
        )

        analysis = TranscriptAnalysis(
            transcript_id=transcript.id,
            raw_response=result["raw_response"],
            use_case_category=result.get("use_case_category"),
            presales_stage=result.get("presales_stage"),
            sfdc_use_case_description=result.get("sfdc_use_case_description"),
            sfdc_solutions_notes=result.get("sfdc_solutions_notes"),
            sfdc_technical_risks=result.get("sfdc_technical_risks"),
            model_used=result.get("model_used"),
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            cost_usd=result.get("cost_usd"),
        )
        db.add(analysis)
        transcript.status = "analyzed"
        db.flush()
        return jsonify(_transcript_analysis_to_dict(analysis))
