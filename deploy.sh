#!/bin/bash
# Full deploy script for GTM Hub
# Usage: bash deploy.sh
# Terminates any existing instance, uploads latest code, and launches a fresh one.
#
# FIRST TIME SETUP: Copy deploy.env.example → deploy.env and fill in your values.
# Use your Twilio username wherever you see [username] in the example — it is used
# to tag every AWS resource you create with {Key=owner,Value=your-username} so
# resources can be attributed and cleaned up per person.
#
# HTTPS: Terminated by CloudFront. EC2 serves HTTP only on port 80.
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
for var in OWNER PROFILE REGION BUCKET SG_ID TAG_NAME KEY_NAME EIP_ALLOC DOMAIN GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET SECRET_KEY FRONTEND_URL TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN; do
  if [ -z "${!var}" ]; then
    echo "ERROR: $var is not set in deploy.env"
    exit 1
  fi
done

# Warn if any app is missing its .env file
for example in backend/apps/*/.env.example; do
  env_file="${example%.example}"
  if [ ! -f "$env_file" ]; then
    echo "WARNING: $env_file not found — copy from $example and fill in values"
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

# ── 0. Build frontend + check for old instance in parallel ───────────────────
echo "Building frontend and checking for running instances..."

# Kick off instance lookup in background
OLD_IDS=""
_instance_check() {
  aws ec2 describe-instances \
    --profile "$PROFILE" --region "$REGION" \
    --filters "Name=tag:Name,Values=$TAG_NAME" "Name=instance-state-name,Values=running,pending" \
    --query "Reservations[].Instances[].InstanceId" \
    --output text
}
_INSTANCE_IDS_FILE=$(mktemp)
_instance_check > "$_INSTANCE_IDS_FILE" &
_INSTANCE_CHECK_PID=$!

# Kick off AMI lookup in background while build runs
AMI_CACHE_FILE=".ami-cache"
_ami_lookup() {
  aws ec2 describe-images \
    --profile "$PROFILE" --region "$REGION" \
    --owners amazon \
    --filters "Name=name,Values=al2023-ami-2023*-x86_64" "Name=state,Values=available" \
    --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text
}
# Refresh AMI cache if older than 7 days or missing
if [ ! -f "$AMI_CACHE_FILE" ] || [ "$(find "$AMI_CACHE_FILE" -mtime +7 2>/dev/null)" ]; then
  _ami_lookup > "$AMI_CACHE_FILE" &
  _AMI_LOOKUP_PID=$!
else
  _AMI_LOOKUP_PID=""
fi

# Build frontend (runs while instance check + AMI lookup run in background)
cd frontend
npm ci --silent
npm run build
cd ..
echo "Frontend built."

# Wait for background instance check
wait "$_INSTANCE_CHECK_PID"
OLD_IDS=$(cat "$_INSTANCE_IDS_FILE")
rm -f "$_INSTANCE_IDS_FILE"

# ── 1. Terminate any running instances with this tag ─────────────────────────
echo ""
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

# ── 2. Upload app files + secrets env to S3 (parallel, piped — no temp files) ─
echo ""
echo "Uploading files to S3..."

# Upload backend and frontend in parallel, tagging inline
tar -czf - -C backend . | aws s3 cp - s3://$BUCKET/backend.tar.gz \
  --profile "$PROFILE" --region "$REGION" &
_BACKEND_UPLOAD_PID=$!

tar -czf - -C frontend/build . | aws s3 cp - s3://$BUCKET/frontend.tar.gz \
  --profile "$PROFILE" --region "$REGION" &
_FRONTEND_UPLOAD_PID=$!

# Build and upload secrets while app bundles upload
SECRETS_FILE=$(mktemp /tmp/secrets.XXXXXX.env)
chmod 600 "$SECRETS_FILE"
cat > "$SECRETS_FILE" << SECRETS
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
SECRET_KEY=${SECRET_KEY}
FRONTEND_URL=https://${DOMAIN}
BUCKET=${BUCKET}
REGION=${REGION}
FIRESTORE_PROJECT=${FIRESTORE_PROJECT}
FIRESTORE_CREDENTIALS_B64=${FIRESTORE_CREDENTIALS_B64}
TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}
TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}
SALESFORCE_INSTANCE_URL=${SALESFORCE_INSTANCE_URL:-}
SALESFORCE_CLIENT_ID=${SALESFORCE_CLIENT_ID:-}
SALESFORCE_CLIENT_SECRET=${SALESFORCE_CLIENT_SECRET:-}
SALESFORCE_REFRESH_TOKEN=${SALESFORCE_REFRESH_TOKEN:-}
SALESFORCE_ACCESS_TOKEN=${SALESFORCE_ACCESS_TOKEN:-}
SECRETS
# Append each app's .env (skip lines that are comments or blank)
for app_env in backend/apps/*/.env; do
  if [ -f "$app_env" ]; then
    app_name=$(basename "$(dirname "$app_env")")
    echo "" >> "$SECRETS_FILE"
    echo "# ${app_name}" >> "$SECRETS_FILE"
    grep -v '^\s*#' "$app_env" | grep -v '^\s*$' >> "$SECRETS_FILE" || true
  fi
done
aws s3 cp "$SECRETS_FILE" s3://$BUCKET/secrets.env \
  --profile "$PROFILE" --region "$REGION" \
  --sse aws:kms &
_SECRETS_UPLOAD_PID=$!

# Wait for all uploads (check each individually so a failure isn't silently swallowed)
wait "$_BACKEND_UPLOAD_PID"  || { echo "ERROR: backend upload failed";  exit 1; }
wait "$_FRONTEND_UPLOAD_PID" || { echo "ERROR: frontend upload failed"; exit 1; }
wait "$_SECRETS_UPLOAD_PID"  || { rm -f "$SECRETS_FILE"; echo "ERROR: secrets upload failed"; exit 1; }
rm -f "$SECRETS_FILE"

# Tag all three objects in parallel (resource attribution)
aws s3api put-object-tagging --bucket "$BUCKET" --key backend.tar.gz  --tagging "TagSet=[{Key=owner,Value=$OWNER}]" --profile "$PROFILE" --region "$REGION" &
aws s3api put-object-tagging --bucket "$BUCKET" --key frontend.tar.gz --tagging "TagSet=[{Key=owner,Value=$OWNER}]" --profile "$PROFILE" --region "$REGION" &
aws s3api put-object-tagging --bucket "$BUCKET" --key secrets.env     --tagging "TagSet=[{Key=owner,Value=$OWNER}]" --profile "$PROFILE" --region "$REGION" &
wait
echo "Upload complete."

# ── 3. Generate pre-signed download URLs (parallel) ──────────────────────────
_BACKEND_PRESIGN_FILE=$(mktemp)
_FRONTEND_PRESIGN_FILE=$(mktemp)
_SECRETS_PRESIGN_FILE=$(mktemp)
chmod 600 "$_BACKEND_PRESIGN_FILE" "$_FRONTEND_PRESIGN_FILE" "$_SECRETS_PRESIGN_FILE"

aws s3 presign s3://$BUCKET/backend.tar.gz  --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES         > "$_BACKEND_PRESIGN_FILE"  &
_BACKEND_PRESIGN_PID=$!
aws s3 presign s3://$BUCKET/frontend.tar.gz --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES         > "$_FRONTEND_PRESIGN_FILE" &
_FRONTEND_PRESIGN_PID=$!
aws s3 presign s3://$BUCKET/secrets.env     --profile "$PROFILE" --region "$REGION" --expires-in $SECRETS_EXPIRES > "$_SECRETS_PRESIGN_FILE"  &
_SECRETS_PRESIGN_PID=$!
wait "$_BACKEND_PRESIGN_PID" || { echo "ERROR: backend presign failed"; exit 1; }
wait "$_FRONTEND_PRESIGN_PID" || { echo "ERROR: frontend presign failed"; exit 1; }
wait "$_SECRETS_PRESIGN_PID" || { echo "ERROR: secrets presign failed"; exit 1; }

BACKEND_URL_S3=$(cat "$_BACKEND_PRESIGN_FILE")
FRONTEND_URL_S3=$(cat "$_FRONTEND_PRESIGN_FILE")
SECRETS_URL_S3=$(cat "$_SECRETS_PRESIGN_FILE")
rm -f "$_BACKEND_PRESIGN_FILE" "$_FRONTEND_PRESIGN_FILE" "$_SECRETS_PRESIGN_FILE"

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
# Install as /app/secrets.env (read by systemd EnvironmentFile — never in user-data)
install -o root -g root -m 600 "\$SECRETS_TMP" /app/secrets.env
rm -f "\$SECRETS_TMP"

# ── Write systemd service ────────────────────────────────────────────────────
cat > /etc/systemd/system/app.service << 'EOF'
[Unit]
Description=GTM Hub API
After=network.target
[Service]
User=ec2-user
WorkingDirectory=/app
EnvironmentFile=/app/secrets.env
ExecStart=/usr/local/bin/gunicorn -b 127.0.0.1:5000 -w 2 --timeout 120 app:app
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

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
        try_files \$uri \$uri.html \$uri/ @fallback;
    }

    location @fallback {
        rewrite ^ /index.html last;
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

# ── 5. Resolve AMI and launch new instance ───────────────────────────────────
echo ""
echo "Launching new instance..."

# Wait for AMI lookup if it was running in background
if [ -n "$_AMI_LOOKUP_PID" ]; then
  wait "$_AMI_LOOKUP_PID"
fi
AMI_ID=$(cat "$AMI_CACHE_FILE")

INSTANCE_ID=$(aws ec2 run-instances \
  --profile "$PROFILE" --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type t3.micro \
  --security-group-ids "$SG_ID" \
  --key-name "$KEY_NAME" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$TAG_NAME},{Key=owner,Value=$OWNER}]" "ResourceType=volume,Tags=[{Key=owner,Value=$OWNER}]" \
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

# ── 7. Register Twilio SMS webhook ───────────────────────────────────────────
WEBHOOK_URL="https://${DOMAIN}/api/se-scorecard-v2/sms"
echo "Registering Twilio SMS webhook: $WEBHOOK_URL"
_PHONE_SID=$(curl -s -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" \
  "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/IncomingPhoneNumbers.json?PhoneNumber=%2B18446990268" \
  | python3 -c "import sys,json; nums=json.load(sys.stdin).get('incoming_phone_numbers',[]); print(nums[0]['sid'] if nums else '')" 2>/dev/null)
if [ -n "$_PHONE_SID" ]; then
  curl -s -X POST -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" \
    "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/IncomingPhoneNumbers/${_PHONE_SID}.json" \
    --data-urlencode "SmsUrl=${WEBHOOK_URL}" \
    --data-urlencode "SmsMethod=POST" > /dev/null
  echo "Webhook registered on phone SID ${_PHONE_SID}."
else
  echo "Warning: could not find phone number SID — set webhook manually in Twilio console to ${WEBHOOK_URL}"
fi

# ── 8. Delete secrets file from S3 once instance is booted ────────────────── once instance signals setup complete ───────
# Instance is running — give it 3 min to finish downloading secrets, then delete
echo "Waiting 3 minutes for instance to fetch secrets, then cleaning up S3..."
sleep 180
aws s3 rm s3://$BUCKET/secrets.env --profile "$PROFILE" --region "$REGION" && echo "Secrets file deleted from S3." || echo "Warning: could not delete secrets.env from S3 — delete manually."

echo ""
echo "✓ Done. App should be live now or within ~1 minute at:"
echo "  https://$DOMAIN"
