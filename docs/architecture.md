# PR Agent - Zero Touch Architecture

## System Overview
Fully automated PR governance system with Risk Analysis, Auto-Close, and Auto-Merge capabilities.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Developer Actions"
        DEV[Developer]
        DEV -->|1. Push Code| GIT[GitHub Repository]
    end
    
    subgraph "GitHub"
        GIT -->|2. Webhook Event<br/>Push/PR/Comment| WH[GitHub Webhook]
    end
    
    subgraph "AWS Lambda - Gateway"
        WH -->|3. HTTP POST| GATE[GitHub-PR-Risk-Reviewer<br/>Gateway Lambda]
        GATE -->|4a. Push Event| AUTOPR[Auto-PR Logic]
        GATE -->|4b. PR Event| RISK[Risk Analysis Trigger]
        GATE -->|4c. Comment Event| CMD[Command Router]
    end
    
    subgraph "AWS Lambda - Brain"
        AUTOPR -->|5. Create PR via API| GIT
        RISK -->|6. Analyze Risk| BRAIN[PR-Agent-Brain<br/>Brain Lambda]
        CMD -->|6. Approval/Rejection| BRAIN
        BRAIN -->|7. AI Analysis| GEMINI[Google Gemini API]
        GEMINI -->|8. Risk Score| BRAIN
    end
    
    subgraph "Decision Engine"
        BRAIN -->|9a. High Risk| CLOSE[Auto-Close PR]
        BRAIN -->|9b. Low Risk| MERGE[Auto-Merge PR]
        BRAIN -->|9c. Pending| APPROVE[Wait for Approval]
    end
    
    subgraph "Governance & Audit"
        CLOSE -->|10. Update Ticket| JIRA[Jira API]
        APPROVE -->|10. Create Ticket| JIRA
        MERGE -->|10. Update Ticket| JIRA
        BRAIN -->|11. Send Email| SES[AWS SES]
    end
    
    subgraph "GitHub Actions"
        CLOSE -->|12. Close PR| GIT
        MERGE -->|12. Merge PR| GIT
        APPROVE -->|13. Set Status Check| GIT
        BRAIN -->|14. Post Comments| WRITER[PR-Agent-GitHub-Writer<br/>Writer Lambda]
        WRITER -->|15. GitHub API| GIT
    end
    
    style DEV fill:#e1f5ff
    style GATE fill:#fff4e6
    style BRAIN fill:#fff4e6
    style WRITER fill:#fff4e6
    style GEMINI fill:#f3e5f5
    style JIRA fill:#e8f5e9
    style SES fill:#e8f5e9
    style GIT fill:#fce4ec
```

## Detailed Flow Diagrams

### Flow 1: Zero Touch - Push to Auto-PR

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant GH as GitHub
    participant GW as Gateway Lambda
    participant API as GitHub API
    
    Dev->>GH: git push origin feature-xyz
    GH->>GW: Webhook: push event
    Note over GW: Detects: ref=refs/heads/feature-xyz
    GW->>API: Check if PR exists for branch
    API-->>GW: No PR found
    GW->>API: Create Pull Request
    Note over API: Title: "Auto-PR: feature-xyz"
    API-->>GH: PR Created (#123)
    GH->>GW: Webhook: pull_request opened
    Note over GW: Triggers Risk Analysis →
```

### Flow 2: Risk Analysis - High Risk Path

```mermaid
sequenceDiagram
    participant GH as GitHub
    participant GW as Gateway
    participant BR as Brain Lambda
    participant GM as Gemini API
    participant JR as Jira
    
    GH->>GW: PR Opened/Synced
    GW->>BR: Trigger Risk Analysis
    BR->>GH: Set Status: Pending
    BR->>GM: Analyze PR Changes
    Note over GM: Reviews code, checks<br/>incident history
    GM-->>BR: Risk Level: HIGH
    BR->>GH: Set Status: FAILURE
    BR->>GH: Close PR
    BR->>JR: Create Approval Ticket
    BR->>GH: Comment: "⛔ Blocked - High Risk"
    Note over GH: PR is CLOSED<br/>Merge button disabled
```

### Flow 3: Approval Workflow

```mermaid
sequenceDiagram
    participant User as Approver
    participant GH as GitHub
    participant GW as Gateway
    participant BR as Brain Lambda
    participant JR as Jira
    
    User->>GH: Comment: "approved"
    GH->>GW: Webhook: issue_comment
    GW->>BR: Handle Approval
    BR->>GH: Set Status: SUCCESS
    BR->>GH: Reopen PR
    BR->>GH: Merge PR
    BR->>JR: Update Ticket: Approved
    BR->>GH: Comment: "✅ Approved & Merged"
    Note over GH: PR is MERGED<br/>Branch deleted
```

### Flow 4: Happy Path - Auto-Merge

```mermaid
sequenceDiagram
    participant GH as GitHub
    participant GW as Gateway
    participant BR as Brain Lambda
    participant GM as Gemini API
    participant JR as Jira
    
    GH->>GW: PR Opened
    GW->>BR: Trigger Risk Analysis
    BR->>GM: Analyze PR Changes
    GM-->>BR: Risk Level: LOW
    BR->>GH: Set Status: SUCCESS
    BR->>GH: Merge PR
    BR->>JR: Update Ticket: Auto-Merged
    BR->>GH: Comment: "✅ Low Risk - Auto-Merged"
    Note over GH: PR Merged<br/>No human intervention
```

## Component Details

### 1. GitHub-PR-Risk-Reviewer (Gateway Lambda)
- **Purpose**: Entry point for all GitHub events
- **Events Handled**:
  - `push` → Auto-PR creation
  - `pull_request` → Risk analysis trigger
  - `issue_comment` → Command routing
- **Fast Path Operations**: Branch creation, deletion, listing (no AI needed)

### 2. PR-Agent-Brain (Brain Lambda)
- **Purpose**: Risk analysis and decision engine
- **Key Functions**:
  - AI-powered risk assessment via Gemini
  - Approval workflow management
  - Auto-Close/Auto-Merge logic
  - Jira integration
  - GitHub status checks

### 3. PR-Agent-GitHub-Writer (Writer Lambda)
- **Purpose**: GitHub API operations
- **Operations**:
  - Post comments
  - Create/delete branches
  - Manage PR state

### 4. External Services
- **Google Gemini API**: AI risk analysis using incident history and policies
- **Jira API**: Governance audit trail and approval tracking
- **AWS SES**: Email notifications for high-risk PRs

## Data Flow

```mermaid
graph LR
    A[Push Event] -->|Branch Name| B[Auto-PR Logic]
    B -->|PR Number| C[Risk Analysis]
    C -->|Code Diff| D[Gemini AI]
    D -->|Risk Score| E{Decision}
    E -->|HIGH| F[Close + Jira Ticket]
    E -->|LOW| G[Merge + Update Jira]
    E -->|MEDIUM| F
    F -->|Approval Comment| H[Reopen + Merge]
    H -->|Success| G
```

## Security & Governance

### Zero Trust Enforcement
1. **All** code changes trigger AI analysis
2. High-risk PRs are **physically closed** (Free Tier workaround)
3. Approval requires explicit human comment
4. Every action logged to Jira

### Audit Trail
- **GitHub Comments**: Timestamped decision records
- **Jira Tickets**: Approval requests and outcomes
- **Status Checks**: Visual PR state indicators
- **Lambda Logs**: Full event trace in CloudWatch

## Configuration

### Required GitHub Webhook Events
- ✅ Pushes
- ✅ Pull requests
- ✅ Issue comments

### Environment Variables
```bash
# Gateway Lambda
GITHUB_TOKEN=<PAT with repo access>

# Brain Lambda
GITHUB_TOKEN=<PAT with repo access>
GOOGLE_API_KEY=<Gemini API key>
```

## Key Features

| Feature | Description | Benefit |
|---------|-------------|---------|
| **Auto-PR** | Creates PR on branch push | Zero manual PR creation |
| **Risk Analysis** | AI evaluates every change | Prevents bad code |
| **Auto-Close** | Blocks high-risk PRs | Free Tier enforcement |
| **Auto-Merge** | Merges safe PRs | Faster deployment |
| **Jira Sync** | Audit trail | Compliance ready |
| **Status Checks** | Visual indicators | Clear PR state |

## Workflow Summary

```
Developer Push
    ↓
Auto-PR Created
    ↓
AI Risk Analysis
    ↓
┌─────────────┬──────────────┐
│   HIGH      │     LOW      │
│   RISK      │     RISK     │
└─────────────┴──────────────┘
    ↓                ↓
Auto-Close      Auto-Merge
    ↓                ✓
Approval?
    ↓
Reopen + Merge
    ✓
```

## Performance Metrics
- **Gateway Latency**: ~500ms (event routing)
- **Risk Analysis**: ~3-5s (Gemini API call)
- **Auto-Merge**: ~2s (GitHub API)
- **End-to-End**: ~8s (Push → Merge for low risk)

---

**Status**: ✅ Production Ready | **Version**: 2.0 | **Last Updated**: 2026-01-17
