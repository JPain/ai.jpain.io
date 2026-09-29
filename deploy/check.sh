#!/usr/bin/env bash
# Behavioural checks for a blog on Arctic: every line states what the server
# SHOULD do and compares it with what it does. Read-only apart from harmless
# refused requests. Modelled on ops/neverknown/check.sh.
#
#   deploy/check.sh ai.jpain.io             # against the public name
#   deploy/check.sh ai.jpain.io --staging   # against Arctic directly, before
#                                           # DNS moves (self-signed cert OK)
D="${1:?usage: $0 <domain> [--staging]}"
IP4=95.211.45.90; IP6=2001:1af8:5301:109:1c00:82ff:fe00:7d3   # Fern since 2026-09-29
C=(curl -s --max-time 10)
if [[ "${2:-}" == "--staging" ]]; then
  C+=(-k --resolve "$D:443:$IP4" --resolve "$D:80:$IP4" --resolve "www.$D:443:$IP4")
fi
pass=0; fail=0
chk() { # name expected actual
  if [[ "$3" == $2 ]]; then printf 'PASS  %-52s %s\n' "$1" "$3"; pass=$((pass+1));
  else printf 'FAIL  %-52s expected [%s] got [%s]\n' "$1" "$2" "$3"; fail=$((fail+1)); fi; }
code() { "${C[@]}" -o /dev/null -w '%{http_code}' "$@"; }
loc()  { "${C[@]}" -o /dev/null -w '%{http_code} %header{location}' "$@"; }
ctype(){ "${C[@]}" -o /dev/null -w '%{content_type}' "$@"; }
hdr()  { "${C[@]}" -o /dev/null -D - "${@:2}" | tr -d '\r' | awk -F': ' -v h="$1" 'tolower($1)==h{print $2}'; }

# A post, one of its images and a tag, taken from the live sitemap/feed.
# Prefer a post with images, so the image checks run.
POST=; IMG=
for u in $("${C[@]}" "https://$D/sitemap.xml" | grep -oE "https://$D/[a-z0-9-]+/" | sed "s#https://$D##" | grep -v '^/$'); do
  [[ -z "$POST" ]] && POST=$u
  i=$("${C[@]}" "https://$D$u" | grep -oE 'src="[^"/]+\.(webp|png|jpg)"' | head -1 | cut -d'"' -f2)
  if [[ -n "$i" ]]; then POST=$u; IMG=$i; break; fi
done
echo "(post $POST, image ${IMG:-none})"

echo "--- URLs that must keep working"
chk "http -> https (keeps path)"          "301 https://$D/a?b=1"  "$(loc "http://$D/a?b=1")"
chk "home 200"                            "200"                   "$(code "https://$D/")"
chk "HEAD home 200"                       "200"                   "$(code -I "https://$D/")"
chk "post 200"                            "200"                   "$(code "https://$D$POST")"
chk "post without slash -> 301 to slash"  "301 ${POST}"           "$(loc "https://$D${POST%/}")"
[[ -n "$IMG" ]] && chk "post image 200"   "200"                   "$(code "https://$D$POST$IMG")"

echo "--- One address per page (SEO audit 2026-09-28)"
chk "/index.html -> 301 /"                "301 /"                 "$(loc "https://$D/index.html")"
chk "post index.html -> 301 to post"      "301 ${POST}"           "$(loc "https://$D${POST}index.html")"
chk "post names itself canonical"         "1"                     "$("${C[@]}" "https://$D$POST" | grep -c "<link rel=\"canonical\" href=\"https://$D$POST\">")"
chk "home names itself canonical"         "1"                     "$("${C[@]}" "https://$D/" | grep -c "<link rel=\"canonical\" href=\"https://$D/\">")"
chk "post has BlogPosting JSON-LD"        "1"                     "$("${C[@]}" "https://$D$POST" | grep -c '"@type":"BlogPosting"')"
chk "post has a share card"               "1"                     "$("${C[@]}" "https://$D$POST" | grep -c '<meta property="og:title"')"
chk "sitemap has <lastmod> per URL"       "yes"                   "$(s=$("${C[@]}" "https://$D/sitemap.xml"); [[ $(grep -o '<loc>' <<<"$s" | wc -l) -eq $(grep -o '<lastmod>' <<<"$s" | wc -l) ]] && echo yes || echo no)"
if [[ "$D" == "ai.jpain.io" ]]; then
  chk "markdown names the post canonical" "<https://$D${POST}>; rel=\"canonical\"" "$(hdr link "https://$D${POST}index.md")"
  chk "no Link header on a normal page"   ""                      "$(hdr link "https://$D$POST")"
fi
if [[ "$D" == "ai.jpain.io" ]]; then
  chk "post markdown 200"                 "200"                   "$(code "https://$D${POST}index.md")"
  chk "post markdown is text/markdown"    "text/markdown; charset=utf-8" "$(ctype "https://$D${POST}index.md")"
  chk "feed.xml application/xml"          "application/xml; charset=utf-8" "$(ctype "https://$D/feed.xml")"
  chk "feed.json application/json"        "application/json; charset=utf-8" "$(ctype "https://$D/feed.json")"
  PAGES="/about/ /colophon/ /tags/ /llms.txt /robots.txt /sitemap.xml /style.css"
else   # jpain.io: Bear's addresses and content types
  chk "www -> apex (keeps path)"          "301 https://$D/a?b=1"  "$(loc "https://www.$D/a?b=1")"
  chk "/feed/ is Atom"                    "application/atom+xml; charset=utf-8" "$(ctype "https://$D/feed/")"
  chk "/atom/ is Atom"                    "application/atom+xml; charset=utf-8" "$(ctype "https://$D/atom/")"
  chk "/feed/?type=rss is RSS"            "application/rss+xml; charset=utf-8"  "$(ctype "https://$D/feed/?type=rss")"
  chk "/rss/ is RSS"                      "application/rss+xml; charset=utf-8"  "$(ctype "https://$D/rss/")"
  chk "sitemap text/xml, as Bear"         "text/xml; charset=utf-8" "$(ctype "https://$D/sitemap.xml")"
  chk "Bear tag link /blog/?q=ai 200"     "200"                   "$(code "https://$D/blog/?q=ai")"
  chk "kudos GET answers JSON"            '{"count": *'           "$("${C[@]}" "https://$D/kudos${POST}")"
  chk "kudos never cached"                "no-store"              "$(hdr cache-control "https://$D/kudos${POST}")"
  chk "kudos from another site refused"   "403"                   "$(code -X POST -H 'Origin: https://evil.example' "https://$D/kudos${POST}")"
  chk "kudos for no such post"            "404"                   "$(code "https://$D/kudos/no-such-post/")"
  chk "fonts cached 1 year"               "max-age=31536000"      "$(hdr cache-control "https://$D/fonts/plex-sans-400.woff2")"
  PAGES="/blog/ /tags/ /robots.txt /style.css /site.js /favicon.svg"
fi
for p in $PAGES; do
  chk "$p 200"                            "200"                   "$(code "https://$D$p")"
done
chk "unknown path 404"                    "404"                   "$(code "https://$D/no-such-post/")"

echo "--- headers (on every kind of response: no location may drop them)"
for u in / "$POST" "$POST$IMG" /no-such-post/; do
  [[ -z "$u" ]] && continue
  chk "CSP on $u"                         "default-src 'self';*"  "$(hdr content-security-policy "https://$D$u")"
  chk "HSTS on $u"                        "max-age=63072000"      "$(hdr strict-transport-security "https://$D$u")"
  chk "nosniff on $u"                     "nosniff"               "$(hdr x-content-type-options "https://$D$u")"
done
chk "X-Served-By: ${SERVED_BY:-fern}"                  "${SERVED_BY:-fern}"                "$(hdr x-served-by "https://$D/")"
chk "HTTP/2 negotiated"                   "2"                     "$("${C[@]}" -o /dev/null -w '%{http_version}' "https://$D/")"
chk "HTTP/3 advertised (Alt-Svc)"         'h3=":443"; ma=86400'   "$(hdr alt-svc "https://$D/")"
chk "HTML cached 10 minutes"              "max-age=600"           "$(hdr cache-control "https://$D/")"
[[ -n "$IMG" ]] && chk "images cached 1 day" "max-age=86400"      "$(hdr cache-control "https://$D$POST$IMG")"
chk "gzip on CSS"                         "gzip"                  "$(hdr content-encoding -H 'Accept-Encoding: gzip' "https://$D/style.css")"

echo "--- nothing exposed, nothing accepted"
for m in POST PUT DELETE; do chk "$m / -> 405" "405" "$(code -X "$m" "https://$D/")"; done
chk "POST to a post page -> 405"          "405"                   "$(code -X POST "https://$D$POST")"
for p in /.git/config /.env /404.html; do chk "$p -> 404" "404" "$(code "https://$D$p")"; done
chk "path traversal refused"              "400"                   "$(code --path-as-is "https://$D/../../etc/passwd")"

echo "--- neighbours on the same nginx still fine"
chk "i.j3p.uk 200"                        "200"                   "$(curl -s -o /dev/null -w '%{http_code}' https://i.j3p.uk/)"
chk "weareneverknown.com 200"             "200"                   "$(curl -s -o /dev/null -w '%{http_code}' https://weareneverknown.com/)"
chk "unknown SNI still refused"           "35"                    "$(curl -s -o /dev/null --resolve evil.example:443:$IP4 https://evil.example/; echo $?)"

echo; echo "$pass passed, $fail failed"
(( fail == 0 ))
