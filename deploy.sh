#!/bin/bash
# Full deploy script for GTM Hub
# Usage: bash deploy.sh
# Terminates any existing instance, uploads latest code, and launches a fresh one.
#
# HTTPS: Terminated by CloudFront (distribution kali-gtm-hub-cf / EHJS9BMWR6QG1).
#        EC2 serves HTTP only on port 80 — no certs needed on the instance.
#
# SECURITY: Secrets are never interpolated into EC2 user-data.
# They are uploaded to a private S3 object and fetched via a short-lived
# pre-signed URL at instance boot time. The URL expires in 30 minutes.

set -e
cd "$(dirname "$0")"  # always run from the script's directory

# ── Load config ───────────────────────────────────────────────────────────────
if [ ! -f deploy.env ]; then
  echo "ERROR: deploy.env not found."
  echo "Copy deploy.env.example to deploy.env and fill in your values."
  exit 1
fi
source deploy.env

# Validate required vars
for var in PROFILE REGION BUCKET SG_ID TAG_NAME KEY_NAME EIP_ALLOC DOMAIN GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET SECRET_KEY FRONTEND_URL SALESFORCE_INSTANCE_URL SALESFORCE_CLIENT_ID SALESFORCE_CLIENT_SECRET SALESFORCE_REFRESH_TOKEN; do
  if [ -z "${!var}" ]; then
    echo "ERROR: $var is not set in deploy.env"
    exit 1
  fi
done

EXPIRES=7200          # pre-signed URL TTL for app bundles (2 hours)
SECRETS_EXPIRES=1800  # pre-signed URL TTL for secrets env file (30 minutes)

# ── PRE-DEPLOY CHECKLIST ──────────────────────────────────────────────────────
# Before deploying, run a security audit with Claude:
#
#   claude "Perform a security audit of this codebase before I deploy to
#   production. Check for: authentication bypasses, input validation gaps,
#   injection vulnerabilities (SOQL, command, path traversal), secrets in code
#   or logs, CSRF weaknesses, insecure direct object references, unprotected
#   endpoints, and any other OWASP Top 10 issues. Review backend/app.py,
#   backend/apps/se_scorecard_v2/routes.py, backend/salesforce.py, and the
#   frontend API layer. Report findings with severity (Critical/High/Medium/Low)
#   and recommended fixes."
#
# Only proceed if there are no Critical or High findings.
# ─────────────────────────────────────────────────────────────────────────────

# ── 0. Build SvelteKit frontend ───────────────────────────────────────────────
echo "Building frontend..."
cd frontend
npm ci --silent
npm run build
cd ..
echo "Frontend built."

# ── 1. Terminate any running instances with this tag ─────────────────────────
echo ""
echo "Checking for running instances..."
OLD_IDS=$(aws ec2 describe-instances \
  --profile "$PROFILE" --region "$REGION" \
  --filters "Name=tag:Name,Values=$TAG_NAME" "Name=instance-state-name,Values=running,pending" \
  --query "Reservations[].Instances[].InstanceId" \
  --output text)

if [ -n "$OLD_IDS" ]; then
  echo "Terminating: $OLD_IDS"
  aws ec2 terminate-instances \
    --profile "$PROFILE" --region "$REGION" \
    --instance-ids $OLD_IDS > /dev/null
  echo "Waiting for termination..."
  aws ec2 wait instance-terminated \
    --profile "$PROFILE" --region "$REGION" \
    --instance-ids $OLD_IDS
  echo "Terminated."
else
  echo "No running instances found."
fi

# ── 2. Upload app files + secrets env to S3 ──────────────────────────────────
echo ""
echo "Uploading files to S3..."
tar -czf /tmp/backend.tar.gz  -C backend .
tar -czf /tmp/frontend.tar.gz -C frontend/build .
aws s3 cp /tmp/backend.tar.gz  s3://$BUCKET/backend.tar.gz  --profile "$PROFILE" --region "$REGION"
aws s3 cp /tmp/frontend.tar.gz s3://$BUCKET/frontend.tar.gz --profile "$PROFILE" --region "$REGION"
aws s3api put-object-tagging --bucket "$BUCKET" --key backend.tar.gz  --tagging 'TagSet=[{Key=owner,Value=kali}]' --profile "$PROFILE" --region "$REGION"
aws s3api put-object-tagging --bucket "$BUCKET" --key frontend.tar.gz --tagging 'TagSet=[{Key=owner,Value=kali}]' --profile "$PROFILE" --region "$REGION"
rm /tmp/backend.tar.gz /tmp/frontend.tar.gz

# Write secrets to a temp file, upload to S3, then delete locally
SECRETS_FILE=$(mktemp /tmp/secrets.XXXXXX.env)
chmod 600 "$SECRETS_FILE"
cat > "$SECRETS_FILE" << SECRETS
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
SECRET_KEY=${SECRET_KEY}
SALESFORCE_INSTANCE_URL=${SALESFORCE_INSTANCE_URL}
SALESFORCE_CLIENT_ID=${SALESFORCE_CLIENT_ID}
SALESFORCE_CLIENT_SECRET=${SALESFORCE_CLIENT_SECRET}
SALESFORCE_REFRESH_TOKEN=${SALESFORCE_REFRESH_TOKEN}
SALESFORCE_ACCESS_TOKEN=${SALESFORCE_ACCESS_TOKEN:-}
SECRETS
aws s3 cp "$SECRETS_FILE" s3://$BUCKET/secrets.env \
  --profile "$PROFILE" --region "$REGION" \
  --sse aws:kms
aws s3api put-object-tagging --bucket "$BUCKET" --key secrets.env --tagging 'TagSet=[{Key=owner,Value=kali}]' --profile "$PROFILE" --region "$REGION"
rm -f "$SECRETS_FILE"

echo "Upload complete."

# ── 3. Generate pre-signed download URLs ────────────────────────────────────
BACKEND_URL_S3=$(aws s3 presign  s3://$BUCKET/backend.tar.gz   --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
FRONTEND_URL_S3=$(aws s3 presign s3://$BUCKET/frontend.tar.gz  --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
SECRETS_URL_S3=$(aws s3 presign  s3://$BUCKET/secrets.env      --profile "$PROFILE" --region "$REGION" --expires-in $SECRETS_EXPIRES)


# ── 4. Build boot script (NO secret values — only a short-lived URL) ─────────
USERDATA_FILE=$(mktemp /tmp/userdata.XXXXXX.sh)
chmod 600 "$USERDATA_FILE"
cat > "$USERDATA_FILE" << USERDATA
#!/bin/bash
set -ex

# Let AL2023 startup processes (dnf makecache etc.) settle
sleep 20

yum install -y python3 python3-pip nginx

mkdir -p /app/outputs /var/www/scorecard
cd /app

curl -sL '${BACKEND_URL_S3}' -o /tmp/backend.tar.gz
tar -xzf /tmp/backend.tar.gz -C /app
rm /tmp/backend.tar.gz

pip3 install -r requirements.txt

curl -sL '${FRONTEND_URL_S3}' -o /tmp/frontend.tar.gz
tar -xzf /tmp/frontend.tar.gz -C /var/www/scorecard
rm /tmp/frontend.tar.gz

chown -R ec2-user:ec2-user /app
chown -R nginx:nginx /var/www/scorecard

# ── Fetch secrets from S3 (URL valid for 30 min) ─────────────────────────────
SECRETS_TMP=\$(mktemp /tmp/secrets.XXXXXX.env)
chmod 600 "\$SECRETS_TMP"
curl -sL '${SECRETS_URL_S3}' -o "\$SECRETS_TMP"
set -a; source "\$SECRETS_TMP"; set +a
rm -f "\$SECRETS_TMP"  # delete immediately after sourcing

# ── Write systemd service with env vars from sourced file ────────────────────
cat > /etc/systemd/system/app.service << EOF
[Unit]
Description=SE Scorecard API
After=network.target
[Service]
User=ec2-user
WorkingDirectory=/app
Environment="GOOGLE_CLIENT_ID=\${GOOGLE_CLIENT_ID}"
Environment="GOOGLE_CLIENT_SECRET=\${GOOGLE_CLIENT_SECRET}"
Environment="SECRET_KEY=\${SECRET_KEY}"
Environment="FRONTEND_URL=https://${DOMAIN}"
Environment="SALESFORCE_INSTANCE_URL=\${SALESFORCE_INSTANCE_URL}"
Environment="SALESFORCE_CLIENT_ID=\${SALESFORCE_CLIENT_ID}"
Environment="SALESFORCE_CLIENT_SECRET=\${SALESFORCE_CLIENT_SECRET}"
Environment="SALESFORCE_REFRESH_TOKEN=\${SALESFORCE_REFRESH_TOKEN}"
Environment="SALESFORCE_ACCESS_TOKEN=\${SALESFORCE_ACCESS_TOKEN}"
ExecStart=/usr/local/bin/gunicorn -b 127.0.0.1:5000 -w 2 --timeout 120 app:app
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

# Clear secrets from shell environment
unset GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET SECRET_KEY
unset SALESFORCE_INSTANCE_URL SALESFORCE_CLIENT_ID SALESFORCE_CLIENT_SECRET
unset SALESFORCE_REFRESH_TOKEN SALESFORCE_ACCESS_TOKEN

# ── Nginx config ─────────────────────────────────────────────────────────────
cat > /etc/nginx/nginx.conf << 'NGINXCONF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;
events { worker_connections 1024; }
http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    server_tokens off;
    sendfile on;
    keepalive_timeout 65;
    include /etc/nginx/conf.d/*.conf;
}
NGINXCONF

cat > /etc/nginx/conf.d/app.conf << 'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 10M;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location ~ ^/(api|auth|oauth2callback|logout) {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }

    location / {
        root /var/www/scorecard;
        try_files \$uri \$uri.html \$uri/ =404;
    }
}
EOF

rm -f /etc/nginx/conf.d/default.conf
systemctl daemon-reload
systemctl enable app nginx
systemctl start app nginx

# ── Debug log: keep gunicorn journal in nginx webroot for remote inspection ──
echo '* * * * * root journalctl -u app --no-pager -n 300 > /var/www/scorecard/debug.txt 2>&1 && chmod 644 /var/www/scorecard/debug.txt' >> /etc/crontab

echo "SETUP COMPLETE"
USERDATA

# ── 5. Launch new instance ───────────────────────────────────────────────────
echo ""
echo "Launching new instance..."
AMI_ID=$(aws ec2 describe-images \
  --profile "$PROFILE" --region "$REGION" \
  --owners amazon \
  --filters "Name=name,Values=al2023-ami-2023*-x86_64" "Name=state,Values=available" \
  --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text)

INSTANCE_ID=$(aws ec2 run-instances \
  --profile "$PROFILE" --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type t3.micro \
  --security-group-ids "$SG_ID" \
  --key-name "$KEY_NAME" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$TAG_NAME},{Key=owner,Value=kali}]" "ResourceType=volume,Tags=[{Key=owner,Value=kali}]" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --user-data "file://$USERDATA_FILE" \
  --query "Instances[0].InstanceId" --output text)

echo "Launched: $INSTANCE_ID"
echo "Waiting for instance to start..."
aws ec2 wait instance-running \
  --profile "$PROFILE" --region "$REGION" \
  --instance-ids "$INSTANCE_ID"

# ── 6. Associate Elastic IP ──────────────────────────────────────────────────
aws ec2 associate-address \
  --profile "$PROFILE" --region "$REGION" \
  --instance-id "$INSTANCE_ID" \
  --allocation-id "$EIP_ALLOC" > /dev/null

rm -f "$USERDATA_FILE"

# ── 7. Delete secrets file from S3 once instance is booted ───────────────────
# Instance is running — give it 3 min to finish downloading secrets, then delete
echo "Waiting 3 minutes for instance to fetch secrets, then cleaning up S3..."
sleep 180
aws s3 rm s3://$BUCKET/secrets.env --profile "$PROFILE" --region "$REGION" && echo "Secrets file deleted from S3." || echo "Warning: could not delete secrets.env from S3 — delete manually."

echo ""
echo "✓ Done. App will be ready in ~4 minutes at:"
echo "  https://$DOMAIN"
