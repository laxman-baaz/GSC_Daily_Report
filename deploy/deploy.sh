#!/usr/bin/env bash
# One-shot deploy of the GSC daily report to AWS Lambda (container image) +
# EventBridge Scheduler (fires 06:00 Asia/Kolkata, exactly, every day).
#
# Idempotent: safe to re-run to ship new code or rotate secrets.
#
# Prereqs: run from the repo root, in an env with docker + aws CLI + credentials
# (AWS CloudShell has all three). A secrets file (default: ./secrets.env, same
# KEY=VALUE format as .env) must exist next to this repo.
#
# Usage:
#   bash deploy/deploy.sh                 # uses ./secrets.env, region ap-south-1
#   REGION=ap-south-1 SECRETS=./secrets.env bash deploy/deploy.sh
set -euo pipefail

REGION="${REGION:-ap-south-1}"                 # Mumbai
SECRETS="${SECRETS:-./secrets.env}"
FN="${FN:-gsc-daily-report}"
REPO="${REPO:-gsc-daily-report}"
SCHEDULE="${SCHEDULE:-gsc-daily-6am-ist}"
TZ_NAME="${TZ_NAME:-Asia/Kolkata}"
CRON="${CRON:-cron(0 6 * * ? *)}"              # 06:00 daily, in TZ_NAME
LAMBDA_ROLE="gsc-report-lambda-role"
SCHED_ROLE="gsc-report-scheduler-role"

[ -f "$SECRETS" ] || { echo "ERROR: secrets file '$SECRETS' not found. Copy deploy/secrets.env.example and fill it."; exit 1; }

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${ECR}/${REPO}:latest"
echo ">> Account ${ACCOUNT}, region ${REGION}"

echo ">> [1/7] Ensuring ECR repo '${REPO}'"
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null

echo ">> [2/7] Building & pushing image"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR"
docker build -t "${REPO}:latest" .
docker tag "${REPO}:latest" "$IMAGE"
docker push "$IMAGE"

echo ">> [3/7] Lambda execution role"
if ! aws iam get-role --role-name "$LAMBDA_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$LAMBDA_ROLE" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$LAMBDA_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "   waiting for role to propagate..."; sleep 12
fi
LAMBDA_ROLE_ARN="$(aws iam get-role --role-name "$LAMBDA_ROLE" --query Role.Arn --output text)"

echo ">> [4/7] Building env.json from ${SECRETS}"
python3 deploy/build_env_json.py "$SECRETS" env.json

echo ">> [5/7] Creating/updating Lambda '${FN}'"
if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FN" --image-uri "$IMAGE" --region "$REGION" >/dev/null
  aws lambda wait function-updated --function-name "$FN" --region "$REGION"
  aws lambda update-function-configuration --function-name "$FN" --region "$REGION" \
    --timeout 120 --memory-size 512 --environment file://env.json >/dev/null
else
  aws lambda create-function --function-name "$FN" --package-type Image \
    --code ImageUri="$IMAGE" --role "$LAMBDA_ROLE_ARN" --region "$REGION" \
    --timeout 120 --memory-size 512 --environment file://env.json >/dev/null
fi
aws lambda wait function-updated --function-name "$FN" --region "$REGION"
FN_ARN="$(aws lambda get-function --function-name "$FN" --region "$REGION" --query Configuration.FunctionArn --output text)"
rm -f env.json
echo "   Lambda ARN: ${FN_ARN}"

echo ">> [6/7] Scheduler role"
if ! aws iam get-role --role-name "$SCHED_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$SCHED_ROLE" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"scheduler.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  echo "   waiting for role to propagate..."; sleep 12
fi
aws iam put-role-policy --role-name "$SCHED_ROLE" --policy-name invoke-lambda \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"${FN_ARN}\"}]}"
SCHED_ROLE_ARN="$(aws iam get-role --role-name "$SCHED_ROLE" --query Role.Arn --output text)"

echo ">> [7/7] Creating/updating schedule '${SCHEDULE}' (${CRON} ${TZ_NAME})"
TARGET="{\"Arn\":\"${FN_ARN}\",\"RoleArn\":\"${SCHED_ROLE_ARN}\"}"
if aws scheduler get-schedule --name "$SCHEDULE" --region "$REGION" >/dev/null 2>&1; then
  aws scheduler update-schedule --name "$SCHEDULE" --region "$REGION" \
    --schedule-expression "$CRON" --schedule-expression-timezone "$TZ_NAME" \
    --flexible-time-window '{"Mode":"OFF"}' --target "$TARGET" >/dev/null
else
  aws scheduler create-schedule --name "$SCHEDULE" --region "$REGION" \
    --schedule-expression "$CRON" --schedule-expression-timezone "$TZ_NAME" \
    --flexible-time-window '{"Mode":"OFF"}' --target "$TARGET" >/dev/null
fi

echo ""
echo "DONE. Daily send at 06:00 ${TZ_NAME}."
echo "Test now:   aws lambda invoke --function-name ${FN} --region ${REGION} /dev/stdout"
echo "Logs:       aws logs tail /aws/lambda/${FN} --region ${REGION} --follow"
