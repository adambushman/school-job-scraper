#!/usr/bin/env bash
# Install (or update) the systemd timer that runs the daily scan.
#
#   sudo deploy/install.sh
#
# Re-run it any time the units or the install path change; it is idempotent.
set -euo pipefail

UNIT=school-job-scraper
SYSTEMD_DIR=/etc/systemd/system

die() {
	printf 'error: %s\n' "$1" >&2
	exit 1
}

[ "$(id -u)" -eq 0 ] || die "writes to $SYSTEMD_DIR; re-run with sudo"

# Derive both values rather than asking, so the unit can never point at the
# wrong checkout or run as a user that cannot read .env.
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUN_USER=${SUDO_USER:-root}

[ -x "$REPO_DIR/.venv/bin/python" ] || die \
	"no virtualenv at $REPO_DIR/.venv - run: python3 -m venv .venv && .venv/bin/pip install -e ."
[ -f "$REPO_DIR/.env" ] || die \
	"no $REPO_DIR/.env - copy .env.example and fill in your SMTP settings"

if [ "$RUN_USER" = root ]; then
	printf 'warning: no SUDO_USER set, so the service will run as root.\n' >&2
	printf '         Prefer: sudo -u <you> ... or run this via sudo from your own login.\n' >&2
fi

# .env holds a mail password, so it must not be world-readable, and the service
# user has to be able to read it.
env_mode=$(stat -c '%a' "$REPO_DIR/.env")
case "$env_mode" in
600 | 400) ;;
*) printf 'warning: %s/.env is mode %s; tighten it with: chmod 600 .env\n' \
	"$REPO_DIR" "$env_mode" >&2 ;;
esac
sudo -u "$RUN_USER" test -r "$REPO_DIR/.env" || die \
	"$RUN_USER cannot read $REPO_DIR/.env - fix with: chown $RUN_USER $REPO_DIR/.env"

printf 'installing %s\n  repo: %s\n  user: %s\n' "$UNIT" "$REPO_DIR" "$RUN_USER"

for file in "$UNIT.service" "$UNIT.timer"; do
	sed -e "s|@DIR@|$REPO_DIR|g" -e "s|@USER@|$RUN_USER|g" \
		"$REPO_DIR/deploy/$file" >"$SYSTEMD_DIR/$file"
	chmod 644 "$SYSTEMD_DIR/$file"
done

systemctl daemon-reload
systemctl enable --now "$UNIT.timer"

printf '\ndone. next scheduled run:\n'
systemctl list-timers "$UNIT.timer" --no-pager || true
cat <<'NEXT'

Test one run right now (sends a real email):
  sudo systemctl start school-job-scraper.service

Read the output:
  journalctl -u school-job-scraper -n 50 --no-pager

Change the schedule:
  edit OnCalendar in deploy/school-job-scraper.timer, then re-run this script
NEXT
