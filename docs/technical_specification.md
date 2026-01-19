# PR Governance: The Risk Analysis Agent
**Technical Specification & Implementation Guide**

## 1. Introduction
<<<<<<< HEAD
In fast-paced development environments, the friction of manual Pull Request creation and the latency of human review often lead to "Governance Fatigue". Developers may bypass checks to ship faster, while reviewers might rubber-stamp changes without proper context. The Change Risk Analysis Agent addresses this by fully automating the lifecycle of code changes—from the initial code push to the final merge—ensuring that governance is active, invisible, and strictly enforced
=======
In fast-paced development environments, the friction of manual Pull Request creation and the latency of human review often lead to "Governance Fatigue". Developers may bypass checks to ship faster, while reviewers might rubber-stamp changes without proper context. The Change Risk Analysis Agent addresses this by fully automating the lifecycle of code changes—from the initial code push to the final merge—ensuring that governance is active, invisible, and strictly enforced.
>>>>>>> 382bc5f (Final V2 Release: Llama 3 Migration, Loop Fixes, Jira Integration)

## 2. Objective
To achieve a "Zero Touch" developer experience while maintaining strict security posture:
- **Eliminate Manual Toil**: Automatically recognize code pushes and generate formatted Pull Requests immediately.
- **Contextual Risk Analysis**: Instantly evaluate changes against `deployment_policies.txt` and `incident_history.txt` to predict downstream impact.
- **Enforce Gatekeeper Logic**: Proactively "Auto-Close" high-risk PRs to physically prevent merging until specific approval is granted.
- **Loop Prevention**: Smart detection of agent-initiated actions (Merge/Re-open) to prevent infinite analysis loops.
- **Accelerate Happy Paths**: Automatically merge low-risk changes without human intervention.

## 3. Solution Architecture
The system employs a Serverless Event-Driven Architecture leveraging AWS Lambda for orchestration and **Meta Llama 3 70B** for reasoning.

| Layer | Component | Function |
| :--- | :--- | :--- |
| **Interface Layer** | GitHub Webhooks | Captures `push` (code updates), `pull_request` (creation/sync), and `issue_comment` (approvals) events. |
| **Orchestration Layer** | AWS Lambda (Gateway) | Routes events: triggers Auto-PR for pushes, inputs for formatting, or Risk Analysis for PRs. |
| **Knowledge Layer** | Local Context Files | Stores policies and incident history directly within the inference execution environment context. |
| **Monitor Layer** | **Meta Llama 3 70B** | Performs ultra-fast (<1s) multi-step reasoning to diff code, semantic analysis, and risk scoring. |
| **Execution Layer** | AWS Lambda (Writer) | Performs side-effects: Creating PRs via API, posting comments, closing/reopening/merging PRs, and **updating Jira**. |

## 4. Personas & ROI Benefits
- **Developer**: "Zero Touch" experience. pushes code and walks away. If it's safe, it's merged automatically. If not, they get immediate feedback.
- **Security Lead**: "Zero Trust" enforcement. High-risk code is physically blocked (Closed) by default, requiring an audit trail for re-opening.
- **IT Manager**: Full compliance visibility via Jira integration for every approval and rejection.

## 5. Agent Logic & Flow
The agent follows a **Monitor-Analyze-Act** cycle:

1.  **Ingestion ("Auto-PR")**:
    -   User pushes to a new branch (e.g., `feature-login`).
    -   Gateway Lambda detects the push and checks for an existing PR.
    -   **Action**: If none exists, it hits the GitHub API to **Create Pull Request** immediately.
2.  **Retrieval & Reasoning ("Risk Analysis")**:
    -   The `pull_request` creation event triggers the Brain.
    -   **Loop Guard**: Gateway ignores events if the sender is a bot OR if the last comment indicates "Risk Accepted".
    -   **Context Injection**: The agent reads `incident_history.txt` (e.g., "Login refactor caused 404 in June").
    -   **Heuristic Check**: Compares code diff against `deployment_policies.txt` (e.g., "No DB schema changes on Fridays").
3.  **Decision & Execution**:
    -   **HIGH RISK**:
        -   **Action**: **Auto-Close PR**.
        -   **Output**: "⛔ Blocked: High Risk detected. Manager approval required to re-open."
    -   **LOW RISK**:
        -   **Action**: **Auto-Merge PR**.
        -   **Output**: "✅ Approved: Low risk change detected. Merging..."

## 6. Technical Implementation
-   **Foundational Model**: **Meta Llama 3 70B**.
-   **Orchestrator**: AWS Lambda (Python 3.12+).
-   **Data Source**: Flat-file Context (`.txt` files zipped with Lambda).
-   **GitHub Integration**: `urllib` (Standard Library) authentication via GitHub PAT.
-   **Gov Integration**: Jira API (Comments on existing tickets supported).

## 7. Use Case Scenarios

| Scenario | Input Signal | AI Logic | Result |
| :--- | :--- | :--- | :--- |
| **Safe Fix** | Push to `fix-css-typo` | Diff shows CSS only. Risk is 'LOW'. | **AUTO-PR** → **AUTO-MERGE** (Zero Touch) |
| **Dangerous Change** | Push to `refactor-auth` | Diff shows DB drop. Matches Policy 'No-Data-Loss'. | **AUTO-PR** → **AUTO-CLOSE** (Blocked) |
| **Policy Violation** | Push during Freeze | Checks Date vs `deployment_policies.txt`. | **AUTO-CLOSE** (Policy Block) |
| **Approval** | Comment "Approved" | Verifies User Permissions. | **RE-OPEN** → **AUTO-MERGE** |

## 8. Conclusion
The Zero Touch PR Governance Agent transforms the PR process from a passive waiting game into an active, intelligent workflow. By automating the bureaucratic steps (PR creation, basic review, merging) and strictly enforcing the critical ones (High Risk gating), it creates a development pipeline that is simultaneously faster and safer.

## 9. Appendix: Production Stack
-   **Webhooks**: Direct GitHub payloads to AWS Lambda Function URLs / API Gateway.
-   **Auth**: Environment Variables (`GITHUB_TOKEN`, `GROQ_API_KEY`).
-   **Logging**: AWS CloudWatch for full trace audit.
