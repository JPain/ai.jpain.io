#!/usr/bin/env bash
# Deploy a blog to Arctic's nginx. Idempotent: re-run after any build.
#
#   deploy/deploy.sh ai.jpain.io            # push the built site + nginx config
#   deploy/deploy.sh ai.jpain.io --tls      # also get the Let's Encrypt cert
#                                           # (only once DNS points at Arctic)
#   deploy/deploy.sh ai.jpain.io --config   # nginx config only, not the files
#
# Modelled on ops/neverknown/deploy.sh. nginx, certbot, the ACME webroot, the
# certbot reload hook and ufw 80/443 already exist on Arctic (ops/filehost).
#
# Differences from the neverknown script, both on purpose:
# - The new config is tested against a full copy of /etc/nginx BEFORE it is
#   installed, so a bad config never lands in /etc (neverknown's installs
#   first and tests after).
# - With no certificate yet, the real TLS config is installed with a
#   self-signed staging pair instead of an HTTP-only bootstrap, so headers,
#   HTTP/2 and redirects can all be checked before DNS moves:
#     curl -k --resolve ai.jpain.io:443:85.17.65.153 https://ai.jpain.io/
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLOG="$(dirname "$HERE")"
HOST="${SITE_SSH:-james@arctic}"
DOMAIN="${1:-}"
MODE="${2:-}"

case "$DOMAIN" in
  ai.jpain.io) OUT="$BLOG/out"; NAMES=(ai.jpain.io) ;;
  *) echo "usage: $0 ai.jpain.io [--tls|--config]" >&2; exit 2 ;;
esac
CONF="$HERE/nginx-${DOMAIN}.conf"

say() { printf '\033[36m==\033[0m %s\n' "$*"; }

[[ -f "$CONF" ]] || { echo "missing $CONF" >&2; exit 1; }
if [[ "$MODE" != "--config" ]]; then
  [[ -f "$OUT/index.html" ]] || { echo "$OUT/index.html missing: build first" >&2; exit 1; }
fi

STAGE="/tmp/blog-deploy-$DOMAIN"
say "copying to $HOST"
ssh "$HOST" "rm -rf '$STAGE' && mkdir -p '$STAGE/site'"
if [[ "$MODE" != "--config" ]]; then
  # Dotfiles (.nojekyll) and CNAME are GitHub Pages furniture, not the site.
  rsync -rt --delete --exclude='.*' --exclude=CNAME "$OUT/" "$HOST:$STAGE/site/"
fi
scp -q "$CONF" "$HOST:$STAGE/site.conf"

ssh "$HOST" DOMAIN="$DOMAIN" STAGE="$STAGE" MODE="$MODE" 'bash -s' <<'REMOTE'
set -euo pipefail
say() { printf '\033[36m--\033[0m %s\n' "$*"; }
LE="/etc/letsencrypt/live/${DOMAIN}"
STAGING="/etc/nginx/staging-certs/${DOMAIN}"

if sudo test -f "$LE/fullchain.pem"; then
  say "Let's Encrypt certificate present"
else
  say "no certificate yet: using a self-signed staging pair"
  if ! sudo test -f "$STAGING/fullchain.pem"; then
    sudo install -d -m 0700 "$STAGING"
    sudo openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
      -days 90 -subj "/CN=${DOMAIN} (staging, not trusted)" -addext "subjectAltName=DNS:${DOMAIN}" \
      -keyout "$STAGING/privkey.pem" -out "$STAGING/fullchain.pem" 2>/dev/null
  fi
  sed -i "s#${LE}/#${STAGING}/#g" "$STAGE/site.conf"
fi

# Test first, on a copy of the whole nginx tree with this site swapped in.
T="$(sudo mktemp -d /tmp/nginx-test.XXXXXX)"
trap 'sudo rm -rf "$T"' EXIT
sudo cp -a /etc/nginx/. "$T/"
sudo sed -i "s#/etc/nginx/#$T/#g" "$T/nginx.conf"
sudo install -m 0644 "$STAGE/site.conf" "$T/sites-available/${DOMAIN}"
sudo ln -sfn "$T/sites-available/${DOMAIN}" "$T/sites-enabled/${DOMAIN}"
if ! sudo nginx -t -q -c "$T/nginx.conf"; then
  echo "nginx -t FAILED on the new config; nothing was installed" >&2
  exit 1
fi
say "config passes nginx -t"

if [[ "$MODE" != "--config" ]]; then
  sudo install -d -o root -g root -m 0755 "/var/www/${DOMAIN}"
  sudo rsync -rt --delete --chown=root:root --chmod=D0755,F0644 "$STAGE/site/" "/var/www/${DOMAIN}/"
  say "site files: $(sudo find "/var/www/${DOMAIN}" -type f | wc -l)"
fi
sudo install -o root -g root -m 0644 "$STAGE/site.conf" "/etc/nginx/sites-available/${DOMAIN}"
sudo ln -sfn "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
sudo nginx -t -q
sudo systemctl reload nginx
rm -rf "$STAGE"
say "nginx: $(systemctl is-active nginx)"
REMOTE

if [[ "$MODE" == "--tls" ]]; then
  args=(); for n in "${NAMES[@]}"; do args+=(-d "$n"); done
  say "requesting certificate for ${NAMES[*]}"
  ssh "$HOST" "sudo certbot certonly --webroot -w /var/www/certbot ${args[*]} \
      --cert-name '$DOMAIN' --non-interactive --agree-tos -m jamesepain@gmail.com --keep-until-expiring"
  say "re-running deploy to switch nginx to the real certificate"
  "$HERE/deploy.sh" "$DOMAIN" --config
fi

say "done"
