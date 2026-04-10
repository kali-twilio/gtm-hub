#!/bin/bash
# Full deploy script for SE Scorecard
# Usage: bash deploy.sh
# Terminates any existing instance, uploads latest code, and launches a fresh one.

set -e
cd "$(dirname "$0")"  # always run from the script's directory

# ── Load config ───────────────────────────────────────────────────────────────
if [ ! -f deploy.env ]; then
  echo "ERROR: deploy.env not found."
  echo "Copy deploy.env.example to deploy.env and fill in your values."
  exit 1
fi
source deploy.env

EXPIRES=7200  # pre-signed URL TTL in seconds (2 hours)

# ── 1. Terminate any running instances with this tag ─────────────────────────
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

# ── 2. Upload app files to S3 ────────────────────────────────────────────────
echo ""
echo "Uploading files to S3..."
aws s3 cp app.py            s3://$BUCKET/app.py            --profile "$PROFILE" --region "$REGION"
aws s3 cp requirements.txt  s3://$BUCKET/requirements.txt  --profile "$PROFILE" --region "$REGION"
aws s3 cp se_analysis.py    s3://$BUCKET/se_analysis.py    --profile "$PROFILE" --region "$REGION"
aws s3 cp se_rankings.py    s3://$BUCKET/se_rankings.py    --profile "$PROFILE" --region "$REGION"
aws s3 cp templates/index.html      s3://$BUCKET/templates/index.html      --profile "$PROFILE" --region "$REGION"
aws s3 cp templates/login.html      s3://$BUCKET/templates/login.html      --profile "$PROFILE" --region "$REGION"
aws s3 cp templates/se_profile.html s3://$BUCKET/templates/se_profile.html --profile "$PROFILE" --region "$REGION"
echo "Upload complete."

# ── 3. Generate pre-signed download URLs ────────────────────────────────────
APP_URL=$(aws s3 presign      s3://$BUCKET/app.py            --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
REQS_URL=$(aws s3 presign     s3://$BUCKET/requirements.txt  --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
ANALYSIS_URL=$(aws s3 presign s3://$BUCKET/se_analysis.py    --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
RANKINGS_URL=$(aws s3 presign s3://$BUCKET/se_rankings.py    --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
INDEX_URL=$(aws s3 presign      s3://$BUCKET/templates/index.html      --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
LOGIN_URL=$(aws s3 presign      s3://$BUCKET/templates/login.html      --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
SE_PROFILE_URL=$(aws s3 presign s3://$BUCKET/templates/se_profile.html --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)

# ── 4. Build boot script ─────────────────────────────────────────────────────
USERDATA_FILE=$(mktemp /tmp/userdata.XXXXXX.sh)
chmod 600 "$USERDATA_FILE"
cat > "$USERDATA_FILE" << USERDATA
#!/bin/bash
set -ex

# Let AL2023 startup processes (dnf makecache etc.) settle
sleep 20

yum install -y python3 python3-pip nginx augeas-libs
pip3 install certbot certbot-nginx

mkdir -p /app/templates /app/outputs
cd /app

curl -sL '${APP_URL}'      -o app.py
curl -sL '${REQS_URL}'     -o requirements.txt
curl -sL '${ANALYSIS_URL}' -o se_analysis.py
curl -sL '${RANKINGS_URL}' -o se_rankings.py
curl -sL '${INDEX_URL}'      -o templates/index.html
curl -sL '${LOGIN_URL}'      -o templates/login.html
curl -sL '${SE_PROFILE_URL}' -o templates/se_profile.html

pip3 install -r requirements.txt
chown -R ec2-user:ec2-user /app

cat > /etc/systemd/system/app.service << EOF
[Unit]
Description=SE Scorecard
After=network.target
[Service]
User=ec2-user
WorkingDirectory=/app
Environment="GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}"
Environment="GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}"
Environment="SECRET_KEY=$(openssl rand -hex 32)"
ExecStart=/usr/local/bin/gunicorn -b 127.0.0.1:5000 -w 2 --timeout 120 app:app
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

# Replace the full nginx.conf to avoid conflict with AL2023 default server block
cat > /etc/nginx/nginx.conf << 'NGINXCONF'
user nginx;
worker_processes auto;
server_tokens off;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;
events { worker_connections 1024; }
http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    include /etc/nginx/conf.d/*.conf;
}
NGINXCONF

cat > /etc/nginx/conf.d/app.conf << EOF
server {
    listen 80;
    server_name ${DOMAIN};
    client_max_body_size 20M;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host \\\$host;
        proxy_set_header   X-Real-IP \\\$remote_addr;
        proxy_set_header   X-Forwarded-Proto \\\$scheme;
        proxy_read_timeout 120s;
    }
}
EOF

rm -f /etc/nginx/conf.d/default.conf
systemctl daemon-reload
systemctl enable app nginx
systemctl start app nginx

# Get SSL cert and auto-configure nginx for HTTPS
certbot --nginx -d ${DOMAIN} \
  --non-interactive --agree-tos \
  -m ${CERTBOT_EMAIL} \
  --redirect

# Auto-renew certs (Let's Encrypt certs expire every 90 days)
echo "0 0,12 * * * root certbot renew --quiet" >> /etc/crontab

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
  --key-name se-scorecard-key \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$TAG_NAME}]" \
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

echo ""
echo "✓ Done. App will be ready in ~7 minutes at:"
echo "  https://$DOMAIN"
