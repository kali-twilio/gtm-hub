#!/bin/bash
# Full deploy script for SE Scorecard
# Usage: bash deploy.sh
# Terminates any existing instance, uploads latest code, and launches a fresh one.

set -e

PROFILE="290549574947_Standard_PowerUser"
REGION="us-west-2"
BUCKET="se-scorecard-deploy-1775761654"
SG_ID="sg-009ff23d837b491dc"
TAG_NAME="se-team-dev-twilio"
EIP_ALLOC="eipalloc-0b1f06fb219e5ea52"  # permanent IP: 44.230.217.150
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
aws s3 cp templates/index.html s3://$BUCKET/templates/index.html --profile "$PROFILE" --region "$REGION"
aws s3 cp templates/login.html s3://$BUCKET/templates/login.html --profile "$PROFILE" --region "$REGION"
echo "Upload complete."

# ── 3. Generate pre-signed download URLs ────────────────────────────────────
APP_URL=$(aws s3 presign      s3://$BUCKET/app.py            --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
REQS_URL=$(aws s3 presign     s3://$BUCKET/requirements.txt  --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
ANALYSIS_URL=$(aws s3 presign s3://$BUCKET/se_analysis.py    --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
RANKINGS_URL=$(aws s3 presign s3://$BUCKET/se_rankings.py    --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
INDEX_URL=$(aws s3 presign    s3://$BUCKET/templates/index.html --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)
LOGIN_URL=$(aws s3 presign    s3://$BUCKET/templates/login.html --profile "$PROFILE" --region "$REGION" --expires-in $EXPIRES)

# ── 4. Build boot script ─────────────────────────────────────────────────────
cat > /tmp/userdata.sh << USERDATA
#!/bin/bash
set -e
exec > /var/log/app-setup.log 2>&1

yum update -y
yum install -y python3 python3-pip nginx

mkdir -p /app/templates /app/outputs
cd /app

curl -sL '${APP_URL}'      -o app.py
curl -sL '${REQS_URL}'     -o requirements.txt
curl -sL '${ANALYSIS_URL}' -o se_analysis.py
curl -sL '${RANKINGS_URL}' -o se_rankings.py
curl -sL '${INDEX_URL}'    -o templates/index.html
curl -sL '${LOGIN_URL}'    -o templates/login.html

pip3 install -r requirements.txt
chown -R ec2-user:ec2-user /app

cat > /etc/systemd/system/app.service << 'EOF'
[Unit]
Description=SE Scorecard
After=network.target
[Service]
User=ec2-user
WorkingDirectory=/app
ExecStart=/usr/local/bin/gunicorn -b 127.0.0.1:5000 -w 2 --timeout 120 app:app
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/nginx/conf.d/app.conf << 'EOF'
server {
    listen 80;
    client_max_body_size 20M;
    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_read_timeout 120s;
    }
}
EOF

rm -f /etc/nginx/conf.d/default.conf
systemctl daemon-reload
systemctl enable app nginx
systemctl start app nginx
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
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$TAG_NAME}]" \
  --user-data file:///tmp/userdata.sh \
  --query "Instances[0].InstanceId" --output text)

echo "Launched: $INSTANCE_ID"
echo "Waiting for instance to start..."
aws ec2 wait instance-running \
  --profile "$PROFILE" --region "$REGION" \
  --instance-ids "$INSTANCE_ID"

PUBLIC_IP=$(aws ec2 describe-instances \
  --profile "$PROFILE" --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

# ── 6. Associate Elastic IP ──────────────────────────────────────────────────
aws ec2 associate-address \
  --profile "$PROFILE" --region "$REGION" \
  --instance-id "$INSTANCE_ID" \
  --allocation-id "$EIP_ALLOC" > /dev/null

echo ""
echo "✓ Done. App will be ready in ~3 minutes at:"
echo "  http://44.230.217.150"
