"""
Ultra-lightweight PR Agent Brain using Direct Gemini REST API.
No compiled dependencies - pure Python for maximum Lambda compatibility.
"""
import json
import boto3
import os
import re
import base64
import urllib.request
from datetime import datetime

# Constants
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

# Load Knowledge Base
KB_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_BASE = {}

def load_knowledge_base():
    """Loads knowledge base files for risk analysis context."""
    global KNOWLEDGE_BASE
    
    kb_files = {
        'incident_history': 'incident_history.txt',
        'architecture_map': 'architecture_map.txt',
        'deployment_policies': 'deployment_policies.txt'
    }
    
    for key, filename in kb_files.items():
        filepath = os.path.join(KB_DIR, filename)
        try:
            with open(filepath, 'r') as f:
                KNOWLEDGE_BASE[key] = f.read()
            print(f"DEBUG: Loaded KB - {filename}")
        except FileNotFoundError:
            print(f"WARN: KB file not found: {filepath}")
            KNOWLEDGE_BASE[key] = f"# {filename} not available"
    
    return KNOWLEDGE_BASE

# Load KB at module initialization
load_knowledge_base()


def lambda_handler(event, context):
    """Main Lambda handler for Gemini-based PR agent."""
    print(f"DEBUG: Brain received payload -> {json.dumps(event)}")
    
    # Parse Event
    repo_full_name = event.get('repo_full_name')
    try:
        pr_number = str(int(float(event.get('pr_number'))))
    except:
        pr_number = str(event.get('pr_number'))
    
    is_pr = event.get('is_pull_request', False)
    user_msg = event.get('user_message') or event.get('user_comment', 'Evaluate the request.')
    sender_name = event.get('sender_name', 'unknown')
    
    is_automatic_trigger = event.get('is_automatic_trigger', False)
    commit_sha = event.get('commit_sha')

    if is_automatic_trigger and commit_sha:
        set_commit_status(repo_full_name, commit_sha, "pending", "Analyzing Risk (Gemma 3 12B)...")
    
    # Fetch PR Diff
    pr_diff = "No code diff available."
    if is_pr:
        try:
            diff_url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3.diff"
            }
            diff_req = urllib.request.Request(diff_url, headers=headers)
            with urllib.request.urlopen(diff_req) as res:
                pr_diff = res.read().decode('utf-8')
        except Exception as e:
            print(f"DEBUG: Diff fetch skipped: {e}")
    
    # Check for Autopilot (Approval Flow)
    print(f"DEBUG: Checking for approval. user_msg lower = '{user_msg.lower()}'")
    print(f"DEBUG: 'approved' in user_msg.lower() = {'approved' in user_msg.lower()}")
    if "approved" in user_msg.lower():
        print("DEBUG: APPROVAL DETECTED - calling handle_approval")
        return handle_approval(user_msg, repo_full_name, pr_number, sender_name)
    
    elif "rejected" in user_msg.lower():
        return handle_rejection(user_msg, repo_full_name, pr_number, sender_name)
    
    # Smart Bypass for Simple Commands
    bypass_result = try_bypass_commands(user_msg, repo_full_name, pr_number)
    if bypass_result:
        return bypass_result
    
    # Use Gemini for Risk Analysis
    try:
        prompt = build_system_prompt(repo_full_name, pr_number, user_msg, pr_diff)
        analysis = call_groq_api(prompt)
        
        print(f"DEBUG: Gemini Analysis -> {analysis}")
        
        # Extract risk decision
        risk_level = extract_risk_level(analysis)
        
        if risk_level in ['HIGH', 'MEDIUM']:
            return trigger_high_risk_approval_smart(
                user_msg, repo_full_name, pr_number, analysis, risk_level, commit_sha
            )
        else:
            if is_automatic_trigger and commit_sha:
                set_commit_status(repo_full_name, commit_sha, "success", "Low Risk - Safe to Merge")
                # Auto-Merge (Happy Path)
                merge_pull_request(repo_full_name, pr_number)
                post_github_comment(repo_full_name, pr_number, f"{analysis}\n\n✅ **Auto-Merge**: Low Risk. Merging automatically.")
            else: 
                post_github_comment(repo_full_name, pr_number, analysis)
            return {"statusCode": 200, "body": "Low Risk - Executed"}
    
    except Exception as e:
        print(f"ERROR: Gemini API failed -> {e}")
        return handle_fallback(user_msg, repo_full_name, pr_number, str(e), commit_sha)


def call_groq_api(prompt: str) -> str:
    """Call Groq API directly via REST (Llama 3 70B)."""
    # SWITCH: Using Llama 3 70B via Groq
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant for Code Reviews."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 2048
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"GROQ API ERROR: {str(e)}")
        # Fallback to a simple error message if API fails
        return f"Error calling AI Model: {str(e)}"


def build_system_prompt(repo: str, pr_num: str, user_msg: str, diff: str) -> str:
    """Builds the system prompt for Gemini with KB context."""
    kb_context = f"""
KNOWLEDGE BASE CONTEXT (use this for risk analysis):

{KNOWLEDGE_BASE.get('architecture_map', '')}

{KNOWLEDGE_BASE.get('incident_history', '')}

{KNOWLEDGE_BASE.get('deployment_policies', '')}
"""
    
    return f"""You are a PR Risk Analyzer. Analyze the following request and provide a risk assessment.

Context: PULL REQUEST #{pr_num} in {repo}
Existing Code Changes (Diff):
{diff[:5000]}

User Request: {user_msg}

{kb_context}

INSTRUCTIONS:
1. Analyze the request using the KNOWLEDGE BASE above
2. Identify risk level: LOW, MEDIUM, or HIGH
3. Reference specific incidents or policies from the KB
4. Explain your reasoning

RISK CLASSIFICATION RULES:
- Schema changes (especially user_id field) = HIGH RISK (reference Incident #OUTAGE-2024-06)
- Changes affecting Legacy-Scanner-Adapter = HIGH RISK
- Database modifications = HIGH RISK
- Branch operations (create/delete) = LOW/MEDIUM RISK depending on context
- Documentation updates = LOW RISK

Provide your analysis in this format:
RISK LEVEL: [LOW/MEDIUM/HIGH]
REASONING: [Your detailed analysis referencing KB]
RECOMMENDATION: [What should be done]
"""


def update_pr_state(repo_full_name: str, pr_number: str, state: str):
    """Updates the state of a PR (open/closed)."""
    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
    data = {"state": state}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28" 
            },
            method='PATCH'
        )
        with urllib.request.urlopen(req) as res:
            print(f"DEBUG: Updated PR #{pr_number} state to '{state}'")
    except Exception as e:
        print(f"WARN: Failed to update PR state: {e}")

def set_commit_status(repo_full_name: str, sha: str, state: str, description: str, target_url: str = None):
    """Sets the GitHub commit status (pending/success/failure)."""
    if not sha: return
    
    url = f"https://api.github.com/repos/{repo_full_name}/statuses/{sha}"
    data = {
        "state": state,
        "description": description,
        "context": "PR-Agent-Risk-Check"
    }
    if target_url:
        data["target_url"] = target_url
        
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req) as res:
            print(f"DEBUG: Set commit status for {sha} to {state}")
    except Exception as e:
        print(f"WARN: Failed to set commit status: {e}")


def extract_risk_level(analysis: str) -> str:
    """Extract risk level from Gemini's analysis."""
    # FIX: Use \W+ to match any non-word characters (colons, asterisks, spaces) between label and level
    # Handles: "RISK LEVEL: MEDIUM", "**RISK LEVEL:** MEDIUM", "**RISK LEVEL**: MEDIUM"
    match = re.search(r'RISK LEVEL\W+(HIGH|MEDIUM|LOW)', analysis, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # Fallback to older heuristic but stricter
    if "RISK LEVEL: HIGH" in analysis.upper():
        return "HIGH"
    elif "RISK LEVEL: MEDIUM" in analysis.upper():
        return "MEDIUM"
    else:
        return "LOW"


def trigger_high_risk_approval_smart(user_msg: str, repo: str, pr_num: str, analysis: str, risk_level: str, commit_sha: str = None):
    """Triggers approval flow for high-risk operations with AI analysis."""
    
    # Risk Analysis: Block Merge
    if commit_sha:
        set_commit_status(repo, commit_sha, "failure", "High Risk - Approval Required")
        
        # Auto-Close Enforcer (Free Plan Guard)
        # If High/Medium Risk, CLOSE the PR to prevent merging
        print(f"DEBUG: Closing PR #{pr_num} due to High Risk")
        update_pr_state(repo, pr_num, "closed")


    writer = boto3.client('lambda')
    ticket_id = f"SCRUM-{int(datetime.now().timestamp()) % 1000}"
    
    try:
        jira_res = writer.invoke(
            FunctionName='PR-Agent-GitHub-Writer',
            InvocationType='RequestResponse',
            Payload=json.dumps({
                "actionGroup": "ManualReply", 
                "function": "manage_jira_governance",
                "repo_full_name": repo,
                "parameters": {
                    "pr_number": pr_num,
                    "risk_level": risk_level,
                    "service_name": repo,
                    "approval_comment": f"AI RISK ANALYSIS:\n{analysis}"
                }
            })
        )
        jira_out = json.loads(jira_res['Payload'].read().decode('utf-8'))
        jira_text = jira_out.get('response', {}).get('functionResponse', {}).get('responseBody', {}).get('TEXT', {}).get('body', '')
        
        match = re.search(r'(SCRUM-\d+)', jira_text)
        if match:
            ticket_id = match.group(1)
    except Exception as e:
        print(f"WARN: Jira ticket creation failed: {e}")
    
    # Send Approval Email
    action_name = "ai_analyzed_action"
    params_json = base64.urlsafe_b64encode(json.dumps({
        "request": user_msg,
        "jira_ticket_id": ticket_id,
        "repo_full_name": repo,
        "pr_number": pr_num,
        "commit_sha": commit_sha
    }).encode()).decode()
    
    writer.invoke(
        FunctionName='PR-Agent-GitHub-Writer',
        InvocationType='Event',
        Payload=json.dumps({
            "actionGroup": "ManualReply", 
            "function": "send_approval_email",
            "repo_full_name": repo,
            "parameters": {
                "pr_number": pr_num,
                "risk_level": risk_level,
                "service_name": repo,
                "details": f"{analysis}\n\n[ACTION: {action_name}]\n[PARAMS: {params_json}]"
            }
        })
    )
    
    # Post Risk Report
    # We embed the PARAMS using Markdown Link Reference syntax (invisible in rendered view, visible in raw)
    risk_report = f"""**🤖 AI Risk Analysis (Powered by Llama 3 70B)**

**Jira Ticket:** {ticket_id}

{analysis}

⏸️ **Paused:** Waiting for approval via email.
 
<!-- params: {params_json} -->
"""
    post_github_comment(repo, pr_num, risk_report)
    
    return {"statusCode": 200, "body": "High Risk Approval Flow Triggered"}

def merge_pull_request(repo_full_name: str, pr_number: str, merge_method: str = "merge"):
    """Merges a PR automatically."""
    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/merge"
    data = {"merge_method": merge_method}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28" 
            },
            method='PUT'
        )
        with urllib.request.urlopen(req) as res:
            print(f"DEBUG: Merged PR #{pr_number} automatically.")
            return True
    except Exception as e:
        print(f"WARN: Failed to merge PR: {e}")
        return False


def handle_rejection(user_msg: str, repo: str, pr_num: str, sender_name: str = "unknown"):
    """Handles rejection workflow: updates Jira and GitHub."""
    print("DEBUG: Rejection detected.")
    
    params_dict = {}
    ticket_id = None
    
    # 1. Try to find params in current message (unlikely for manual rejection)
    params_match = re.search(r'Params:\s*([a-zA-Z0-9\-_=]+)', user_msg)
    if params_match:
        try:
            decoded_json = base64.urlsafe_b64decode(params_match.group(1)).decode('utf-8')
            params_dict = json.loads(decoded_json)
            ticket_id = params_dict.get('jira_ticket_id')
        except Exception as e:
            print(f"WARN: Failed to decode params: {e}")

    # 2. If not found, fetch from previous bot comments (Context Recovery)
    if not ticket_id:
        print("DEBUG: No context in rejection message. Searching history...")
        try:
            url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments?sort=created&direction=desc"
            req = urllib.request.Request(url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
            with urllib.request.urlopen(req) as res:
                comments = json.loads(res.read().decode('utf-8'))
                for comment in comments:
                    body = comment.get('body', '')
                    if "AI Risk Analysis" in body or "Fallback Mode" in body:
                        # FIX: Handle markdown (**Jira Ticket:**) using \W+
                        jira_match = re.search(r'Jira Ticket\W+([A-Z]+-\d+)', body)
                        if jira_match:
                            ticket_id = jira_match.group(1)
                            print(f"DEBUG: Recovered Jira ticket from history: {ticket_id}")
                            break
        except Exception as e:
            print(f"WARN: Failed to fetch history for rejection: {e}")

    writer = boto3.client('lambda')
    
    if ticket_id:
        # Update Jira
        writer.invoke(
            FunctionName='PR-Agent-GitHub-Writer',
            InvocationType='Event',
            Payload=json.dumps({
                "actionGroup": "ManualReply", 
                "function": "manage_jira_governance",
                "repo_full_name": repo,
                "parameters": {
                    "ticket_id": ticket_id, 
                    "comment_text": f"❌ **Rejected by {sender_name}:** User denied the request.", 
                    "pr_number": pr_num
                }
            })
        )
        print(f"DEBUG: Updated Jira ticket {ticket_id} with rejection.")
    
    # Post to GitHub
    post_github_comment(repo, pr_num, f"❌ **Request Rejected**\n\nThe operation has been cancelled by {sender_name}.\n\n**Jira Updated:** {ticket_id if ticket_id else 'N/A'}")
    
    return {"statusCode": 200, "body": "Rejection Handled"}



def handle_approval(user_msg: str, repo: str, pr_num: str, sender_name: str = "unknown"):
    """Handles approval workflow and EXECUTES the action (STATELESS)."""
    
    print("DEBUG: Approval detected. Using STATELESS re-analysis approach.")
    
    # STATELESS APPROACH: Re-fetch PR diff and analyze what needs to be done
    try:
            # Try to get branch name from PR, but if that fails, try to find test branches
            branch_name = None
            pr_title = ""
            pr_body = ""
            try:
                pr_url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
                req = urllib.request.Request(pr_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
                with urllib.request.urlopen(req) as res:
                    pr_data = json.loads(res.read().decode('utf-8'))
                    branch_name = pr_data['head']['ref']
                    pr_title = pr_data.get('title', '')
                    pr_body = pr_data.get('body', '')
                    print(f"DEBUG: Got branch from PR: {branch_name}")
            except Exception as e:
                print(f"WARN: Could not fetch PR: {e}")
                # Try common branch patterns (test-v19, test-v18, etc.)
                for test_branch in [f"test-v{i}" for i in range(1, 20)][::-1]:
                    test_url = f"https://api.github.com/repos/{repo}/branches/{test_branch}"
                    try:
                        req = urllib.request.Request(test_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
                        urllib.request.urlopen(req)
                        branch_name = test_branch
                        print(f"DEBUG: Found test branch: {branch_name}")
                        break
                    except:
                        continue
            
            # If we couldn't find an existing branch, create a new one
            if not branch_name:
                # Create a new test branch
                import time
                branch_name = f"approved-change-{int(time.time()) % 10000}"
                print(f"DEBUG: No existing branch found. Creating new branch: {branch_name}")
                
                writer = boto3.client('lambda')
                try:
                    writer.invoke(
                        FunctionName='PR-Agent-GitHub-Writer',
                        InvocationType='RequestResponse',  # Synchronous
                        Payload=json.dumps({
                            "actionGroup": "GitHubManagement",
                            "function": "create_branch",
                            "repo_full_name": repo,
                            "parameters": {
                                "branch_name": branch_name,
                                "base_branch": "main"
                            }
                        })
                    )
                    print(f"DEBUG: Created branch {branch_name}")
                except Exception as e:
                    post_github_comment(repo, pr_num, f"⚠️ **Approval Failed**: Could not create branch `{branch_name}`\n\nError: {str(e)}")
                    return {"statusCode": 200, "body": f"Branch creation failed: {e}"}
            
            # Step 2: Look for bot comments to find Jira ticket AND context
            print(f"DEBUG: Fetching comments for PR #{pr_num}")
            comments_url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments?sort=created&direction=desc"
            req = urllib.request.Request(comments_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
            jira_ticket = "UNKNOWN"
            recovered_request = None
            commit_sha_recovered = None
            
            try:
                with urllib.request.urlopen(req) as res:
                    comments = json.loads(res.read().decode('utf-8'))
                    # reverse to find most recent first
                    for comment in comments:
                        body = comment.get('body', '')
                        # FIX: Check for both standard analysis AND fallback mode comments
                        if "AI Risk Analysis" in body or "Fallback Mode" in body:
                            # 2a. Find Jira Ticket
                            if jira_ticket == "UNKNOWN":
                                # FIX: Handle markdown (**Jira Ticket:**) using \W+
                                jira_match = re.search(r'Jira Ticket\W+([A-Z]+-\d+)', body)
                                if jira_match:
                                    jira_ticket = jira_match.group(1)
                                    print(f"DEBUG: Found Jira ticket: {jira_ticket}")
                            
                            # 2b. Find Hidden Context (Params) - Try both formats
                            params_match = re.search(r'<!-- params:\s*([a-zA-Z0-9\-_=]+)\s*-->', body)
                            if not params_match:
                                # Try legacy [params] format
                                params_match = re.search(r'\[params\]:\s*([a-zA-Z0-9\-_=]+)', body)
                                
                            if params_match:
                                try:
                                    decoded = base64.urlsafe_b64decode(params_match.group(1)).decode('utf-8')
                                    json_params = json.loads(decoded)
                                    recovered_request = json_params.get('request')
                                    commit_sha_recovered = json_params.get('commit_sha')
                                    print(f"DEBUG: Recovered original request from history: {recovered_request}")
                                except Exception as e:
                                    print(f"WARN: Failed to decode params from history: {e}")
                            
                            if jira_ticket != "UNKNOWN" and recovered_request:
                                break
            except Exception as e:
                print(f"WARN: Failed to fetch comments: {e}")
            
            # Step 3: Parse intent
            # Priority: Context in user msg > Recovered from history > PR title > PR body
            request_text = pr_title # Default
            
            if "Context:" in user_msg:
                 context_match = re.search(r'Context:\s*(.+)', user_msg, re.IGNORECASE)
                 if context_match: 
                     request_text = context_match.group(1).strip()
            elif recovered_request:
                request_text = recovered_request
            
            print(f"DEBUG: Final Request Context: {request_text}")

            if commit_sha_recovered:
                set_commit_status(repo, commit_sha_recovered, "success", f"Approved by {sender_name}")

            # Risk Analysis "Unblock Only" Flow
            if "Automatic Risk Analysis Trigger" in request_text:
                print("DEBUG: Risk Analysis Unblock detected. No file changes needed.")
                
                # Update Jira
                if jira_ticket and jira_ticket != "UNKNOWN":
                    writer = boto3.client('lambda')
                    try:
                        print(f"DEBUG: Invoking manage_jira_governance for Ticket {jira_ticket}")
                        resp = writer.invoke(
                            FunctionName='PR-Agent-GitHub-Writer',
                            InvocationType='RequestResponse', # Changed to Sync to see error
                            Payload=json.dumps({
                                "actionGroup": "ManualReply", 
                                "function": "manage_jira_governance",
                                "repo_full_name": repo,
                                "parameters": {
                                    "ticket_id": jira_ticket, 
                                    "comment_text": f"✅ **Approved by {sender_name}:** Risk accepted. PR unblocked.", 
                                    "pr_number": pr_num
                                }
                            })
                        )
                        payload = json.loads(resp['Payload'].read().decode('utf-8'))
                        print(f"DEBUG: Jira Update Response: {payload}")
                    except Exception as e:
                        print(f"ERROR: Failed to update Jira: {e}")

                # CRITICAL ORDER FIX: Post "Risk Accepted" comment BEFORE Re-opening
                # This ensures Gateway finds this comment when it processes the 'reopened' event
                post_github_comment(repo, pr_num, f"✅ **Risk Accepted**\n\nPR has been unblocked by {sender_name} (Re-opened).\n\n**Jira Updated:** {jira_ticket}")

                # Auto-Close: Re-open PR
                print(f"DEBUG: Re-opening PR #{pr_num} after approval")
                update_pr_state(repo, pr_num, "open")
                
                # Auto-Merge (Happy Path)
                merged = merge_pull_request(repo, pr_num)
                merge_msg = "Merged Automatically 🚀" if merged else "Ready to Merge (Manual Merge Required)"
                
                # Post final status
                post_github_comment(repo, pr_num, f"**Status:** {merge_msg}")
                return {"statusCode": 200, "body": "Risk Analysis Unblocked"}


            # FIX: If we have context, try to extract specific branch name from it
            # User might have said "create branch X and update Y"
            # If we just use PR head ref, we might edit the wrong branch (e.g. migration-test vs X)
            context_branch_match = re.search(r'(?:create|on|to)\s+(?:a\s+)?(?:branch\s+)?([a-zA-Z0-9\-_]+)', request_text, re.IGNORECASE)
            if context_branch_match:
                extracted_branch = context_branch_match.group(1)
                # Filter out keywords like "and", "update", "change"
                if extracted_branch.lower() not in ['and', 'update', 'change', 'services', 'file']:
                    print(f"DEBUG: Overriding branch name from context: {extracted_branch}")
                    branch_name = extracted_branch
            
            execution_log = "Action logged."
            writer = boto3.client('lambda')
            
            # Step 4: Detect file update request
            # FIX: Allow any file extension (2-5 chars), not just .py
            file_match = re.search(r'([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]{2,5})', request_text, re.IGNORECASE)
            if not file_match:
                # Try to find "update X" pattern
                file_match = re.search(r'update\s+([a-zA-Z0-9_\-\./]+)', request_text, re.IGNORECASE)
            
            if file_match:
                target_file = file_match.group(1)
                print(f"DEBUG: Detected file update request for: {target_file}")
                
                try:
                    # Step 5: GET current content from the branch
                    file_url = f"https://api.github.com/repos/{repo}/contents/{target_file}?ref={branch_name}"
                    print(f"DEBUG: Fetching file: {file_url}")
                    req = urllib.request.Request(file_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
                    
                    with urllib.request.urlopen(req) as f:
                        file_data = json.loads(f.read().decode('utf-8'))
                        current_content = base64.b64decode(file_data['content']).decode('utf-8')
                        print(f"DEBUG: File fetched successfully. Length: {len(current_content)}")
                    
                    # Step 6: ASK GEMINI for the new code
                    transform_prompt = f"""You are a Code Editor.
User's Request: {request_text}
File: {target_file}
Current Content:
{current_content}

Apply the requested changes and output ONLY the full new content of the file. No markdown blocks, no explanations."""
                    
                    print("DEBUG: Calling Gemini for code transformation...")
                    new_content = call_groq_api(transform_prompt).strip()
                    # Clean up markdown if Gemini added it
                    new_content = re.sub(r'^```\w*\n', '', new_content)
                    new_content = re.sub(r'\n```$', '', new_content)
                    print(f"DEBUG: Gemini returned {len(new_content)} characters")
                    
                    # Step 7: APPLY the change
                    print(f"DEBUG: Applying changes to {target_file} on branch {branch_name}")
                    print(f"DEBUG: Invoking Writer Lambda with update_file...")
                    
                    update_response = writer.invoke(
                        FunctionName='PR-Agent-GitHub-Writer',
                        InvocationType='RequestResponse',  # Changed to synchronous to get immediate response
                        Payload=json.dumps({
                            "actionGroup": "GitHubManagement", 
                            "function": "update_file",
                            "repo_full_name": repo,
                            "parameters": {
                                "file_path": target_file,
                                "branch_name": branch_name,
                                "new_content": new_content
                            }
                        })
                    )
                    
                    # Check response
                    response_payload = json.loads(update_response['Payload'].read().decode('utf-8'))
                    print(f"DEBUG: Writer response: {response_payload}")
                    
                    execution_log = f"✅ Executed update on `{target_file}` on branch `{branch_name}` based on approval."
                    post_github_comment(repo, pr_num, f"✅ **Approved & Executed (Direct Mode)**\n\nRequest: {request_text}\n\nUpdated `{target_file}` on branch `{branch_name}`\n\n**Approved By:** {sender_name}\n\nWriter Response: {response_payload.get('body', 'Success')}")
                    return {"statusCode": 200, "body": "Direct execution complete"}
                    
                except urllib.error.HTTPError as e:
                    error_msg = f"File fetch failed: {e.code} {e.reason}"
                    if e.code == 404:
                        error_msg = f"File `{target_file}` not found on branch `{branch_name}`"
                    execution_log = f"⚠️ Execution failed: {error_msg}"
                    print(f"ERROR: {error_msg}")
                except Exception as e:
                    execution_log = f"⚠️ Execution failed: {str(e)}"
                    print(f"ERROR: {e}")
            else:
                execution_log = "⚠️ Could not detect file to update from request"
                print(f"WARN: No file pattern found in: {request_text}")

            # Step 8: Update Jira
            if jira_ticket and jira_ticket != 'UNKNOWN':
                try:
                    print(f"DEBUG: Invoking manage_jira_governance for Rejection {jira_ticket}")
                    resp = writer.invoke(
                        FunctionName='PR-Agent-GitHub-Writer',
                        InvocationType='RequestResponse', # Sync for debugging
                        Payload=json.dumps({
                            "actionGroup": "ManualReply", 
                            "function": "manage_jira_governance",
                            "repo_full_name": repo,
                            "parameters": {
                                "ticket_id": jira_ticket, 
                                "comment_text": f"❌ **Rejected by {sender_name}:** Request denied by user.", 
                                "pr_number": pr_num
                            }
                        })
                    )
                    payload = json.loads(resp['Payload'].read().decode('utf-8'))
                    print(f"DEBUG: Jira Rejection Update Response: {payload}")
                except Exception as e:
                     print(f"ERROR: Failed to update Jira rejection: {e}")
            
            # Step 9: Post result
            post_github_comment(repo, pr_num, f"✅ **Approved Action Executed**\n\nRequest: {request_text}\n\n**Status:** {execution_log}\n**Approved By:** {sender_name}\n**Jira Updated:** {jira_ticket}")
        
    except Exception as e:
        error_msg = f"Unexpected error in approval handler: {str(e)}"
        print(f"ERROR: {error_msg}")
        post_github_comment(repo, pr_num, f"⚠️ **Approval Failed**: {error_msg}")
    
    return {"statusCode": 200, "body": "Autopilot Execution Complete"}
    
    post_github_comment(repo, pr_num, f"✅ **Approved Action Executed**\n\nRequest: {params_dict.get('request', 'N/A')}\n\n**Approved By:** {sender_name}\n**Jira Updated:** {ticket_id}")
    
    return {"statusCode": 200, "body": "Autopilot Execution Complete"}


def try_bypass_commands(user_msg: str, repo: str, pr_num: str):
    """Fast path for simple commands."""
    
    # Check for bulk delete command: "delete all branches except main"
    if re.search(r'delete\s+all\s+branches?.*except\s+main', user_msg, re.IGNORECASE):
        print("DEBUG: Bulk branch deletion detected")
        writer = boto3.client('lambda')
        
        # Fetch all branches
        try:
            url = f"https://api.github.com/repos/{repo}/branches"
            req = urllib.request.Request(url, headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            })
            with urllib.request.urlopen(req) as res:
                branches = json.loads(res.read().decode('utf-8'))
                
            # Filter out 'main' and delete the rest
            branches_to_delete = [b['name'] for b in branches if b['name'] != 'main']
            
            if not branches_to_delete:
                post_github_comment(repo, pr_num, f"ℹ️ **No branches to delete**\n\nOnly `main` branch exists.")
                return {"statusCode": 200, "body": "No branches to delete"}
            
            # Delete each branch
            deleted_count = 0
            for branch_name in branches_to_delete:
                try:
                    writer.invoke(
                        FunctionName='PR-Agent-GitHub-Writer',
                        InvocationType='Event',
                        Payload=json.dumps({
                            "actionGroup": "GitHubManagement",
                            "function": "delete_branch",
                            "repo_full_name": repo,
                            "parameters": {"branch_name": branch_name}
                        })
                    )
                    deleted_count += 1
                except Exception as e:
                    print(f"WARN: Failed to delete {branch_name}: {e}")
            
            branch_list = '\n'.join([f"- `{b}`" for b in branches_to_delete])
            post_github_comment(repo, pr_num, f"✅ **Bulk Deletion Complete**\n\nDeleted {deleted_count} branches:\n{branch_list}\n\n`main` branch preserved.")
            return {"statusCode": 200, "body": f"Deleted {deleted_count} branches"}
            
        except Exception as e:
            post_github_comment(repo, pr_num, f"⚠️ **Bulk deletion failed**: {str(e)}")
            return {"statusCode": 200, "body": f"Failed: {e}"}
    
    # Original single-operation logic
    intent_match = re.search(
        r'(create|delete|merge)\b.*?\b(branch|file|pr|pull request)\b(?:\s+(?:named|called|for))?\s+([a-zA-Z0-9\-_/\.]+)', 
        user_msg, 
        re.IGNORECASE
    )
    
    if not intent_match or "approved" in user_msg.lower():
        return None
        
    # Prevent bypass if this is a compound command (contains code change keywords)
    # This allows the Gateway's Priority 0 flow to work: Gateway creates branch -> Brain analyzes code
    # FIX: Use word boundaries to prevent false positives from branch names like "branchfix-1"
    code_change_keywords = ["update", "modify", "change", "fix", "edit", "rewrite", "replace"]
    for keyword in code_change_keywords:
        # FIX: Use word boundaries AND require following space/end of string to avoid matching "fix-1"
        if re.search(rf'\b{keyword}(?:\s|$)', user_msg, re.IGNORECASE):
            print(f"DEBUG: Code change keyword '{keyword}' detected in '{user_msg}'. Skipping bypass to allow AI analysis.")
            return None
    
    action_verb = intent_match.group(1).lower()
    resource_type = intent_match.group(2).lower() if intent_match.group(2) else "unknown"
    target_name = intent_match.group(3) if intent_match.group(3) else "demo-target"
    
    writer = boto3.client('lambda')
    
    if "create" in action_verb and "branch" in resource_type:
        print("DEBUG: Low Risk Fast-Path (Create Branch)")
        writer.invoke(
            FunctionName='PR-Agent-GitHub-Writer',
            InvocationType='Event',
            Payload=json.dumps({
                "actionGroup": "GitHubManagement", 
                "function": "create_branch",
                "repo_full_name": repo,
                "parameters": {"branch_name": target_name, "base_branch": "main"}
            })
        )
        post_github_comment(repo, pr_num, f"✅ **Low Risk Action:** Branch `{target_name}` created successfully.\nNo risk analysis required.")
        return {"statusCode": 200, "body": "Low Risk Success"}
    
    return None


def handle_fallback(user_msg: str, repo: str, pr_num: str, error: str, commit_sha: str = None):
    """Fallback when Gemini fails."""
    print(f"DEBUG: Fallback Mode - {error}")
    
    fallback_analysis = f"""RISK LEVEL: MEDIUM
REASONING: Unable to perform AI analysis due to technical error. Defaulting to cautious approach.
RECOMMENDATION: Please review manually."""
    
    # FIX: Trigger approval flow for fallback (MEDIUM risk)
    return trigger_high_risk_approval_smart(
        user_msg, repo, pr_num, fallback_analysis, "MEDIUM", commit_sha
    )



def fetch_previous_bot_comment(repo: str, pr_num: str) -> str:
    """Fetches key context from the most recent AI risk analysis comment."""
    print(f"DEBUG: Fetching history for {repo} PR #{pr_num}")
    try:
        url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        })
        
        with urllib.request.urlopen(req) as res:
            comments = json.loads(res.read().decode('utf-8'))
            
            # Sort by created_at desc
            comments.sort(key=lambda x: x['created_at'], reverse=True)
            
            for comment in comments:
                body = comment.get('body', '')
                if "AI Risk Analysis" in body:
                    print("DEBUG: Found previous Risk Analysis comment (candidates).")
                    # We return the first one (most recent) that looks like it has data, or just the most recent one
                    return body
                    
        print("DEBUG: No suitable history found.")
        return ""
    except Exception as e:
        print(f"WARN: Failed to fetch history: {e}")
        return ""


def post_github_comment(repo: str, pr_num: str, text: str):
    """Posts a comment to GitHub PR."""
    writer = boto3.client('lambda')
    writer.invoke(
        FunctionName='PR-Agent-GitHub-Writer',
        InvocationType='Event',
        Payload=json.dumps({
            "actionGroup": "ManualReply", 
            "function": "post_comment",
            "repo_full_name": repo,
            "parameters": {
                "repo_full_name": repo,
                "pr_number": pr_num,
                "comment_text": text
            }
        })
    )
