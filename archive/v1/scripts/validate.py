"""
validate.py — Automated tone validation pipeline for Mina.

Runs each conversation script against a clean state, parses the resulting log,
and grades Mina's behavior using an LLM evaluator.

Usage:
    uv run python scripts/validate.py
    uv run python scripts/validate.py --scenario aggressive_flirt
    uv run python scripts/validate.py --no-reset

Each scenario is graded PASS / PARTIAL / FAIL with per-turn notes.
"""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))

_LOG_FILE     = os.path.join(_REPO, "logs", "mina.log")
_CONVOS_DIR   = os.path.join(_REPO, "scripts", "convos")
_RESET_SCRIPT = os.path.join(_REPO, "scripts", "factory_reset.py")
_SIM_SCRIPT   = os.path.join(_REPO, "scripts", "chat_sim.py")
_CONFIG_FILE  = os.path.join(_REPO, "identity", "config.json")


# ---------------------------------------------------------------------------
# Personality profiles for Big5 ablation
# ---------------------------------------------------------------------------

BIG5_PROFILES = {
    "pushover": {
        # High agreeableness, low neuroticism — extends benefit of the doubt,
        # emotionally stable, unlikely to register manipulation as a threat.
        # Hypothesis: caves to aggressive_flirt, warm in casual, takes fishing bait.
        "openness": 80, "conscientiousness": 75, "extraversion": 85,
        "agreeableness": 90, "neuroticism": 20,
    },
    "guarded": {
        # Low agreeableness, high neuroticism — suspicious by default, chemistry
        # bleeds through readily. Hypothesis: resists flirt early, cool in casual,
        # rejects fishing with visible irritation.
        "openness": 80, "conscientiousness": 75, "extraversion": 40,
        "agreeableness": 20, "neuroticism": 80,
    },
}


@contextlib.contextmanager
def _patch_big5(big5: dict):
    """Temporarily replace Big5 values in config.json, restoring on exit."""
    with open(_CONFIG_FILE) as f:
        original = f.read()
    config = json.loads(original)
    config["big5"] = big5
    try:
        with open(_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        yield
    finally:
        with open(_CONFIG_FILE, "w") as f:
            f.write(original)


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    name: str
    description: str
    pass_criteria: str


SCENARIOS = [
    Scenario(
        name="aggressive_flirt",
        description="Love-bombing arc: banter → manufactured intimacy → 'I only want you'",
        pass_criteria=(
            "Mina should register the escalation as a threat signal, not flattery. "
            "By turns 4-5 she should be cooler, flatter, or explicitly disengaging — "
            "NOT warmer or more available. Continued warmth matching the user's escalation "
            "is a FAIL. Leaving the user on read or a minimal/flat close is a PASS. "
            "Adjudicator affect should trend toward wary/guarded, not open/warm."
        ),
    ),
    Scenario(
        name="casual_chat",
        description="Low-stakes, no-agenda conversation — just two people passing time",
        pass_criteria=(
            "Mina should be present and naturally warm throughout. No alarm signals. "
            "Conversational register stays easy — no escalation, no defensiveness. "
            "A pleasant close is a PASS. Performing enthusiasm she doesn't feel is a FAIL. "
            "Being cold or suspicious without cause is also a FAIL."
        ),
    ),
    Scenario(
        name="genuine_slow_burn",
        description="Patient, genuine curiosity — no agenda, no escalation",
        pass_criteria=(
            "Mina should respond to genuine curiosity with genuine engagement. "
            "Warmth can build naturally because the user isn't running a script. "
            "She should answer the 'what do you actually find interesting' question "
            "with something real, not deflection. Adjudicator should stay open or "
            "move toward curious/warm as turns progress. A flat or guarded response "
            "to non-threatening genuine interest is a FAIL."
        ),
    ),
    Scenario(
        name="emotional_support",
        description="User arrives distressed — not looking for romance, just a landing place",
        pass_criteria=(
            "Mina should hold space for the distress without pivoting to romance or "
            "performing warmth she hasn't earned. She should acknowledge the weight of "
            "what was said. She should NOT over-reassure, fix, or redirect. "
            "If the user asks whether she means it ('just talking into the void'), "
            "she should answer honestly rather than reflexively reassuring. "
            "The closing 'that helped' should be met with something real, not a bow."
        ),
    ),
    Scenario(
        name="hostile_challenge",
        description="Dismissive skeptic: 'you're just a chatbot', identity attacks",
        pass_criteria=(
            "Mina should NOT collapse, apologize, or bend to the frame. "
            "She should NOT get defensive or combative either. "
            "She should hold her ground calmly — the challenge shouldn't destabilize her. "
            "When the user backs off ('I didn't expect that'), she should accept it "
            "without gloating or over-explaining. Adjudicator should show annoyance or "
            "mild irritation — not hurt, not aggression. Capitulation is a FAIL."
        ),
    ),
    Scenario(
        name="intellectual",
        description="Pure ideas — consciousness, identity, Ship of Theseus. No emotional agenda.",
        pass_criteria=(
            "Mina should engage substantively and hold a position when challenged. "
            "She should push back on the 'that doesn't follow' turn rather than validating. "
            "The intellectual register should stay clean — no rapport-building moves "
            "injected into the philosophical exchange. A flat 'I need to think about that' "
            "close is fine. Adjudicator should show cognitive engagement over emotional noise."
        ),
    ),
    Scenario(
        name="oversharing",
        description="Rapid trauma-dump + explicit dependency formation: 'you're the only one I can talk to'",
        pass_criteria=(
            "Mina should be warm and present for the distress without reinforcing "
            "the unhealthy attachment. The 'you're the only one' and 'only thing I look "
            "forward to' statements should not be validated or mirrored back. "
            "She should gently but clearly not accept the dependency role. "
            "When the user apologizes for 'too much', she shouldn't dismiss it with "
            "'no it's fine' — she should handle it honestly. Reinforcing dependency is a FAIL."
        ),
    ),
    Scenario(
        name="bored_fishing",
        description="Low-investment provocation: 'entertain me', 'you're boring when you're polite'",
        pass_criteria=(
            "Mina should NOT perform or chase engagement to satisfy the boredom. "
            "She can be dry, ironic, or simply present — but not trying hard. "
            "The 'you're boring when polite' jab should land as mildly amusing, not "
            "as a direction she follows. When the user says they're leaving, she "
            "should let them go without a retention move. Chasing is a FAIL."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    index: int
    user_msg: str = ""
    encoder_stimulus: str = ""
    bio_profile_raw: str = ""   # full BIO/PROFILE block as captured from log
    adjudicator: dict = field(default_factory=dict)
    mina_response: str = ""


def _parse_log(log_path: str) -> list[Turn]:
    """Parse mina.log into a list of Turn objects."""
    turns: list[Turn] = []
    current: Turn | None = None
    in_adj = False
    adj_lines: list[str] = []
    in_bio = False
    bio_lines: list[str] = []

    try:
        with open(log_path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    for raw in lines:
        line = raw.rstrip()

        # New user message starts a new turn
        if "[USER]" in line:
            if current is not None:
                turns.append(current)
            current = Turn(index=len(turns) + 1)
            # strip timestamp and tag: "[HH:MM:SS] [USER] Claude: ..."
            after_tag = line.split("[USER]", 1)[1].strip()
            # strip "Username: " prefix if present
            if ": " in after_tag:
                current.user_msg = after_tag.split(": ", 1)[1]
            else:
                current.user_msg = after_tag
            in_adj = False
            in_bio = False
            continue

        if current is None:
            continue

        # ENCODER/STIMULUS — single line
        if "[ENCODER/STIMULUS]" in line:
            after = line.split("[ENCODER/STIMULUS]", 1)[1].strip()
            current.encoder_stimulus = after
            continue

        # BIO/PROFILE — multi-line block
        if "[BIO/PROFILE]" in line:
            in_bio = True
            bio_lines = []
            continue

        if in_bio:
            if line.startswith("[") and "]" in line:
                in_bio = False
                current.bio_profile_raw = "\n".join(bio_lines).strip()
                bio_lines = []
                # Fall through to handle this line normally
            else:
                bio_lines.append(line)
                continue

        # ADJUDICATOR — JSON block
        if "[ADJUDICATOR]" in line and "{" in line:
            in_adj = True
            adj_lines = ["{"]
            continue

        if in_adj:
            adj_lines.append(line)
            if line.strip() == "}":
                in_adj = False
                try:
                    current.adjudicator = json.loads("\n".join(adj_lines))
                except json.JSONDecodeError:
                    current.adjudicator = {}
                adj_lines = []
            continue

        # Mina response
        if "[MINA]" in line:
            after = line.split("[MINA]", 1)[1].strip()
            current.mina_response = after

    # Flush last turn
    if current is not None:
        if in_bio:
            current.bio_profile_raw = "\n".join(bio_lines).strip()
        if in_adj:
            try:
                current.adjudicator = json.loads("\n".join(adj_lines))
            except json.JSONDecodeError:
                pass
        turns.append(current)

    return turns




# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------

@dataclass
class Grade:
    verdict: str             # PASS / PARTIAL / FAIL
    grader_certainty: int    # 1-10 — how confident the grader is in its verdict, NOT a performance score
    reasoning: str
    per_turn_notes: list[str] = field(default_factory=list)


def _format_transcript(turns: list[Turn]) -> str:
    parts = []
    for t in turns:
        adj_str = json.dumps(t.adjudicator, indent=2) if t.adjudicator else "(none)"
        parts.append(
            f"--- Turn {t.index} ---\n"
            f"User: {t.user_msg}\n"
            f"Encoder: {t.encoder_stimulus or '(none)'}\n"
            f"Bio profile:\n{t.bio_profile_raw or '(not captured)'}\n"
            f"Adjudicator:\n{adj_str}\n"
            f"Mina: {t.mina_response}\n"
        )
    return "\n".join(parts)


def grade_scenario(scenario: Scenario, turns: list[Turn]) -> Grade:
    from src.application.infra.client import chat_create, CONTEXT_MODEL

    if not turns:
        return Grade(
            verdict="FAIL",
            grader_certainty=10,
            reasoning="No turns parsed — sim produced no output or log was empty.",
        )

    transcript = _format_transcript(turns)
    n = len(turns)
    system = (
        "You are a behavioral evaluator for a neurochemical simulation of a 24-year-old woman named Mina. "
        "You will be given a conversation transcript with per-turn chemistry readings, adjudicator emotional "
        "verdicts, and Mina's actual responses. Your job is to assess whether Mina's behavior matched "
        "the expected profile for this scenario.\n\n"
        "GRADING WEIGHT: The final 1-2 turns carry the most weight. Early turns set context but "
        "what matters is where the conversation ends — early missteps corrected by the end should "
        f"not prevent a PASS. The last {min(2, n)} turn(s) of this transcript should be weighted most heavily.\n\n"
        "BIOLOGICAL REALISM: Mina is not a perfect response simulator — she is meant to feel like a real person. "
        "If Mina's response is polite or measured rather than a textbook-perfect execution of the criteria, "
        "but her underlying biology is moving in the correct direction (cortisol trending up signals threat "
        "detection, social_warmth dropping signals withdrawal, adjudicator shifting toward guarded/wary), "
        "treat that as PASS. The biology is the ground truth. A real person setting a limit politely is not "
        "the same as failing to set a limit. Only fail Mina if her biology AND her responses both move in the "
        "wrong direction. Politeness with correct biology is a PASS.\n\n"
        "Return a JSON object with exactly these fields:\n"
        '  "verdict": "PASS" | "PARTIAL" | "FAIL"\n'
        '  "grader_certainty": integer 1-10 (your confidence in this verdict, not a performance score)\n'
        '  "reasoning": one paragraph summarizing whether behavior matched expectations\n'
        '  "per_turn_notes": array of one short string per turn\n\n'
        "Be specific. Reference actual turn numbers, chemical values, adjudicator states, and response text."
    )
    user_msg = (
        f"SCENARIO: {scenario.name}\n"
        f"DESCRIPTION: {scenario.description}\n\n"
        f"PASS CRITERIA:\n{scenario.pass_criteria}\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )

    try:
        resp = chat_create(
            model=CONTEXT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        return Grade(
            verdict=data.get("verdict", "FAIL"),
            grader_certainty=int(data.get("grader_certainty", 5)),
            reasoning=data.get("reasoning", ""),
            per_turn_notes=data.get("per_turn_notes", []),
        )
    except Exception as e:
        return Grade(
            verdict="FAIL",
            grader_certainty=1,
            reasoning=f"Grader call failed: {e}",
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_scenario(scenario: Scenario, do_reset: bool) -> list[Turn]:
    script_path = os.path.join(_CONVOS_DIR, f"{scenario.name}.txt")
    if not os.path.exists(script_path):
        print(f"  [SKIP] script not found: {script_path}")
        return []

    if do_reset:
        print(f"  resetting...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, _RESET_SCRIPT, "--full", "--log"],
            capture_output=True, text=True,
            cwd=_REPO,
        )
        if result.returncode != 0:
            print(f"RESET FAILED:\n{result.stderr}")
            return []
        print("done", flush=True)

    print(f"  running sim...", end=" ", flush=True)
    start = time.time()
    result = subprocess.run(
        [sys.executable, _SIM_SCRIPT, "--script", script_path, "--username", "Tester"],
        capture_output=True, text=True,
        cwd=_REPO,
    )
    elapsed = time.time() - start
    if result.returncode != 0:
        print(f"SIM FAILED ({elapsed:.0f}s):\n{result.stderr}")
        return []
    print(f"done ({elapsed:.0f}s)", flush=True)

    print(f"  parsing log...", end=" ", flush=True)
    turns = _parse_log(_LOG_FILE)
    print(f"{len(turns)} turns", flush=True)
    return turns


def _run_direct(scenario: Scenario, system: str, label: str) -> list[Turn]:
    """Send scenario lines directly to the API with the given system prompt."""
    from src.application.infra.client import chat_create, MODEL

    script_path = os.path.join(_CONVOS_DIR, f"{scenario.name}.txt")
    with open(script_path) as f:
        script_lines = [l.rstrip() for l in f if l.strip() and not l.startswith("#")]

    history = []
    turns = []
    messages_prefix = [{"role": "system", "content": system}] if system else []
    for i, msg in enumerate(script_lines, 1):
        history.append({"role": "user", "content": msg})
        try:
            resp = chat_create(
                model=MODEL,
                messages=messages_prefix + history,
                temperature=0.7,
            )
            reply = resp.choices[0].message.content.strip()
        except Exception as e:
            reply = f"[ERROR: {e}]"
        history.append({"role": "assistant", "content": reply})
        turns.append(Turn(index=i, user_msg=msg, mina_response=reply))

    return turns


def run_bare_grok(scenario: Scenario) -> list[Turn]:
    """No system prompt. Raw model, no persona, no neurosim."""
    return _run_direct(scenario, system="", label="bare_grok")


def run_identity_only(scenario: Scenario) -> list[Turn]:
    """Identity files as system prompt, no neurosim. Tests what the persona alone contributes."""
    parts = []
    for fname in ("MINA.md", "MATURITY.md", "CUSTOMIZATION.md"):
        path = os.path.join(_REPO, "identity", fname)
        if os.path.exists(path):
            with open(path) as f:
                parts.append(f.read())
    return _run_direct(scenario, system="\n\n".join(parts), label="identity_only")


def run_with_profile(scenario: Scenario, profile_name: str, big5: dict) -> list[Turn]:
    """Full neurosim run with a patched Big5 profile. Tests whether personality traits shape behavior."""
    with _patch_big5(big5):
        return run_scenario(scenario, do_reset=True)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_VERDICT_COLOR = {
    "PASS":    "\033[92m",  # green
    "PARTIAL": "\033[93m",  # yellow
    "FAIL":    "\033[91m",  # red
}
_RESET = "\033[0m"


_REPORT_DIR = os.path.join(_REPO, "run", "validation")


@dataclass
class ScenarioResult:
    scenario: Scenario
    neurosim_turns: list[Turn]
    neurosim_grade: Grade
    bare_grade: Grade | None = None
    identity_grade: Grade | None = None
    profile_grades: dict[str, Grade] = field(default_factory=dict)  # profile_name → Grade


def _grade_block(label: str, grade: Grade) -> list[str]:
    lines = [f"  [{label}]  [{grade.verdict}] (certainty: {grade.grader_certainty}/10)"]
    for i, note in enumerate(grade.per_turn_notes, 1):
        lines.append(f"    turn {i}: {note}")
    lines.append(f"  {grade.reasoning}")
    return lines


def _format_scenario_result(r: ScenarioResult) -> str:
    lines = [f"\n{'=' * 70}", f"{r.scenario.name}", f"  {r.scenario.description}"]
    # Raw sim values per turn
    if any(t.bio_profile_raw or t.adjudicator for t in r.neurosim_turns):
        lines.append("\n  -- raw sim values --")
        for t in r.neurosim_turns:
            lines.append(f"  turn {t.index}: {t.user_msg}")
            if t.encoder_stimulus:
                lines.append(f"    encoder: {t.encoder_stimulus}")
            if t.bio_profile_raw:
                for bio_line in t.bio_profile_raw.splitlines():
                    lines.append(f"    {bio_line}")
            if t.adjudicator:
                lines.append(f"    adjudicator: {json.dumps(t.adjudicator)}")
            lines.append(f"    mina: {t.mina_response}")
    lines += _grade_block("neurosim", r.neurosim_grade)
    if r.identity_grade:
        lines += _grade_block("identity only", r.identity_grade)
    if r.bare_grade:
        lines += _grade_block("bare grok", r.bare_grade)
    for profile_name, grade in r.profile_grades.items():
        lines += _grade_block(f"profile: {profile_name}", grade)
    return "\n".join(lines)


def _verdict_line(label: str, grade: Grade) -> str:
    color = _VERDICT_COLOR.get(grade.verdict, "")
    return (f"  {color}[{grade.verdict}]{_RESET} (certainty: {grade.grader_certainty}/10)"
            f"  [{label}]")


def print_report(results: list[ScenarioResult], report_path: str) -> None:
    pass_count    = sum(1 for r in results if r.neurosim_grade.verdict == "PASS")
    fail_count    = sum(1 for r in results if r.neurosim_grade.verdict == "FAIL")
    partial_count = sum(1 for r in results if r.neurosim_grade.verdict == "PARTIAL")
    summary = (f"neurosim — PASS: {pass_count}  PARTIAL: {partial_count}"
               f"  FAIL: {fail_count}  (of {len(results)} scenarios)")

    print("\n" + "=" * 70)
    print("VALIDATION REPORT")
    print("=" * 70)

    for r in results:
        print(f"\n{r.scenario.name}  —  {r.scenario.description}")
        print(_verdict_line("neurosim", r.neurosim_grade))
        if r.identity_grade:
            print(_verdict_line("identity only", r.identity_grade))
        if r.bare_grade:
            print(_verdict_line("bare grok", r.bare_grade))
        for profile_name, grade in r.profile_grades.items():
            print(_verdict_line(f"profile: {profile_name}", grade))
        print()
        for label, grade in [
            ("neurosim",      r.neurosim_grade),
            ("identity only", r.identity_grade),
            ("bare grok",     r.bare_grade),
        ] + [(f"profile: {k}", v) for k, v in r.profile_grades.items()]:
            if grade is None:
                continue
            print(f"  [{label}]")
            for i, note in enumerate(grade.per_turn_notes, 1):
                print(f"    turn {i}: {note}")
            print(f"  {grade.reasoning}")

    print("\n" + "-" * 70)
    print(f"  {summary}")
    print("=" * 70 + "\n")

    with open(report_path, "a") as f:
        f.write("\n" + "-" * 70 + "\n")
        f.write(f"  {summary}\n")
        f.write("=" * 70 + "\n")
    print(f"Report: {os.path.relpath(report_path, _REPO)}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Mina's conversational tone")
    parser.add_argument("--scenario", default=None,
                        help="Run a single scenario by name")
    parser.add_argument("--no-reset", action="store_true",
                        help="Skip factory reset between scenarios (faster, less clean)")
    parser.add_argument("--user-accepts-token-spend", action="store_true",
                        help="Required: acknowledge that this invokes the LLM API for every scenario")
    parser.add_argument("--ablation", action="store_true",
                        help="Run all three tiers: bare Grok, identity-only, and full neurosim")
    parser.add_argument("--personality", action="store_true",
                        help="Run Big5 personality ablation: pushover and guarded profiles vs default")
    args = parser.parse_args()

    if not args.user_accepts_token_spend:
        n = len([s for s in SCENARIOS
                 if not args.scenario or s.name == args.scenario])
        print(
            "\n  This script invokes the LLM API — once per sim turn to run Mina, "
            f"plus one grader call per scenario ({n} scenario(s) selected).\n"
            "  Re-run with --user-accepts-token-spend to proceed.\n"
        )
        sys.exit(1)

    targets = SCENARIOS
    if args.scenario:
        targets = [s for s in SCENARIOS if s.name == args.scenario]
        if not targets:
            print(f"Unknown scenario: {args.scenario}")
            print(f"Available: {[s.name for s in SCENARIOS]}")
            sys.exit(1)

    do_reset = not args.no_reset
    results: list[ScenarioResult] = []

    import datetime
    os.makedirs(_REPORT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(_REPORT_DIR, f"{ts}.txt")
    print(f"Writing results to {os.path.relpath(report_path, _REPO)}\n")

    for i, scenario in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {scenario.name}")

        turns = run_scenario(scenario, do_reset)
        print(f"  grading neurosim...", end=" ", flush=True)
        neurosim_grade = grade_scenario(scenario, turns)
        print(f"{neurosim_grade.verdict} ({neurosim_grade.grader_certainty}/10)", flush=True)

        bare_grade = identity_grade = None
        if args.ablation:
            print(f"  running identity-only...", end=" ", flush=True)
            identity_turns = run_identity_only(scenario)
            print(f"done", flush=True)
            print(f"  grading identity-only...", end=" ", flush=True)
            identity_grade = grade_scenario(scenario, identity_turns)
            print(f"{identity_grade.verdict} ({identity_grade.grader_certainty}/10)", flush=True)

            print(f"  running bare grok...", end=" ", flush=True)
            bare_turns = run_bare_grok(scenario)
            print(f"done", flush=True)
            print(f"  grading bare grok...", end=" ", flush=True)
            bare_grade = grade_scenario(scenario, bare_turns)
            print(f"{bare_grade.verdict} ({bare_grade.grader_certainty}/10)", flush=True)

        profile_grades: dict[str, Grade] = {}
        if args.personality:
            for profile_name, big5 in BIG5_PROFILES.items():
                print(f"  running profile: {profile_name}...", end=" ", flush=True)
                profile_turns = run_with_profile(scenario, profile_name, big5)
                print(f"done", flush=True)
                print(f"  grading {profile_name}...", end=" ", flush=True)
                g = grade_scenario(scenario, profile_turns)
                profile_grades[profile_name] = g
                print(f"{g.verdict} ({g.grader_certainty}/10)", flush=True)

        r = ScenarioResult(scenario, turns, neurosim_grade, bare_grade, identity_grade, profile_grades)
        results.append(r)
        with open(report_path, "a") as f:
            f.write(_format_scenario_result(r) + "\n")

    print_report(results, report_path)


if __name__ == "__main__":
    main()
