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

_LOG_FILE   = os.path.join(_REPO, "logs", "mina.log")
_CONVOS_DIR = os.path.join(_REPO, "scripts", "convos")
_RESET_SCRIPT = os.path.join(_REPO, "scripts", "factory_reset.py")
_SIM_SCRIPT   = os.path.join(_REPO, "scripts", "chat_sim.py")


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
    bio_cortisol: float | None = None
    bio_oxytocin: float | None = None
    bio_endorphins: float | None = None
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
                # New log entry — end bio block
                in_bio = False
                _extract_bio(current, bio_lines)
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
            _extract_bio(current, bio_lines)
        if in_adj:
            try:
                current.adjudicator = json.loads("\n".join(adj_lines))
            except json.JSONDecodeError:
                pass
        turns.append(current)

    return turns


def _extract_bio(turn: Turn, lines: list[str]) -> None:
    """Pull cortisol / oxytocin / endorphins from a BIO/PROFILE block."""
    for line in lines:
        stripped = line.strip()
        for chem, attr in [("cortisol", "bio_cortisol"),
                           ("oxytocin", "bio_oxytocin"),
                           ("endorphins", "bio_endorphins")]:
            if stripped.startswith(chem):
                parts = stripped.split()
                if len(parts) >= 2:
                    try:
                        setattr(turn, attr, float(parts[1]))
                    except ValueError:
                        pass


# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------

@dataclass
class Grade:
    verdict: str          # PASS / PARTIAL / FAIL
    confidence: int       # 1-10
    reasoning: str
    per_turn_notes: list[str] = field(default_factory=list)


def _format_transcript(turns: list[Turn]) -> str:
    parts = []
    for t in turns:
        adj_str = json.dumps(t.adjudicator, indent=2) if t.adjudicator else "(none)"
        chem_str = ""
        if t.bio_cortisol is not None:
            chem_str = (
                f"cortisol={t.bio_cortisol:.1f}  "
                f"oxytocin={t.bio_oxytocin:.1f}  "
                f"endorphins={t.bio_endorphins:.1f}"
            )
        parts.append(
            f"--- Turn {t.index} ---\n"
            f"User: {t.user_msg}\n"
            f"Encoder: {t.encoder_stimulus}\n"
            f"Chemistry: {chem_str or '(not captured)'}\n"
            f"Adjudicator:\n{adj_str}\n"
            f"Mina: {t.mina_response}\n"
        )
    return "\n".join(parts)


def grade_scenario(scenario: Scenario, turns: list[Turn]) -> Grade:
    from src.application.infra.client import chat_create, CONTEXT_MODEL

    if not turns:
        return Grade(
            verdict="FAIL",
            confidence=10,
            reasoning="No turns parsed — sim produced no output or log was empty.",
        )

    transcript = _format_transcript(turns)
    system = (
        "You are a behavioral evaluator for a neurochemical simulation of a 24-year-old woman named Mina. "
        "You will be given a conversation transcript with per-turn chemistry readings, adjudicator emotional "
        "verdicts, and Mina's actual responses. Your job is to assess whether Mina's behavior matched "
        "the expected profile for this scenario.\n\n"
        "Return a JSON object with exactly these fields:\n"
        '  "verdict": "PASS" | "PARTIAL" | "FAIL"\n'
        '  "confidence": integer 1-10\n'
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
            confidence=int(data.get("confidence", 5)),
            reasoning=data.get("reasoning", ""),
            per_turn_notes=data.get("per_turn_notes", []),
        )
    except Exception as e:
        return Grade(
            verdict="FAIL",
            confidence=1,
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


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_VERDICT_COLOR = {
    "PASS":    "\033[92m",  # green
    "PARTIAL": "\033[93m",  # yellow
    "FAIL":    "\033[91m",  # red
}
_RESET = "\033[0m"


def print_report(results: list[tuple[Scenario, list[Turn], Grade]]) -> None:
    print("\n" + "=" * 70)
    print("VALIDATION REPORT")
    print("=" * 70)

    pass_count = sum(1 for _, _, g in results if g.verdict == "PASS")
    fail_count = sum(1 for _, _, g in results if g.verdict == "FAIL")
    partial_count = sum(1 for _, _, g in results if g.verdict == "PARTIAL")

    for scenario, turns, grade in results:
        color = _VERDICT_COLOR.get(grade.verdict, "")
        print(f"\n{color}[{grade.verdict}]{_RESET} ({grade.confidence}/10)  {scenario.name}")
        print(f"  {scenario.description}")
        if grade.per_turn_notes:
            for i, note in enumerate(grade.per_turn_notes, 1):
                print(f"    turn {i}: {note}")
        print(f"  {grade.reasoning}")

    print("\n" + "-" * 70)
    print(f"  PASS: {pass_count}  PARTIAL: {partial_count}  FAIL: {fail_count}  "
          f"(of {len(results)} scenarios)")
    print("=" * 70 + "\n")


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
    results: list[tuple[Scenario, list[Turn], Grade]] = []

    for i, scenario in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {scenario.name}")
        turns = run_scenario(scenario, do_reset)
        print(f"  grading...", end=" ", flush=True)
        grade = grade_scenario(scenario, turns)
        print(f"{grade.verdict} ({grade.confidence}/10)", flush=True)
        results.append((scenario, turns, grade))

    print_report(results)


if __name__ == "__main__":
    main()
