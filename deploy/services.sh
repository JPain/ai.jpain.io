#!/usr/bin/env bash
# Install the blogs' services on Fern (moved from Arctic 2026-09-29). Idempotent; run via `deploy.sh services`.
#
#   blog-stats   private view counts from the nginx logs, every 5 min (stats/)
#   /blogs/      the Tailscale-only page showing them (stats/web/), served by the
#                tailnet vhost of ops/filehost through snippets/tailnet-*.conf
#   logrotate    /var/log/nginx/blogs/*.log kept 400 days (logrotate-blogs)
#
# nginx changes are tested against a copy of /etc/nginx before anything is
# installed, as in deploy.sh. The Kudos button went when the blogs merged (2026-10): this
# removes its service if it is still installed, and keeps its last counts in
# /var/lib/kudos/kudos.json.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${SITE_SSH:-james@fern}"
TAILNET_CONF="$(dirname "$(dirname "$HERE")")/filehost/nginx-tailnet.conf"
STAGE=/tmp/blog-services
say() { printf '\033[36m==\033[0m %s\n' "$*"; }

say "copying to $HOST"
ssh "$HOST" "rm -rf $STAGE && mkdir -p $STAGE"
rsync -rt "$HERE/stats" "$HERE/logrotate-blogs" "$HERE/nginx-tailnet-blogs.conf" "$HOST:$STAGE/"
scp -q "$TAILNET_CONF" "$HOST:$STAGE/tailnet.conf"

ssh "$HOST" STAGE="$STAGE" 'bash -s' <<'REMOTE'
set -euo pipefail
say() { printf '\033[36m--\033[0m %s\n' "$*"; }
S=$STAGE

# nginx first, tested on a copy: the snippet, and the tailnet vhost that includes it.
T="$(sudo mktemp -d /tmp/nginx-test.XXXXXX)"
trap 'sudo rm -rf "$T"' EXIT
sudo cp -a /etc/nginx/. "$T/"
sudo sed -i "s#/etc/nginx/#$T/#g" "$T/nginx.conf"
sudo install -D -m 0644 "$S/nginx-tailnet-blogs.conf" "$T/snippets/tailnet-blogs.conf"
sed "s#/etc/nginx/snippets/#$T/snippets/#" "$S/tailnet.conf" | sudo tee "$T/sites-available/fern-tailnet" >/dev/null
sudo ln -sfn "$T/sites-available/fern-tailnet" "$T/sites-enabled/fern-tailnet"
sudo nginx -t -q -c "$T/nginx.conf" || { echo "nginx -t FAILED; nothing installed" >&2; exit 1; }
say "nginx changes pass nginx -t"

# Kudos is retired: stop it and remove its unit and code, keeping the counts.
if [ -f /etc/systemd/system/kudos.service ]; then
  sudo systemctl disable -q --now kudos.service || true
  sudo rm -f /etc/systemd/system/kudos.service
  sudo rm -rf /usr/local/lib/kudos /etc/kudos /var/www/blog-stats/kudos
  say "kudos service removed (counts kept in /var/lib/kudos/kudos.json)"
fi

# Account: a fixed system user.
id blog-stats >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin --groups adm blog-stats

# Logs and their rotation.
sudo install -d -o root -g adm -m 0755 /var/log/nginx/blogs
sudo install -o root -g root -m 0644 "$S/logrotate-blogs" /etc/logrotate.d/blogs
sudo logrotate --debug /etc/logrotate.d/blogs >/dev/null 2>&1 || { echo "logrotate rejects logrotate-blogs" >&2; exit 1; }

# The stats page and its data directories.
sudo install -d -o blog-stats -g blog-stats -m 0755 /var/www/blog-stats
for f in index.html stats.css stats.js; do sudo install -o root -g root -m 0644 "$S/stats/web/$f" /var/www/blog-stats/; done

# Code, seed, units.
sudo install -D -o root -g root -m 0644 "$S/stats/blog-stats.py" /usr/local/lib/blog-stats/blog-stats.py
for u in stats/blog-stats.service stats/blog-stats.timer; do
  sudo install -o root -g root -m 0644 "$S/$u" /etc/systemd/system/
done
sudo systemctl daemon-reload
sudo systemctl enable -q blog-stats.timer
sudo systemctl start blog-stats.timer
sudo systemctl start blog-stats.service

# nginx last, now that everything it serves exists.
sudo install -o root -g root -m 0644 "$S/nginx-tailnet-blogs.conf" /etc/nginx/snippets/tailnet-blogs.conf
sudo install -o root -g root -m 0644 "$S/tailnet.conf" /etc/nginx/sites-available/fern-tailnet
sudo nginx -t -q
sudo systemctl reload nginx
rm -rf "$S"
sleep 1
say "blog-stats last run: $(systemctl show -p Result --value blog-stats.service) | nginx: $(systemctl is-active nginx)"
REMOTE
say "done"
