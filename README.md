# 🤖 PR Governance Agent

[![Serverless](https://img.shields.io/badge/Serverless-AWS_Lambda-orange?style=flat-square&logo=amazon-aws)](https://aws.amazon.com/lambda/)
[![AI](https://img.shields.io/badge/AI-Multi--Model-blue?style=flat-square&logo=google-gemini)](https://deepmind.google/technologies/gemini/)
[![PRs](https://img.shields.io/badge/PRs-Automated-green?style=flat-square&logo=github)](https://github.com/)

> **"Push Code, Walk Away."** — The future of secure development.

## 🚀 Overview
The **PR Governance Agent** is an autonomous AI system that manages the entire lifecycle of code changes. It eliminates "Governance Fatigue" by automating the boring stuff (PR creation, basic checks) and strictly enforcing the critical stuff (Risk Analysis).

**Core Logic:**
1.  **Monitor**: Auto-detects code pushes.
2.  **Act**: Instantly creates a Pull Request.
3.  **Analyze**: AI (Llama 3, Gemini, or Bedrock) evaluates risk against internal policies.
4.  **Enforce**: 
    -   ⛔ **High Risk**: Auto-Closes the PR (Requires Manager Approval).
    -   ✅ **Low Risk**: Auto-Merges the PR (Automated).

## 🛠️ Architecture
-   **Brains**: 
    -   **Meta Llama 3 70B** (via Groq)
    -   **Google Gemini 2.0 Flash**
    -   **Claude 3 Sonnet** (via AWS Bedrock)
-   **Orchestration**: AWS Lambda (Python 3.12)
-   **Integration**: GitHub Webhooks & REST API
-   **Storage**: S3 / Local Context (Incident History, Policies)

## ✨ Features

| Feature | Description |
| :--- | :--- |
| **Auto-PR** | Developer pushes to a new branch -> Agent creates PR immediately. |
| **Risk Analysis** | Checks code against `deployment_policies.txt` and `incident_history.txt`. |
| **Auto-Close** | High-risk changes are physically closed to prevent accidental merging. |
| **Auto-Merge** | Safe changes are merged automatically without human intervention. |
| **Audit Trail** | Full synchronization with Jira for compliance. |
| **Colab Ready** | Test and demo the brains instantly without any cloud setup. |

## 📦 Installation

### Prerequisites
-   AWS Account (Lambda Access)
-   API Keys for your chosen brain (Groq, Gemini, or AWS)
-   GitHub Personal Access Token (Repo Scope)

### Deployment
1.  **Clone the Repo**:
    ```bash
    git clone https://github.com/lmudu2/PR-agent.git
    cd PR-agent
    ```

2.  **Configure Environment Variables** in AWS Lambda:
    -   `GITHUB_TOKEN`: Your GitHub PAT.
    -   `GROQ_API_KEY`: Your Groq API Key (for Llama 3).
    -   `GOOGLE_API_KEY`: Your Gemini API Key.

3.  **Deploy Lambdas**:
    -   Zip and upload `GitHub-PR-Risk-Reviewer` (Gateway).
    -   Zip and upload `PR-Agent-Brain` (Brain).

## 📖 Usage Guide

### The Automated Flow
1.  **Create Branch**: `git checkout -b feature-login-fix`
2.  **Push Code**: `git push origin feature-login-fix`
3.  **Done**: The Agent takes over. Watch your PR tab!

### 🧪 Google Colab (Live Demo)
1.  **Zero-Touch Demo**: Open the [Live Demo Notebook](https://colab.research.google.com/github/lmudu2/PR-agent/blob/main/PR_Agent_Demo.ipynb). 
    - *Best for seeing the full agent workflow (Branch -> PR -> AI Audit -> Jira -> Email).*
2.  **Internal Testing**: Open the [Brain Lab Notebook](https://colab.research.google.com/github/lmudu2/PR-agent/blob/main/PR_Agent_Colab.ipynb).
    - *Best for testing individual LLM brains (Gemini, Llama) locally.*

## 📄 Documentation
-   [Technical Specification](./docs/technical_specification.md)
-   [Architecture Overview](./CONSOLIDATED_ARCHITECTURE.md)
-   [E2E Test Guide](./E2E_TEST_GUIDE.md)

---
**Powered by Multi-Model AI** | Built for Speed & Security.
