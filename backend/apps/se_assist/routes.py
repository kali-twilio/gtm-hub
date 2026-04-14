"""
SE Assist — Flask Blueprint.
AI-powered Gong call analysis for SFDC opportunity updates.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections import namedtuple
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm import joinedload

from .database import get_db, init_db
from .models import (
    AIAnalysis,
    GongEmail,
    SFDCSync,
    Transcript,
    TranscriptAnalysis,
    User,
)
from .services.claude_analysis import analyze_gong_email, analyze_transcript
from .services.email_parser import parse_call_date, parse_eml

log = logging.getLogger(__name__)

bp = Blueprint("se_assist", __name__)

ADMIN_EMAIL = os.environ.get("SE_ASSIST_ADMIN_EMAIL", "cchin@twilio.com")

# Initialize database tables on import
init_db()

# Lightweight user info that doesn't require an open DB session
UserInfo = namedtuple("UserInfo", ["id", "email", "name"])


# ---------------------------------------------------------------------------
# SE Assist user profile
# ---------------------------------------------------------------------------

@bp.route("/api/se_assist/me", methods=["GET"])
def se_assist_me():
    email = session.get("user_email")
    if not email:
        return jsonify({"detail": "Not authenticated"}), 401
    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return jsonify({"name": email.split("@")[0], "email": email})
        return jsonify({"name": user.name, "email": user.email})
    finally:
        db.close()

@bp.route("/api/se_assist/me", methods=["PUT"])
def update_se_assist_me():
    email = session.get("user_email")
    if not email:
        return jsonify({"detail": "Not authenticated"}), 401
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"detail": "name is required"}), 400
    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=name)
            db.add(user)
        else:
            user.name = name
        db.commit()
        return jsonify({"name": user.name, "email": user.email})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_user():
    """Bridge gtm-hub session auth to se-assist User model.
    Returns (UserInfo, None) on success or (None, error_response) on failure.
    """
    email = session.get("user_email")
    if not email:
        return None, (jsonify({"detail": "Not authenticated"}), 401)
    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            name = session.get("sf_display_name") or email.split("@")[0]
            user = User(email=email, name=name)
            db.add(user)
            db.commit()
            db.refresh(user)
        # Keep name in sync with session (e.g. sf_display_name from Salesforce)
        sf_name = session.get("sf_display_name")
        if sf_name and user.name != sf_name:
            user.name = sf_name
        user.last_login = datetime.utcnow()
        db.commit()
        # Extract values while session is still open
        info = UserInfo(id=user.id, email=user.email, name=user.name)
        return info, None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _can_delete(user: UserInfo, owner_id: int) -> bool:
    return user.email == ADMIN_EMAIL or user.id == owner_id


def _email_to_dict(e: GongEmail) -> dict:
    return {
        c.name: getattr(e, c.name)
        for c in GongEmail.__table__.columns
    } | {
        "uploaded_by_name": e.user.name if e.user else None,
    }


def _transcript_to_dict(t: Transcript) -> dict:
    return {
        c.name: getattr(t, c.name)
        for c in Transcript.__table__.columns
    } | {
        "uploaded_by_name": t.user.name if t.user else None,
    }


def _analysis_to_dict(a) -> dict:
    return {c.name: getattr(a, c.name) for c in a.__class__.__table__.columns}


def _serialize(obj):
    """JSON-safe serialization for datetime values."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Email routes
# ---------------------------------------------------------------------------

@bp.route("/api/se_assist/emails/", methods=["GET"])
def list_emails():
    status = request.args.get("status")
    uploaded_by = request.args.get("uploaded_by", type=int)
    skip = max(request.args.get("skip", 0, type=int), 0)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 100)

    db = get_db()
    try:
        query = db.query(GongEmail).options(joinedload(GongEmail.user))
        if status:
            query = query.filter(GongEmail.status == status)
        if uploaded_by:
            query = query.filter(GongEmail.user_id == uploaded_by)

        total = query.count()
        emails = query.order_by(GongEmail.received_at.desc()).offset(skip).limit(limit).all()

        return jsonify(_serialize({
            "emails": [_email_to_dict(e) for e in emails],
            "total": total,
        }))
    finally:
        db.close()


@bp.route("/api/se_assist/emails/uploaders", methods=["GET"])
def list_email_uploaders():
    db = get_db()
    try:
        rows = (
            db.query(User.id, User.name)
            .join(GongEmail, GongEmail.user_id == User.id)
            .distinct()
            .order_by(User.name)
            .all()
        )
        return jsonify([{"id": r.id, "name": r.name} for r in rows])
    finally:
        db.close()


@bp.route("/api/se_assist/emails/<int:email_id>", methods=["GET"])
def get_email(email_id: int):
    db = get_db()
    try:
        email_obj = (
            db.query(GongEmail)
            .options(joinedload(GongEmail.user))
            .filter(GongEmail.id == email_id)
            .first()
        )
        if not email_obj:
            return jsonify({"detail": "Email not found"}), 404
        return jsonify(_serialize(_email_to_dict(email_obj)))
    finally:
        db.close()


@bp.route("/api/se_assist/emails/upload", methods=["POST"])
def upload_eml():
    user, err = _current_user()
    if err:
        return err

    file = request.files.get("file")
    if not file or not file.filename or not file.filename.endswith(".eml"):
        return jsonify({"detail": "Please upload a .eml file"}), 400

    raw_bytes = file.read()
    result = parse_eml(raw_bytes)
    parsed = result["parsed_data"]
    call_date = parse_call_date(parsed.get("call_date"))

    msg_id = result.get("message_id") or f"upload-{uuid.uuid4().hex[:12]}"
    msg_id = f"{msg_id}-{uuid.uuid4().hex[:8]}"

    db = get_db()
    try:
        gong_email = GongEmail(
            user_id=user.id,
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
        db.commit()
        db.refresh(gong_email)
        return jsonify({"message": "Email uploaded", "email_id": gong_email.id})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/emails/<int:email_id>", methods=["DELETE"])
def delete_email(email_id: int):
    user, err = _current_user()
    if err:
        return err

    db = get_db()
    try:
        email_obj = db.query(GongEmail).filter(GongEmail.id == email_id).first()
        if not email_obj:
            return jsonify({"detail": "Email not found"}), 404
        if not _can_delete(user, email_obj.user_id):
            return jsonify({"detail": "Only the uploader or admin can delete this email"}), 403
        db.delete(email_obj)
        db.commit()
        return jsonify({"message": "Email deleted"})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/emails/seed-demo", methods=["POST"])
def seed_demo():
    user, err = _current_user()
    if err:
        return err

    fixture_path = Path(__file__).parent / "fixtures" / "continental_finance.eml"
    with open(fixture_path, "rb") as f:
        result = parse_eml(f.read())

    parsed = result["parsed_data"]
    call_date = parse_call_date(parsed.get("call_date"))
    msg_id = f"demo-continental-finance-{uuid.uuid4().hex[:8]}"

    db = get_db()
    try:
        gong_email = GongEmail(
            user_id=user.id,
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
        db.commit()
        db.refresh(gong_email)
        return jsonify({"message": "Demo seeded", "email_id": gong_email.id})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Analysis routes
# ---------------------------------------------------------------------------

@bp.route("/api/se_assist/analysis/<int:email_id>", methods=["POST"])
def run_analysis(email_id: int):
    db = get_db()
    try:
        gong_email = db.query(GongEmail).filter(GongEmail.id == email_id).first()
        if not gong_email:
            return jsonify({"detail": "Email not found"}), 404

        if gong_email.analysis:
            return jsonify({"detail": "Analysis already exists. Use PUT to update."}), 409

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
        db.commit()
        db.refresh(analysis)

        return jsonify(_serialize(_analysis_to_dict(analysis)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/analysis/<int:email_id>", methods=["GET"])
def get_analysis(email_id: int):
    db = get_db()
    try:
        analysis = db.query(AIAnalysis).filter(AIAnalysis.gong_email_id == email_id).first()
        if not analysis:
            return jsonify({"detail": "Analysis not found"}), 404
        return jsonify(_serialize(_analysis_to_dict(analysis)))
    finally:
        db.close()


@bp.route("/api/se_assist/analysis/<int:analysis_id>", methods=["PUT"])
def update_analysis(analysis_id: int):
    db = get_db()
    try:
        analysis = db.query(AIAnalysis).filter(AIAnalysis.id == analysis_id).first()
        if not analysis:
            return jsonify({"detail": "Analysis not found"}), 404

        data = request.get_json() or {}
        for key in ("use_case_category", "presales_stage", "sfdc_use_case_description",
                     "sfdc_solutions_notes", "sfdc_technical_risks"):
            if key in data:
                setattr(analysis, key, data[key])

        db.commit()
        db.refresh(analysis)
        return jsonify(_serialize(_analysis_to_dict(analysis)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/analysis/<int:email_id>/rerun", methods=["POST"])
def rerun_analysis(email_id: int):
    db = get_db()
    try:
        gong_email = db.query(GongEmail).filter(GongEmail.id == email_id).first()
        if not gong_email:
            return jsonify({"detail": "Email not found"}), 404

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
        db.commit()
        db.refresh(analysis)

        return jsonify(_serialize(_analysis_to_dict(analysis)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Transcript routes
# ---------------------------------------------------------------------------

@bp.route("/api/se_assist/transcripts/", methods=["GET"])
def list_transcripts():
    uploaded_by = request.args.get("uploaded_by", type=int)
    skip = max(request.args.get("skip", 0, type=int), 0)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 100)

    db = get_db()
    try:
        query = db.query(Transcript).options(joinedload(Transcript.user))
        if uploaded_by:
            query = query.filter(Transcript.user_id == uploaded_by)

        total = query.count()
        transcripts = query.order_by(Transcript.created_at.desc()).offset(skip).limit(limit).all()

        return jsonify(_serialize({
            "transcripts": [_transcript_to_dict(t) for t in transcripts],
            "total": total,
        }))
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/uploaders", methods=["GET"])
def list_transcript_uploaders():
    db = get_db()
    try:
        rows = (
            db.query(User.id, User.name)
            .join(Transcript, Transcript.user_id == User.id)
            .distinct()
            .order_by(User.name)
            .all()
        )
        return jsonify([{"id": r.id, "name": r.name} for r in rows])
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/<int:transcript_id>", methods=["GET"])
def get_transcript(transcript_id: int):
    db = get_db()
    try:
        obj = (
            db.query(Transcript)
            .options(joinedload(Transcript.user))
            .filter(Transcript.id == transcript_id)
            .first()
        )
        if not obj:
            return jsonify({"detail": "Transcript not found"}), 404
        return jsonify(_serialize(_transcript_to_dict(obj)))
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/", methods=["POST"])
def create_transcript():
    user, err = _current_user()
    if err:
        return err

    data = request.get_json() or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"detail": "company_name is required"}), 400
    transcript_text = data.get("transcript_text", "").strip()
    if not transcript_text:
        return jsonify({"detail": "transcript_text is required"}), 400

    call_date = parse_call_date(data.get("call_date")) if data.get("call_date") else None

    db = get_db()
    try:
        transcript = Transcript(
            user_id=user.id,
            company_name=company_name,
            call_date=call_date,
            duration=data.get("duration"),
            transcript_text=transcript_text,
            status="uploaded",
        )
        db.add(transcript)
        db.commit()
        db.refresh(transcript)

        return jsonify(_serialize(
            _transcript_to_dict(transcript) | {"uploaded_by_name": user.name}
        ))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/<int:transcript_id>", methods=["DELETE"])
def delete_transcript(transcript_id: int):
    user, err = _current_user()
    if err:
        return err

    db = get_db()
    try:
        obj = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not obj:
            return jsonify({"detail": "Transcript not found"}), 404
        if not _can_delete(user, obj.user_id):
            return jsonify({"detail": "Only the uploader or admin can delete this transcript"}), 403
        db.delete(obj)
        db.commit()
        return jsonify({"message": "Transcript deleted"})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/<int:transcript_id>/analyze", methods=["POST"])
def run_transcript_analysis(transcript_id: int):
    db = get_db()
    try:
        transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not transcript:
            return jsonify({"detail": "Transcript not found"}), 404

        if transcript.analysis:
            return jsonify({"detail": "Analysis already exists. Use rerun endpoint."}), 409

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
        db.commit()
        db.refresh(analysis)

        return jsonify(_serialize(_analysis_to_dict(analysis)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/<int:transcript_id>/analysis", methods=["GET"])
def get_transcript_analysis(transcript_id: int):
    db = get_db()
    try:
        analysis = db.query(TranscriptAnalysis).filter(
            TranscriptAnalysis.transcript_id == transcript_id
        ).first()
        if not analysis:
            return jsonify({"detail": "Analysis not found"}), 404
        return jsonify(_serialize(_analysis_to_dict(analysis)))
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/analysis/<int:analysis_id>", methods=["PUT"])
def update_transcript_analysis(analysis_id: int):
    db = get_db()
    try:
        analysis = db.query(TranscriptAnalysis).filter(TranscriptAnalysis.id == analysis_id).first()
        if not analysis:
            return jsonify({"detail": "Analysis not found"}), 404

        data = request.get_json() or {}
        for key in ("use_case_category", "presales_stage", "sfdc_use_case_description",
                     "sfdc_solutions_notes", "sfdc_technical_risks"):
            if key in data:
                setattr(analysis, key, data[key])

        db.commit()
        db.refresh(analysis)
        return jsonify(_serialize(_analysis_to_dict(analysis)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@bp.route("/api/se_assist/transcripts/<int:transcript_id>/rerun", methods=["POST"])
def rerun_transcript_analysis(transcript_id: int):
    db = get_db()
    try:
        transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not transcript:
            return jsonify({"detail": "Transcript not found"}), 404

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
        db.commit()
        db.refresh(analysis)

        return jsonify(_serialize(_analysis_to_dict(analysis)))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Audit routes
# ---------------------------------------------------------------------------

@bp.route("/api/se_assist/audit/", methods=["GET"])
def list_syncs():
    user_id = request.args.get("user_id", type=int)
    skip = max(request.args.get("skip", 0, type=int), 0)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 100)

    db = get_db()
    try:
        query = db.query(SFDCSync).options(
            joinedload(SFDCSync.user),
            joinedload(SFDCSync.gong_email),
        )
        if user_id:
            query = query.filter(SFDCSync.user_id == user_id)

        total = query.count()
        syncs = query.order_by(SFDCSync.synced_at.desc()).offset(skip).limit(limit).all()

        entries = []
        for sync in syncs:
            entries.append({
                "id": sync.id,
                "user_name": sync.user.name,
                "company_name": sync.gong_email.company_name if sync.gong_email else None,
                "sfdc_opportunity_name": sync.sfdc_opportunity_name,
                "status": sync.status,
                "fields_sent": sync.fields_sent,
                "synced_at": sync.synced_at,
            })

        return jsonify(_serialize({"syncs": entries, "total": total}))
    finally:
        db.close()
