#!/usr/bin/env bash
# shellcheck disable=SC2030,SC2031
# Darwin launchctl → Aqua osascript fallback. Stubs stand in for launchctl
# and osascript so this runs on Linux. The AppleScript shape is the labeled
# hypothesis in scripts/mina: do shell script + quoted form of + /bin/launchctl.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$(mktemp -d)"
# Space in HOME so plist quoting is part of the contract.
HOME_DIR="$(mktemp -d)/Mina Home"
mkdir -p "$HOME_DIR"
STUB="$(mktemp -d)"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  if [[ -f "$LOG/err" ]]; then
    printf '%s\n' "--- stderr ---" "$(cat "$LOG/err")" >&2
  fi
  if [[ -f "$LOG/out" ]]; then
    printf '%s\n' "--- stdout ---" "$(cat "$LOG/out")" >&2
  fi
  exit 1
}

reset_logs() {
  rm -rf "$LOG"
  mkdir -p "$LOG"
}

set_direct() { printf '%s\n' "$2" >"$LOG/direct-$1"; }
set_aqua() { printf '%s\n' "$2" >"$LOG/aqua-$1"; }

cat >"$STUB/launchctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" >>"$LOG/launchctl"
mode="missing-mode"
if [[ -f "$LOG/direct-$1" ]]; then
  mode="$(cat "$LOG/direct-$1")"
fi
case "$mode" in
  ok)
    if [[ "$1" == "print" ]]; then
      printf '%s\n' "state = running"
    fi
    exit 0
    ;;
  missing)
    printf '%s\n' "Could not find service \"com.rafritts.mina\" in domain for uid: 1" >&2
    exit 113
    ;;
  error5)
    printf '%s\n' "Bootstrap failed: 5: Input/output error" >&2
    exit 5
    ;;
  eperm)
    printf '%s\n' "Bootstrap failed: 1: Operation not permitted" >&2
    exit 1
    ;;
  exists)
    printf '%s\n' "Bootstrap failed: 17: File exists" >&2
    exit 17
    ;;
  nosuch)
    printf '%s\n' "Boot-out failed: 3: No such process" >&2
    exit 3
    ;;
  nofile)
    printf '%s\n' "Bootstrap failed: 2: No such file or directory" >&2
    exit 2
    ;;
  *)
    printf 'launchctl %s has no mode (%s)\n' "$1" "$mode" >&2
    exit 99
    ;;
esac
EOF

cat >"$STUB/osascript" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
script="$(cat)"
printf '%s\n' "$script" >"$LOG/osascript.applescript"
printf '%s\n' "$@" >>"$LOG/osascript.args"
grep -q 'do shell script' <<<"$script" || {
  printf '%s\n' "applescript missing do shell script" >&2
  exit 2
}
grep -q 'quoted form of' <<<"$script" || {
  printf '%s\n' "applescript missing quoted form of" >&2
  exit 2
}
grep -q '/bin/launchctl' <<<"$script" || {
  printf '%s\n' "applescript missing /bin/launchctl" >&2
  exit 2
}
verb="${2:-}"
mode="missing-mode"
if [[ -f "$LOG/aqua-$verb" ]]; then
  mode="$(cat "$LOG/aqua-$verb")"
fi
case "$mode" in
  ok)
    if [[ "$verb" == "print" ]]; then
      printf '%s\n' "state = running"
    fi
    exit 0
    ;;
  exists)
    printf '%s\n' "execution error: Bootstrap failed: 17: File exists (17)" >&2
    exit 1
    ;;
  nosuch)
    printf '%s\n' "execution error: Boot-out failed: 3: No such process (3)" >&2
    exit 1
    ;;
  error5)
    printf '%s\n' "execution error: Bootstrap failed: 5: Input/output error (5)" >&2
    exit 5
    ;;
  *)
    printf 'osascript %s has no mode (%s)\n' "$verb" "$mode" >&2
    exit 99
    ;;
esac
EOF

cat >"$STUB/systemctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >>"$LOG/systemctl"
exit 0
EOF

chmod +x "$STUB/launchctl" "$STUB/osascript" "$STUB/systemctl"

export LOG
export MINA_LIB_ONLY=1
export MINA_OS=Darwin
export MINA_LAUNCHCTL="$STUB/launchctl"
export MINA_OSASCRIPT="$STUB/osascript"
export HOME="$HOME_DIR"
# shellcheck disable=SC1091
source "$ROOT/scripts/mina"

UID_N="$(id -u)"
DOMAIN="gui/${UID_N}"
TARGET="gui/${UID_N}/com.rafritts.mina"

no_aqua() {
  [[ ! -e "$LOG/osascript.args" ]] || fail "$1 invoked osascript: $(cat "$LOG/osascript.args")"
}

ran_line() {
  local file="$1" line="$2"
  [[ -f "$file" ]] || fail "missing $file while looking for [$line]"
  grep -Fxq -- "$line" "$file" || fail "missing [$line] in $file: $(cat "$file")"
}

run_svc() {
  local verb="$1"
  set +e
  _svc "$verb" >"$LOG/out" 2>"$LOG/err"
  SVC_RC=$?
  set -e
}

echo "1 start: not loaded, bootstrap error 5, Aqua bootstrap loads the agent"
reset_logs
set_direct print missing
set_direct bootstrap error5
set_aqua bootstrap ok
run_svc start
[[ "$SVC_RC" -eq 0 ]] || fail "start rc=$SVC_RC"
ran_line "$LOG/launchctl" bootstrap
ran_line "$LOG/launchctl" "$DOMAIN"
ran_line "$LOG/launchctl" "$PLIST"
ran_line "$LOG/osascript.args" bootstrap
ran_line "$LOG/osascript.args" "$DOMAIN"
ran_line "$LOG/osascript.args" "$PLIST"
grep -q 'Retrying in the Aqua session via osascript' "$LOG/err" || fail "no fallback line"
grep -q 'launchctl bootstrap succeeded in the Aqua session' "$LOG/err" || fail "no success line"
grep -q 'do shell script' "$LOG/osascript.applescript" || fail "script shape"
[[ "$PLIST" == *" "* ]] || fail "expected a space in plist path to exercise quoting"

echo "2 start: already loaded (print succeeds) is quiet and does not bootstrap"
reset_logs
set_direct print ok
run_svc start
[[ "$SVC_RC" -eq 0 ]] || fail "start rc=$SVC_RC"
ran_line "$LOG/launchctl" print
if grep -Fxq -- bootstrap "$LOG/launchctl"; then
  fail "bootstrap ran for an already-loaded job"
fi
no_aqua "already-loaded start"
[[ ! -s "$LOG/err" ]] || fail "already-loaded start was noisy"

echo "3 start: print error 5 but Aqua print shows loaded — do not bootstrap again"
reset_logs
set_direct print error5
set_aqua print ok
run_svc start
[[ "$SVC_RC" -eq 0 ]] || fail "start rc=$SVC_RC"
if [[ -f "$LOG/launchctl" ]] && grep -Fxq -- bootstrap "$LOG/launchctl"; then
  fail "bootstrap ran even though Aqua print showed the job loaded"
fi
ran_line "$LOG/osascript.args" print
[[ ! -s "$LOG/err" ]] || fail "quiet loaded probe printed fallback chatter"

echo "4 bootstrap: File exists is quiet success without Aqua"
reset_logs
set_direct bootstrap exists
set +e
_mac_launchctl bootstrap "$DOMAIN" "$PLIST" >"$LOG/out" 2>"$LOG/err"
rc=$?
set -e
[[ "$rc" -eq 0 ]] || fail "file-exists rc=$rc"
no_aqua "file-exists bootstrap"
[[ ! -s "$LOG/err" ]] || fail "file-exists was noisy: $(cat "$LOG/err")"

echo "5 bootstrap: error 5 then Aqua File exists is already-loaded, not a failure"
reset_logs
set_direct bootstrap error5
set_aqua bootstrap exists
set +e
_mac_launchctl bootstrap "$DOMAIN" "$PLIST" >"$LOG/out" 2>"$LOG/err"
rc=$?
set -e
[[ "$rc" -eq 0 ]] || fail "aqua file-exists rc=$rc"
grep -q 'already in the desired state in the Aqua session' "$LOG/err" || fail "no already-loaded note"
if grep -q 'Aqua launchctl bootstrap failed' "$LOG/err"; then
  fail "already-loaded Aqua bootstrap reported failure"
fi

echo "6 bootstrap: Operation not permitted falls back to Aqua"
reset_logs
set_direct bootstrap eperm
set_aqua bootstrap ok
set +e
_mac_launchctl bootstrap "$DOMAIN" "$PLIST" >"$LOG/out" 2>"$LOG/err"
rc=$?
set -e
[[ "$rc" -eq 0 ]] || fail "eperm rc=$rc"
grep -q 'Operation not permitted' "$LOG/err" || fail "permission text dropped"
ran_line "$LOG/osascript.args" bootstrap

echo "7 bootstrap: missing plist does not take the Aqua path"
reset_logs
set_direct bootstrap nofile
set +e
_mac_launchctl bootstrap "$DOMAIN" "$PLIST" >"$LOG/out" 2>"$LOG/err"
rc=$?
set -e
[[ "$rc" -eq 2 ]] || fail "nofile rc=$rc"
no_aqua "missing plist"
grep -q 'No such file or directory' "$LOG/err" || fail "original error hidden"

echo "8 stop: already unloaded is quiet"
reset_logs
set_direct bootout nosuch
run_svc stop
[[ "$SVC_RC" -eq 0 ]] || fail "stop rc=$SVC_RC"
no_aqua "absent bootout"
[[ ! -s "$LOG/err" ]] || fail "absent bootout was noisy: $(cat "$LOG/err")"

echo "9 stop: bootout error 5 retries in Aqua"
reset_logs
set_direct bootout error5
set_aqua bootout ok
run_svc stop
[[ "$SVC_RC" -eq 0 ]] || fail "stop rc=$SVC_RC"
ran_line "$LOG/osascript.args" bootout
ran_line "$LOG/osascript.args" "$TARGET"
grep -q 'launchctl bootout succeeded in the Aqua session' "$LOG/err" || fail "no bootout success"

echo "10 stop: Aqua bootout No such process is success"
reset_logs
set_direct bootout error5
set_aqua bootout nosuch
run_svc stop
[[ "$SVC_RC" -eq 0 ]] || fail "stop rc=$SVC_RC"
grep -q 'already in the desired state' "$LOG/err" || fail "unloaded Aqua bootout not treated as success"
if grep -q 'Aqua launchctl bootout failed' "$LOG/err"; then
  fail "unloaded Aqua bootout reported failure"
fi

echo "11 restart: loaded only via Aqua print, kickstart error 5 uses Aqua kickstart -k"
reset_logs
set_direct print error5
set_aqua print ok
set_direct kickstart error5
set_aqua kickstart ok
run_svc restart
[[ "$SVC_RC" -eq 0 ]] || fail "restart rc=$SVC_RC"
ran_line "$LOG/launchctl" kickstart
ran_line "$LOG/launchctl" "-k"
ran_line "$LOG/osascript.args" kickstart
ran_line "$LOG/osascript.args" "-k"
ran_line "$LOG/osascript.args" "$TARGET"
if grep -Fxq -- bootstrap "$LOG/launchctl"; then
  fail "restart bootstrapped a job Aqua print said was loaded"
fi
grep -q 'launchctl kickstart succeeded in the Aqua session' "$LOG/err" || fail "no kickstart success"

echo "12 status: print error 5, Aqua print output is the status"
reset_logs
set_direct print error5
set_aqua print ok
run_svc status
[[ "$SVC_RC" -eq 0 ]] || fail "status rc=$SVC_RC"
grep -q 'state = running' "$LOG/out" || fail "status missed Aqua print output"
if grep -q 'not loaded' "$LOG/out"; then
  fail "status reported not loaded"
fi
grep -q 'Retrying in the Aqua session' "$LOG/err" || fail "status hid the fallback"

echo "13 status: not loaded stays not loaded and does not call Aqua"
reset_logs
set_direct print missing
run_svc status
[[ "$SVC_RC" -eq 0 ]] || fail "status rc=$SVC_RC"
grep -q 'not loaded' "$LOG/out" || fail "missing not-loaded line"
no_aqua "not-loaded status"

echo "14 Aqua bootstrap still failing surfaces the Aqua error"
reset_logs
set_direct bootstrap error5
set_aqua bootstrap error5
set +e
_mac_launchctl bootstrap "$DOMAIN" "$PLIST" >"$LOG/out" 2>"$LOG/err"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "expected failure"
grep -q 'Aqua launchctl bootstrap failed' "$LOG/err" || fail "aqua failure hidden"

echo "15 Linux systemctl path is unchanged and never calls launchctl or osascript"
(
  export MINA_LIB_ONLY=1
  export MINA_OS=Linux
  export MINA_LAUNCHCTL="$STUB/launchctl"
  export MINA_OSASCRIPT="$STUB/osascript"
  export HOME="$HOME_DIR"
  export PATH="$STUB:/usr/bin:/bin"
  export LOG
  # shellcheck disable=SC1091
  source "$ROOT/scripts/mina"
  reset_logs
  set +e
  _svc start >"$LOG/out" 2>"$LOG/err"
  rc=$?
  set -e
  [[ "$rc" -eq 0 ]] || fail "linux start rc=$rc err=$(cat "$LOG/err")"
  ran_line "$LOG/systemctl" --user
  ran_line "$LOG/systemctl" start
  ran_line "$LOG/systemctl" mina
  [[ ! -e "$LOG/launchctl" ]] || fail "linux start called launchctl"
  [[ ! -e "$LOG/osascript.args" ]] || fail "linux start called osascript"
)

echo "16 default OS on this host follows uname (no Darwin leak)"
(
  export MINA_LIB_ONLY=1
  unset MINA_OS
  export HOME="$HOME_DIR"
  export PATH="$STUB:/usr/bin:/bin"
  export LOG
  # shellcheck disable=SC1091
  source "$ROOT/scripts/mina"
  [[ "$OS" == "$(uname -s)" ]] || fail "OS=$OS uname=$(uname -s)"
  [[ "$OS" != "Darwin" ]] || fail "this runner unexpectedly reports Darwin"
  reset_logs
  _svc start >"$LOG/out" 2>"$LOG/err"
  ran_line "$LOG/systemctl" mina
  [[ ! -e "$LOG/launchctl" ]] || fail "default OS called launchctl"
)

echo "17 uninstalled mina still errors before any service call"
empty="$(mktemp -d)"
set +e
out="$(env -u MINA_LIB_ONLY -u MINA_OS HOME="$empty" bash "$ROOT/scripts/mina" start 2>&1)"
rc=$?
set -e
[[ "$rc" -eq 1 ]] || fail "uninstalled rc=$rc out=$out"
grep -q 'not installed' <<<"$out" || fail "uninstalled message: $out"

echo "18 enable: error 5 retries enable in Aqua"
reset_logs
set_direct enable error5
set_aqua enable ok
run_svc enable
[[ "$SVC_RC" -eq 0 ]] || fail "enable rc=$SVC_RC"
ran_line "$LOG/osascript.args" enable
ran_line "$LOG/osascript.args" "$TARGET"
grep -q 'launchctl enable succeeded in the Aqua session' "$LOG/err" || fail "no enable success"

echo "19 quiet loaded-probe does not chatter when Aqua print also fails"
reset_logs
set_direct print error5
set_aqua print error5
set_direct bootstrap error5
set_aqua bootstrap error5
run_svc start
[[ "$SVC_RC" -ne 0 ]] || fail "expected start to fail when Aqua bootstrap fails"
if grep -q 'Aqua launchctl print failed' "$LOG/err"; then
  fail "loaded probe reported its own Aqua failure"
fi
grep -q 'Aqua launchctl bootstrap failed' "$LOG/err" || fail "bootstrap Aqua failure hidden"

echo "20 help mentions the Aqua fallback"
help_home="$(mktemp -d)"
mkdir -p "$help_home/.config/mina"
printf '%s\n' "$help_home/repo" >"$help_home/.config/mina/dir"
set +e
out="$(env -u MINA_LIB_ONLY -u MINA_OS HOME="$help_home" bash "$ROOT/scripts/mina" help 2>&1)"
rc=$?
set -e
[[ "$rc" -eq 0 ]] || fail "help rc=$rc out=$out"
grep -q 'osascript' <<<"$out" || fail "help missing osascript"
grep -q 'error 5' <<<"$out" || fail "help missing error 5"

echo "all darwin launchctl fallback checks passed"
rm -rf "$LOG" "$(dirname "$HOME_DIR")" "$STUB" "$empty" "$help_home"
