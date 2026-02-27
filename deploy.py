#!/usr/bin/env python3
"""
PR Governance Agent — One-Command Deployment Script
Run: python3 deploy.py
"""
import subprocess
import os
import sys
import json
import zipfile
import shutil
from getpass import getpass

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
REGION = "us-east-1"
RUNTIME = "python3.12"
TIMEOUT = 300
MEMORY = 512

LAMBDAS = [
    {
        "name": "GitHub-PR-Risk-Reviewer",
        "folder": "GitHub-PR-Risk-Reviewer",
        "handler": "lambda_function.lambda_handler",
        "description": "Gateway: routes GitHub webhook events",
        "env_keys": ["GITHUB_TOKEN"]
    },
    {
        "name": "PR-Agent-Brain",
        "folder": "PR-Agent-Brain-Simple",
        "handler": "lambda_function.lambda_handler",
        "description": "Brain: AI risk analysis via Llama 3 / Gemini",
        "env_keys": ["GITHUB_TOKEN", "GROQ_API_KEY", "GOOGLE_API_KEY", "JIRA_EMAIL", "JIRA_TOKEN"]
    },
    {
        "name": "PR-Agent-GitHub-Writer",
        "folder": "PR-Agent-GitHub-Writer",
        "handler": "lambda_function.lambda_handler",
        "description": "Writer: executes GitHub / Jira actions",
        "env_keys": ["GITHUB_TOKEN", "JIRA_EMAIL", "JIRA_TOKEN"]
    }
]

def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Error: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()

def zip_folder(folder, output_zip):
    if os.path.exists(output_zip):
        os.remove(output_zip)
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(folder):
            # Skip __pycache__
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, folder)
                zf.write(filepath, arcname)
    print(f"  📦 Zipped {folder}/ → {output_zip}")

def get_or_create_role():
    """Get or create a basic Lambda execution role."""
    role_name = "pr-agent-lambda-role"
    try:
        result = run(f"aws iam get-role --role-name {role_name} --query Role.Arn --output text", check=False)
        if "arn:aws" in result:
            print(f"  ✅ Using existing IAM role: {role_name}")
            return result
    except:
        pass

    print(f"  🔧 Creating IAM role: {role_name} ...")
    trust = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    })
    arn = run(f"aws iam create-role --role-name {role_name} --assume-role-policy-document '{trust}' --query Role.Arn --output text")
    run(f"aws iam attach-role-policy --role-name {role_name} --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    import time; time.sleep(10)  # Wait for role propagation
    print(f"  ✅ IAM role created: {arn}")
    return arn

def deploy_lambda(config, env_vars, role_arn):
    name = config["name"]
    folder = config["folder"]
    zip_file = f"/tmp/{name}.zip"

    print(f"\n📦 Deploying {name}...")
    zip_folder(folder, zip_file)

    # Build env string (only include keys that have a value)
    env_str = ",".join([f"{k}={env_vars[k]}" for k in config["env_keys"] if env_vars.get(k)])
    env_param = f"--environment Variables={{{env_str}}}" if env_str else ""

    # Check if function already exists
    existing = run(f"aws lambda get-function --function-name {name} --region {REGION} --query Configuration.FunctionName --output text 2>/dev/null", check=False)

    if existing.strip() == name:
        print(f"  🔄 Updating existing function...")
        run(f"aws lambda update-function-code --function-name {name} --zip-file fileb://{zip_file} --region {REGION}")
        if env_str:
            run(f"aws lambda update-function-configuration --function-name {name} --environment Variables={{{env_str}}} --region {REGION}")
    else:
        print(f"  🆕 Creating new function...")
        run(f"""aws lambda create-function \
            --function-name {name} \
            --runtime {RUNTIME} \
            --role {role_arn} \
            --handler {config['handler']} \
            --zip-file fileb://{zip_file} \
            --timeout {TIMEOUT} \
            --memory-size {MEMORY} \
            {env_param} \
            --region {REGION}""")

    print(f"  ✅ {name} deployed!")
    return name

def add_function_url(function_name):
    """Add a public Function URL to a Lambda (for the gateway)."""
    existing = run(f"aws lambda get-function-url-config --function-name {function_name} --region {REGION} --query FunctionUrl --output text 2>/dev/null", check=False)
    if existing.startswith("https://"):
        print(f"  🔗 Existing Function URL: {existing}")
        return existing

    url = run(f"aws lambda create-function-url-config --function-name {function_name} --auth-type NONE --region {REGION} --query FunctionUrl --output text")
    run(f"aws lambda add-permission --function-name {function_name} --statement-id AllowPublicAccess --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE --region {REGION}")
    print(f"  🔗 Function URL created: {url}")
    return url


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  🤖 PR Governance Agent — Deployment Script")
    print("="*60 + "\n")

    # Check AWS CLI configured
    identity = run("aws sts get-caller-identity --query Account --output text", check=False)
    if not identity.isdigit():
        print("❌ AWS CLI is not configured. Run 'aws configure' first.")
        sys.exit(1)
    print(f"✅ AWS Account: {identity} | Region: {REGION}\n")

    # Collect credentials securely
    print("🔑 Enter your credentials (input is hidden):\n")
    env_vars = {
        "GITHUB_TOKEN":  getpass("GitHub PAT (required): "),
        "GROQ_API_KEY":  getpass("Groq API Key (for Llama 3, or press Enter to skip): "),
        "GOOGLE_API_KEY": getpass("Gemini API Key (or press Enter to skip): "),
        "JIRA_EMAIL":    input("Jira Email (or press Enter to skip): "),
        "JIRA_TOKEN":    getpass("Jira API Token (or press Enter to skip): "),
    }

    if not env_vars["GITHUB_TOKEN"]:
        print("❌ GitHub PAT is required.")
        sys.exit(1)

    # Get/create IAM role
    print("\n🔧 Setting up IAM role...")
    role_arn = get_or_create_role()

    # Deploy all Lambdas
    for config in LAMBDAS:
        deploy_lambda(config, env_vars, role_arn)

    # Add public URL to Gateway
    print("\n🌐 Configuring Gateway Function URL...")
    webhook_url = add_function_url("GitHub-PR-Risk-Reviewer")

    # Final instructions
    print("\n" + "="*60)
    print("  🎉 Deployment Complete!")
    print("="*60)
    print(f"""
Next step — Configure your GitHub Webhook:

  1. Go to your repo → Settings → Webhooks → Add webhook
  2. Payload URL:   {webhook_url}
  3. Content type:  application/json
  4. Events:        ✅ Pushes, Pull Requests, Issue Comments
  5. Click 'Add webhook'

Then push a branch to test:
  git checkout -b test-pr-agent
  echo "test" >> README.md
  git add . && git commit -m "test"
  git push origin test-pr-agent
""")
