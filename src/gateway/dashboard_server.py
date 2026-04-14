"""
Mina Dashboard Server — FastAPI sidecar.

Exposes biological state read/write, heartbeat trigger, substance management,
token usage, events, and simulation advance over HTTP.

Run:
  uv run python dashboard_server.py [--port 7843]

The built SvelteKit dashboard is served as a static SPA from dashboard/build/.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

_DOTENV = find_dotenv(usecwd=True)
load_dotenv(_DOTENV)
_PROJECT_ROOT = Path(os.path.dirname(_DOTENV))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

import uvicorn

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_STATE_FILE      = _PROJECT_ROOT / "run" / "state.json"
_DASHBOARD_BUILD = _PROJECT_ROOT / "dashboard" / "build"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")


def _check_auth(request: Request) -> None:
    if not DASHBOARD_TOKEN:
        return  # No token configured — open access (dev mode)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Mina Dashboard", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz():
    return {"ok": True, "auth_required": bool(DASHBOARD_TOKEN)}


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

# Body fields that can be directly patched
_BODY_PATCHABLE = {"adenosine", "anandamide", "two_ag"}
_BODY_CLAMP = {
    "adenosine":  (15.0, 100.0),
    "anandamide": (0.0,  5.0),
    "two_ag":     (0.0,  30.0),
}

# Mapping: flat API key → (nt_name, receptor_type) for receptor_sensitivity
_RECEPTOR_FLAT_MAP = {
    "d1":    ("dopamine",    "D1"),
    "d2":    ("dopamine",    "D2"),
    "d3":    ("dopamine",    "D3"),
    "ht1a":  ("serotonin",   "5HT1A"),
    "ht2a":  ("serotonin",   "5HT2A"),
    "ht3":   ("serotonin",   "5HT3"),
    "gabaa": ("gaba",        "GABA_A"),
    "gabab": ("gaba",        "GABA_B"),
    "nmda":  ("glutamate",   "NMDA"),
    "ampa":  ("glutamate",   "AMPA"),
    "cb1":   ("anandamide",  "CB1"),
    "cb2":   ("anandamide",  "CB2"),
    "a1":    ("adenosine",   "A1"),
    "a2a":   ("adenosine",   "A2A"),
}


def _flatten_receptors(rs: dict) -> dict:
    """Flatten nested receptor_sensitivity dict to flat key → float."""
    out = {}
    for flat_key, (nt, rtype) in _RECEPTOR_FLAT_MAP.items():
        out[flat_key] = round(rs.get(nt, {}).get(rtype, 1.0), 4)
    return out


def _build_state_response(s) -> dict:
    """Build the full v3 state response dict from a BiologicalState."""
    from ..bio.chemicals import REGISTRY, normalize, get_label
    from ..sim.psych.derived import derived

    d = derived(s)

    # Tier 1: chemicals (REGISTRY-driven)
    chemicals_out = {}
    for name, profile in REGISTRY.items():
        val = s.chemicals.get(name, 0.0)
        lbl, _ = get_label(name, val)
        chemicals_out[name] = {
            "value":      round(val, 2),
            "unit":       profile.unit,
            "label":      lbl,
            "normalized": round(normalize(name, val), 4),
        }

    # Vital signs
    vs_out = {}
    try:
        from ..bio.vital_signs import vital_signs as _vitals
        vs_out = _vitals(s)
    except Exception:
        pass

    # Neuroendocrine (raw, real units)
    ne = s.neuroendocrine
    neuroendocrine_out = {
        "crh":            round(ne.get("crh",          30.0), 2),
        "acth":           round(ne.get("acth",         25.0), 2),
        "tsh":            round(ne.get("tsh",           2.0), 3),
        "t4":             round(ne.get("t4",            8.0), 2),
        "t3":             round(ne.get("t3",          120.0), 1),
        "estradiol":      round(ne.get("estradiol",   100.0), 1),
        "progesterone":   round(ne.get("progesterone",  0.5), 3),
        "testosterone":   round(ne.get("testosterone", 40.0), 1),
        "ghrelin":        round(ne.get("ghrelin",     400.0), 1),
        "leptin":         round(ne.get("leptin",       15.0), 2),
        "insulin":        round(ne.get("insulin",       5.0), 2),
        "vasopressin":    round(ne.get("vasopressin",   2.0), 3),
        "prolactin":      round(ne.get("prolactin",     8.0), 2),
        "growth_hormone": round(ne.get("growth_hormone",1.0), 3),
        "dhea":           round(ne.get("dhea",        150.0), 1),
        "orexin":         round(ne.get("orexin",      300.0), 1),
    }

    # Immune (inflammation_index normalized 0-1)
    im = s.immune
    raw_infl = im.get("inflammation_index", 0.0)
    immune_out = {
        "il1b":              round(im.get("il1b",     2.0), 2),
        "il6":               round(im.get("il6",      3.0), 2),
        "tnf_alpha":         round(im.get("tnf_alpha",3.0), 2),
        "crp":               round(im.get("crp",      0.5), 3),
        "il10":              round(im.get("il10",    10.0), 2),
        "inflammation_index": round(min(1.0, raw_infl / 100.0), 4),
    }

    # Pain (pain_intensity + central_sensitization normalized 0-1)
    pa = s.pain
    vagal_raw = s.body.get("vagal_tone", 55.0)
    pain_out = {
        "substance_p":          round(pa.get("substance_p",          30.0), 1),
        "pge2":                 round(pa.get("pge2",                  80.0), 1),
        "pain_intensity":       round(min(1.0, pa.get("pain_intensity",      0.0) / 100.0), 4),
        "central_sensitization":round(min(1.0, pa.get("central_sensitization",0.0) / 100.0), 4),
        "vagal_tone":           round(min(1.0, vagal_raw / 100.0), 4),
    }

    # Neuroplasticity (bdnf: pg/mL → ng/mL; others: 0-100 → 0-1)
    np_ = s.neuroplasticity
    bdnf_ng = round(np_.get("bdnf", 9000.0) / 1000.0, 3)
    al_01   = round(min(1.0, np_.get("allostatic_load",        0.0) / 100.0), 4)
    sp_01   = round(min(1.0, np_.get("synaptic_potentiation", 50.0) / 100.0), 4)
    neuroplasticity_out = {
        "bdnf":                  bdnf_ng,
        "synaptic_potentiation": sp_01,
        "allostatic_load":       al_01,
    }

    # Personality drift (if any)
    personality_drift = {}
    for key in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
        drift = s.neuroplasticity.get(f"{key}_drift")
        if drift is not None:
            personality_drift[key] = round(drift, 4)

    # Body / circadian
    b = s.body
    lt = time.localtime()
    current_hour = lt.tm_hour + lt.tm_min / 60.0 + lt.tm_sec / 3600.0
    circadian_phase = round(current_hour / 24.0, 4)
    body_out = {
        "core_temp":          round(b.get("core_temp",          37.0), 2),
        "adenosine":          round(b.get("adenosine",          38.0), 2),
        "anandamide":         round(b.get("anandamide",          1.5), 3),
        "two_ag":             round(b.get("two_ag",              8.0), 2),
        "isolation_pressure": round(b.get("isolation_pressure",  0.0), 1),
        "recent_contact_ts":  round(b.get("recent_contact_ts",   0.0), 0),
        "circadian_phase":    circadian_phase,
    }

    # Receptor sensitivity (flattened)
    receptor_sensitivity_out = _flatten_receptors(s.receptor_sensitivity or {})

    # Cascade queue (map target/fires_at/delta → type/fires_at_unix/magnitude)
    cascade_out = []
    for ev in (s.cascade_queue or []):
        cascade_out.append({
            "type":         ev.get("target", "unknown"),
            "fires_at_unix": ev.get("fires_at", 0.0),
            "magnitude":    ev.get("delta",  0.0),
        })

    return {
        "chemicals":          chemicals_out,
        "sleeping":           s.sleeping,
        "second_order":       d["second_order"],
        "third_order":        d["third_order"],
        "vital_signs":        vs_out,
        "neuroendocrine":     neuroendocrine_out,
        "immune":             immune_out,
        "pain":               pain_out,
        "neuroplasticity":    neuroplasticity_out,
        "personality_drift":  personality_drift,
        "body":               body_out,
        "receptor_sensitivity": receptor_sensitivity_out,
        "cascade_queue":      cascade_out,
        "allostatic_load":    al_01,
        "cycle_day":          max(0, int(s.cycle_day) - 1),  # 0-indexed, 0-27
    }


# ---------------------------------------------------------------------------
# State endpoints
# ---------------------------------------------------------------------------

@app.get("/api/state")
def get_state(request: Request):
    _check_auth(request)
    from ..bio.state import load_state
    s = load_state()
    return _build_state_response(s)


class StatePatch(BaseModel):
    model_config = ConfigDict(extra="allow")  # accepts any field name


@app.patch("/api/state")
def patch_state(body: StatePatch, request: Request):
    _check_auth(request)
    from ..bio.state import load_state, save_state, advance
    from ..bio.chemicals import REGISTRY, clamp_chemical

    s = advance(load_state())
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()
               if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail="No fields provided")

    for field, value in updates.items():
        if field in REGISTRY:
            s.chemicals[field] = clamp_chemical(field, float(value))
        elif field in _BODY_PATCHABLE:
            lo, hi = _BODY_CLAMP[field]
            s.body[field] = round(max(lo, min(hi, float(value))), 4)

    save_state(s)
    return {"ok": True, "updated": list(updates.keys())}


class AdvanceBody(BaseModel):
    hours: float


@app.post("/api/state/advance")
def post_advance_state(body: AdvanceBody, request: Request):
    _check_auth(request)
    from ..bio.state import load_state, save_state

    hours = max(0.0, min(24.0, body.hours))
    if hours == 0:
        raise HTTPException(status_code=422, detail="hours must be > 0")

    try:
        cfg_path = _PROJECT_ROOT / "config.json"
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    except Exception:
        cfg = {}
    compression = float(cfg.get("time_compression_factor", 1.0)) or 1.0

    s = load_state()
    # Backdate last_updated so advance() computes sim_hours = requested hours
    s.last_updated = time.time() - (hours * 3600.0 / compression)

    from ..sim.engine import advance as bio_advance
    s = bio_advance(s)
    save_state(s)
    return _build_state_response(s)


# ---------------------------------------------------------------------------
# Heartbeat / reflection trigger
# ---------------------------------------------------------------------------

_heartbeat_running = False


@app.post("/api/heartbeat")
async def trigger_heartbeat(request: Request):
    _check_auth(request)
    global _heartbeat_running
    if _heartbeat_running:
        raise HTTPException(status_code=409, detail="Heartbeat already running")
    _heartbeat_running = True
    try:
        from ..runtime.freetime import run_freetime
        await run_freetime(force=True)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _heartbeat_running = False


@app.get("/api/heartbeat/status")
def heartbeat_status(request: Request):
    _check_auth(request)
    return {"running": _heartbeat_running}


# ---------------------------------------------------------------------------
# xAI billing
# ---------------------------------------------------------------------------

@app.get("/api/billing")
def get_billing(request: Request):
    _check_auth(request)
    import urllib.request as _urllib

    management_key = os.getenv("XAI_MANAGEMENT_KEY", "")
    team_id        = os.getenv("XAI_TEAM_ID", "")

    if not management_key or not team_id:
        return {"error": "billing_not_configured"}

    url = f"https://management-api.x.ai/v1/billing/teams/{team_id}/postpaid/invoice/preview"
    try:
        req = _urllib.Request(url, headers={
                "Authorization": f"Bearer {management_key}",
                "User-Agent": "Mozilla/5.0",
            })
        with _urllib.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        cap       = float(data["effectiveSpendingLimit"]) / 100
        used      = float(data["coreInvoice"]["amountBeforeVat"]) / 100
        remaining = cap - used
        return {"cap": round(cap, 2), "used": round(used, 2), "remaining": round(remaining, 2)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

@app.get("/api/tokens")
def get_tokens(request: Request):
    _check_auth(request)
    from ..infra import token_stats
    return token_stats.get()


# ---------------------------------------------------------------------------
# Substances
# ---------------------------------------------------------------------------

@app.get("/api/substance")
def get_substances(request: Request):
    _check_auth(request)
    from ..sim.neuro.substances import SUBSTANCE_DEFS
    from ..bio.state import load_state
    s = load_state()
    result = {}
    for name, sub in SUBSTANCE_DEFS.items():
        dose = s.substances.get(name, {})
        result[name] = {
            "display_name": sub["display_name"],
            "level":        round(dose.get("level", 0), 1) if dose else 0.0,
            "active":       name in s.substances,
            "half_life_hours": sub["half_life_hours"],
        }
    return result


@app.post("/api/substance/{name}/dose")
def dose_substance(name: str, request: Request):
    _check_auth(request)
    from ..sim.neuro.substances import SUBSTANCE_DEFS
    from ..bio.state import load_state, save_state, advance

    sub = SUBSTANCE_DEFS.get(name)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Unknown substance: {name}")

    s = advance(load_state())

    for marker, delta in sub["dose_effects"].items():
        if marker in s.chemicals:
            s.chemicals[marker] = max(0.0, s.chemicals[marker] + float(delta))

    current_level = s.substances.get(name, {}).get("level", 0)
    s.substances[name] = {"level": min(100.0, current_level + 100.0)}

    save_state(s)
    return {"ok": True, "substance": name, "level": s.substances[name]["level"]}


@app.delete("/api/substance/{name}")
def clear_substance(name: str, request: Request):
    _check_auth(request)
    from ..bio.state import load_state, save_state
    s = load_state()
    s.substances.pop(name, None)
    save_state(s)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Encoder events
# ---------------------------------------------------------------------------

@app.get("/api/events")
def get_events(request: Request, limit: int = 150):
    _check_auth(request)
    from ..infra.events import read_events
    return read_events(limit=min(limit, 300))


# ---------------------------------------------------------------------------
# SPA static file serving
# ---------------------------------------------------------------------------

if _DASHBOARD_BUILD.exists():
    _app_dir = _DASHBOARD_BUILD / "_app"
    if _app_dir.exists():
        app.mount("/_app", StaticFiles(directory=str(_app_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        candidate = _DASHBOARD_BUILD / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        index = _DASHBOARD_BUILD / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"detail": "Dashboard not built yet. Run: cd dashboard && npm run build"}, status_code=503)
else:
    @app.get("/")
    def root():
        return JSONResponse(
            {"detail": "Dashboard not built. Run: cd dashboard && npm run build"},
            status_code=503,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7843)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"Mina Dashboard starting on http://{args.host}:{args.port}")
    if not DASHBOARD_TOKEN:
        print("  WARNING: DASHBOARD_TOKEN not set — running without auth")
    if not _DASHBOARD_BUILD.exists():
        print("  INFO: dashboard/build/ not found — UI not yet built")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
