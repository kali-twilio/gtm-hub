# Deploying a Flask App on AWS Behind Zscaler

## Overview

This guide deploys a Flask app to AWS EC2 that is **only accessible from the Twilio corporate network via Zscaler**. No password, no VPN client — employees on the Twilio network can reach it automatically. Anyone outside gets a connection timeout.

```
Twilio Employee → Zscaler (corporate proxy) → your EC2 instance
Outside world   →                           → connection timeout
```

---

## Security Model

| What | How |
|------|-----|
| Network access | Security group restricts port 80 to Twilio's Zscaler IP range only |
| No credentials in code | AWS SSO is used — no access keys or secrets in any file |
| No open SSH | Port 22 is not opened. The instance configures itself at boot |
| App not directly exposed | nginx sits in front of your app — the app never binds to a public port |

> **Always use port 80.** Zscaler only proxies standard web ports. Non-standard ports (e.g. 5000, 8080) will silently fail for all employees even on the Twilio network.

---

## Prerequisites

- **AWS CLI v2** — [install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **Access to a Twilio AWS account** via Okta SSO
- **Zscaler Client Connector** running on your machine (standard on Twilio laptops)

### Configure your AWS profile

Add the following to `~/.aws/config`. Replace `YOUR_ACCOUNT_ID` with the 12-digit AWS account number you are deploying to.

```ini
[profile my-app]
sso_session    = twilio-identity-center
sso_account_id = YOUR_ACCOUNT_ID
sso_role_name  = Standard_PowerUser
region         = us-west-2

[sso-session twilio-identity-center]
sso_start_url = https://twilio-us-east-1.awsapps.com/start
sso_region    = us-east-1
sso_registration_scopes = sso:account:access
```

Log in:

```bash
aws sso login --sso-session twilio-identity-center
```

Re-run this whenever your session expires (typically every 8 hours).

---

## One-Time Infrastructure Setup

Run these steps once per AWS account. If the resources already exist, skip to [Deploy](#deploy).

### 1. Create a key pair

```bash
aws ec2 create-key-pair \
  --profile my-app \
  --key-name my-app-key \
  --query "KeyMaterial" \
  --output text > ~/.ssh/my-app-key.pem

chmod 400 ~/.ssh/my-app-key.pem
```

> Keep this file safe. Never commit it to git or share it over Slack. If lost, delete the key pair in AWS and create a new one.

### 2. Create the security group

```bash
VPC_ID=$(aws ec2 describe-vpcs \
  --profile my-app \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" --output text)

SG_ID=$(aws ec2 create-security-group \
  --profile my-app \
  --group-name my-app-sg \
  --description "Zscaler-only access" \
  --vpc-id $VPC_ID \
  --query "GroupId" --output text)

aws ec2 authorize-security-group-ingress \
  --profile my-app \
  --group-id $SG_ID \
  --ip-permissions \
    "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=170.85.0.0/16,Description=Twilio Zscaler}]"

echo "Security Group ID: $SG_ID"
```

Note down the `SG_ID` — you will need it for every deploy.

### 3. Create an S3 bucket

```bash
BUCKET="my-app-deploy-$(date +%s)"

aws s3 mb s3://$BUCKET \
  --profile my-app \
  --region us-west-2

echo "Bucket: $BUCKET"
```

Note down the bucket name — you will reuse it for every deploy.

---

## Deploy

Run these steps every time you deploy or redeploy.

### 1. Upload your app files to S3

```bash
BUCKET="YOUR_BUCKET_NAME"

aws s3 cp app.py           s3://$BUCKET/app.py           --profile my-app --region us-west-2
aws s3 cp requirements.txt s3://$BUCKET/requirements.txt --profile my-app --region us-west-2

# Upload any additional files your app needs, e.g.:
# aws s3 cp templates/index.html s3://$BUCKET/templates/index.html --profile my-app --region us-west-2
```

> **Why S3?** The EC2 instance has no AWS credentials, so it can't access S3 directly. Pre-signed URLs (step 2) give it temporary, expiring download links — no credentials needed on the instance.

### 2. Generate pre-signed download URLs

These expire after 2 hours. If the instance takes longer to boot, regenerate them and relaunch.

```bash
APP_URL=$(aws s3 presign s3://$BUCKET/app.py \
  --profile my-app --region us-west-2 --expires-in 7200)

REQS_URL=$(aws s3 presign s3://$BUCKET/requirements.txt \
  --profile my-app --region us-west-2 --expires-in 7200)

# Add a presign command for each additional file you uploaded
```

### 3. Build the boot script

This script runs automatically when the instance first starts. It installs dependencies, downloads your app from S3, and starts everything.

```bash
cat > /tmp/userdata.sh << USERDATA
#!/bin/bash
set -e
exec > /var/log/app-setup.log 2>&1

yum update -y
yum install -y python3 python3-pip nginx

mkdir -p /app/templates
cd /app

# Download app files
curl -sL '${APP_URL}'  -o app.py
curl -sL '${REQS_URL}' -o requirements.txt
# Add a curl line for each additional file

pip3 install -r requirements.txt
chown -R ec2-user:ec2-user /app

# Run the app internally on localhost only (never exposed publicly)
cat > /etc/systemd/system/app.service << 'EOF'
[Unit]
Description=My App
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

# nginx listens on port 80 and forwards to the app
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
```

### 4. Launch the instance

```bash
SG_ID="YOUR_SECURITY_GROUP_ID"

AMI_ID=$(aws ec2 describe-images \
  --profile my-app --region us-west-2 \
  --owners amazon \
  --filters "Name=name,Values=al2023-ami-2023*-x86_64" "Name=state,Values=available" \
  --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text)

INSTANCE_ID=$(aws ec2 run-instances \
  --profile my-app --region us-west-2 \
  --image-id $AMI_ID \
  --instance-type t3.micro \
  --key-name my-app-key \
  --security-group-ids $SG_ID \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=my-app}]" \
  --user-data file:///tmp/userdata.sh \
  --query "Instances[0].InstanceId" --output text)

echo "Launched: $INSTANCE_ID — waiting for it to start..."

aws ec2 wait instance-running \
  --profile my-app --region us-west-2 \
  --instance-ids $INSTANCE_ID

PUBLIC_IP=$(aws ec2 describe-instances \
  --profile my-app --region us-west-2 \
  --instance-ids $INSTANCE_ID \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

echo "Done. Open in a Twilio browser: http://$PUBLIC_IP"
```

Wait ~3 minutes for the setup script to finish, then open the URL in your browser. It will not load from outside the Twilio network.

---

## Redeploy After Code Changes

1. Upload changed files to S3 (step 1)
2. Terminate the old instance:
   ```bash
   aws ec2 terminate-instances \
     --profile my-app --region us-west-2 \
     --instance-ids YOUR_INSTANCE_ID
   ```
3. Repeat steps 2–4

> The IP address changes on every redeploy. If you need a stable URL, ask your AWS admin to allocate an Elastic IP and associate it after launch.

---

## Troubleshooting

**Page won't load in the browser**
- Check that Zscaler Client Connector is running (system tray icon)
- Wait the full 3 minutes after launch — `yum update` takes time on first boot

**Connection times out outside of Twilio network**
- This is expected behaviour. The security group blocks all non-Zscaler traffic.

**SSO session expired**
```bash
aws sso login --sso-session twilio-identity-center
```

**Check what happened during boot**
The full setup log is written to `/var/log/app-setup.log` on the instance.
