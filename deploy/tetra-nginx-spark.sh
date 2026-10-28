#!/usr/bin/env bash
# One-time setup on tetra.imbamarketing.com (run as root).
#
# Why: on tetra, Plesk's nginx owns ports 80/443 and fronts Coolify's Traefik
# (published on 127.0.0.1:8081 http / 127.0.0.1:8445 https). Traefik therefore
# cannot complete Let's Encrypt HTTP-01 for new domains, so each Coolify app
# domain gets an nginx vhost with a certbot certificate issued via the
# Cloudflare DNS plugin (same pattern as payload.imbamarketing.com).
set -euo pipefail

D=${1:-spark.imbamarketing.com}
TEMPLATE_RENEWAL=/etc/letsencrypt/renewal/payload.imbamarketing.com.conf
CRED=$(awk '/dns_cloudflare_credentials/ {print $3}' "$TEMPLATE_RENEWAL")

if [ ! -d "/etc/letsencrypt/live/$D" ]; then
  certbot certonly --dns-cloudflare --dns-cloudflare-credentials "$CRED" \
    --dns-cloudflare-propagation-seconds 30 -d "$D" \
    --non-interactive --agree-tos --keep-until-expiring
fi

cat > "/etc/nginx/conf.d/$D.conf" <<EOF
server {
    listen 65.21.238.89:80;
    listen [::]:80;
    server_name $D;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/vhosts/default/htdocs;
        try_files \$uri =404;
        types { }
        default_type text/plain;
        auth_basic off;
        allow all;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 65.21.238.89:443 ssl;
    listen [2a01:4f9:6a:4da6::2]:443 ssl;
    http2 on;
    server_name $D;

    ssl_certificate /etc/letsencrypt/live/$D/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$D/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    add_header X-Served-By "spark-proxy" always;
    client_max_body_size 60m;

    location / {
        # Coolify's domain for this app is https://, so Traefik's port-80 router
        # redirects to https. Talk TLS to Traefik's https port with SNI instead,
        # which avoids the redirect loop; Traefik's own cert is irrelevant here.
        proxy_pass https://127.0.0.1:8445;
        proxy_ssl_server_name on;
        proxy_ssl_name $D;
        proxy_ssl_verify off;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120;
    }
}
EOF

nginx -t
systemctl reload nginx
echo "done: https://$D"
