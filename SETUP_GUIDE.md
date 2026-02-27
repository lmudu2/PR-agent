# 🚀 PR Governance Agent — Self-Service Setup Guide

Get the full agent running against **your own GitHub repository** in under 15 minutes.

---

## Prerequisites

Before you start, make sure you have the following:

| Requirement | Notes |
|---|---|
| **AWS Account** | [Free tier works](https://aws.amazon.com/free/). You need permissions to create Lambda functions and configure SES. |
| **GitHub Account** | Any account with at least one repository to test against. |
| **Python 3.12+** | For running the deployment helper script. |
| **AWS CLI** | [Install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Run `aws configure` with your credentials. |

---

## Step 1: Get Your API Keys

You need at least one "Brain" key. You can skip the ones you don't want to test.

| Key | Where to Get It | Free Tier? |
|---|---|---|
| **GitHub PAT** | [github.com/settings/tokens](https://github.com/settings/tokens) → New token (classic) → Check `repo` scope | ✅ Free |
| **Groq API Key** (Llama 3) | [console.groq.com/keys](https://console.groq.com/keys) | ✅ Free |
| **Gemini API Key** | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) | ✅ Free |

> **Note**: The GitHub PAT needs at minimum: `repo` (full), `admin:repo_hook` scopes.

---

## Step 2: Clone the Repository

```bash
git clone https://github.com/lmudu2/PR-agent.git
cd PR-agent
```

---

## Step 3: Run the Automated Deployment Script

A single Python script handles creating all the Lambda functions with your credentials.

```bash
python3 deploy.py
```

The script will prompt you to enter your keys interactively (they are never saved to disk):

```
Enter your GitHub PAT: ****
Enter your Groq API Key (leave blank to skip): ****
Enter your Gemini API Key (leave blank to skip): ****
Enter your AWS SES email (for approval emails): you@example.com
```

It will then automatically:
1. **Zip** and deploy the `GitHub-PR-Risk-Reviewer` (Gateway) Lambda.
2. **Zip** and deploy the `PR-Agent-Brain` (Llama 3 by default) Lambda.
3. **Zip** and deploy the `PR-Agent-GitHub-Writer` Lambda.
4. **Print the Gateway Lambda Function URL** — this is your webhook endpoint.

---

## Step 4: Configure GitHub Webhook

1. Go to your GitHub Repository → **Settings** → **Webhooks** → **Add webhook**.
2. Paste the **Function URL** from the previous step into **Payload URL**.
3. Set **Content type** to `application/json`.
4. Select **"Let me select individual events"** and check:
   - ✅ Pushes
   - ✅ Pull requests
   - ✅ Issue comments
5. Click **Add webhook**.

---

## Step 5: Test It!

### Option A: Full Live Test
```bash
# Create a new branch with a low-risk change
git checkout -b test-my-agent
echo "# test" >> README.md
git add . && git commit -m "test: low risk change"
git push origin test-my-agent
```
Watch your GitHub — within seconds, the agent should:
1. ✅ Auto-create a Pull Request.
2. ✅ Run risk analysis and comment on the PR.
3. ✅ Auto-merge (low risk) or Auto-close (high risk).

### Option B: Colab Demo (No AWS Needed)
Open `PR_Agent_Colab.ipynb` in [Google Colab](https://colab.research.google.com/) and enter your keys when prompted.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Webhook returns `401` | Your `GITHUB_TOKEN` is expired. Regenerate at GitHub and update the Lambda env variable. |
| No PR auto-created | Check the Gateway Lambda's CloudWatch logs in the AWS Console. |
| Email not sending | Your SES email may need to be **verified** in the AWS SES console. |
| Groq `401` error | Your Groq API key is invalid or expired. Regenerate at console.groq.com. |

---

## How to Update Your Tokens Later

If a key expires, update it directly in the AWS Lambda console:

1. Open [console.aws.amazon.com/lambda](https://console.aws.amazon.com/lambda).
2. Select a function (e.g., `GitHub-PR-Risk-Reviewer`).
3. Go to **Configuration** → **Environment variables** → **Edit**.
4. Update the relevant key and click **Save**.

---

*Questions? Open an issue on the [GitHub repository](https://github.com/lmudu2/PR-agent/issues).*
