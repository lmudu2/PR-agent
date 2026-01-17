import boto3
import os
import urllib.request
import urllib.error
import json # Added import for json

# Helper functions for Auto-PR Logic
def check_pr_exists(repo_full_name, branch_name):
    """
    Checks if a pull request already exists for the given branch.
    """
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("ERROR: GITHUB_TOKEN environment variable not set.")
        return False

    url = f"https://api.github.com/repos/{repo_full_name}/pulls?head={branch_name}&state=open"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            pulls = json.loads(response.read().decode())
            # Filter if needed, but head=branch_name usually returns specific PRs
            return len(pulls) > 0
    except urllib.error.HTTPError as e:
        print(f"HTTP Error checking PR existence: {e.code} - {e.reason}")
        return False
    except Exception as e:
        print(f"Error checking PR existence: {e}")
        return False

def create_pull_request(repo_full_name, branch_name):
    """
    Creates a pull request for the given branch against the default branch (main/master).
    """
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("ERROR: GITHUB_TOKEN environment variable not set.")
        return

    # Determine default branch (main or master)
    default_branch = "main" # Assume main first
    try:
        repo_info_url = f"https://api.github.com/repos/{repo_full_name}"
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        req = urllib.request.Request(repo_info_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            repo_data = json.loads(response.read().decode())
            default_branch = repo_data.get('default_branch', 'main')
    except Exception as e:
        print(f"Warning: Could not determine default branch, assuming '{default_branch}'. Error: {e}")


    url = f"https://api.github.com/repos/{repo_full_name}/pulls"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    data = {
        "title": f"Auto-PR: Changes from {branch_name}",
        "head": branch_name,
        "base": default_branch,
        "body": f"This is an automatically generated pull request for branch `{branch_name}`."
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            pr_data = json.loads(response.read().decode())
            print(f"Successfully created PR: {pr_data.get('html_url')}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error creating PR: {e.code} - {e.reason}")
        print(f"Response body: {e.read().decode()}")
    except Exception as e:
        print(f"Error creating PR: {e}")


def lambda_handler(event, context):
    print(f"FULL EVENT: {json.dumps(event)}")
    try:
        body = json.loads(event.get('body', '{}'))
        if 'repository' not in body: return {'statusCode': 200}
        
        repo_name = body.get('repository', {}).get('full_name')
        comment_obj = body.get('comment', {})
        user_text = comment_obj.get('body', '').lower()
        sender_name = comment_obj.get('user', {}).get('login', 'unknown')
        item_number = body.get('issue', {}).get('number') or body.get('pull_request', {}).get('number')

        # Auto-PR Logic: Trigger on Push to new branch
        if 'ref' in body and 'after' in body and 'pull_request' not in body:
            ref = body.get('ref') # refs/heads/branch-name
            if ref and ref.startswith('refs/heads/') and not ref.endswith('/main') and not ref.endswith('/master'):
                branch_name = ref.replace('refs/heads/', '')
                print(f"DEBUG: Push detected on branch '{branch_name}'")
                
                # Check if PR exists
                if not check_pr_exists(repo_name, branch_name):
                    print(f"DEBUG: No PR found for '{branch_name}'. Creating Auto-PR...")
                    create_pull_request(repo_name, branch_name)
                    # Note: We don't trigger brain here. GitHub will send 'pull_request' 'opened' event next.
                else:
                    print(f"DEBUG: PR already exists for '{branch_name}'. Skipping.")
            return {'statusCode': 200, 'body': 'Push Processed'}

        # Gatekeeper Logic: Automatic Trigger on PR Open/Sync
        if 'pull_request' in body and body.get('action') in ['opened', 'synchronize', 'reopened']:
            print(f"DEBUG: Automatic Trigger detected (Action: {body.get('action')})")
            
            pr_data = body.get('pull_request', {})
            pr_number = pr_data.get('number')
            head_sha = pr_data.get('head', {}).get('sha')
            print(f"DEBUG: Automatic Risk Analysis Triggered for PR #{pr_number}")
            
            # Post "Thinking" Comment
            post_thinking_status(repo_name, pr_number, "⏳ **Risk Analysis: Analyzing...**")
            trigger_brain({
                "repo_full_name": repo_name,
                "pr_number": str(pr_number),
                "user_message": "Context: Automatic Risk Analysis Trigger (Strict Analysis)",
                "sender_name": sender_name,
                "is_pull_request": True,
                "is_automatic_trigger": True,
                "commit_sha": head_sha
            })
            return {'statusCode': 200, 'body': 'Auto-Analysis Triggered'}

        if "@pr-agent" in user_text:
            # SMART ROUTING: Separate safe operations from risky code changes
            # Safe operations go through fast path (no Bedrock needed)
            # Code changes always go through AI risk analysis
            
            # Check what type of command this is - require explicit keywords for clarity
            has_delete = ("delete" in user_text or "remove" in user_text) and ("branch" in user_text or "branches" in user_text)
            has_create = "create" in user_text and ("branch" in user_text or "named" in user_text)
            has_list = ("list" in user_text or "show" in user_text) and "branch" in user_text
            
            # Code change keywords that MUST use AI
            code_change_keywords = ["update", "modify", "change", "fix", "edit", "rewrite", "replace"]
            
            # FIX: Use word boundaries AND require following space/end of string to avoid matching "fix-1"
            import re
            has_code_change = False
            for keyword in code_change_keywords:
                # Match keyword as whole word, usually followed by space (verb)
                # FIX: Strictly match whole words. \b matches '-' boundaries, so we use whitespace check
                # (?:^|\s){keyword}(?:\s|$) -> Keyword preceded by start/space AND followed by space/end
                if re.search(rf'(?:^|\s){keyword}(?:\s|$)', user_text):
                    has_code_change = True
                    break


            # PRIORITY 0: COMPOUND COMMAND (Create Branch AND Code Change)
            # Example: "create a test-v1 branch and update services/notification_engine.py..."
            # Logic: Create branch immediately -> Then trigger AI for analysis
            # CRITICAL FIX: Only trigger if BOTH create AND code_change keywords exist
            is_compound_command = has_create and has_code_change
            
            if is_compound_command:
                # 1. Extract Branch Name
                branch_name = "ai-branch-compound"
                
                # Robust extraction (same as Fast Path)
                match = re.search(r'create(?:\s+a)?(?:\s+branch)?(?:\s+named)?\s+([a-zA-Z0-9\-_]+)', user_text, re.IGNORECASE)
                if match:
                    extracted = match.group(1)
                    if extracted.lower() == 'branch':
                         suffix_match = re.search(r'create\s+([a-zA-Z0-9\-_]+)\s+branch', user_text, re.IGNORECASE)
                         if suffix_match:
                             branch_name = suffix_match.group(1)
                    else:
                        branch_name = extracted

                
                # Sanitize
                branch_name = "".join(char for char in branch_name if char.isalnum() or char in "-_")
                print(f"DEBUG: Compound Command - Creating branch '{branch_name}' first")
                
                # 2. Trigger Writer to Create Branch (Fast Path)
                trigger_writer_direct_branch(repo_name, item_number, branch_name)
                
                # 3. Trigger Brain for Risk Analysis (Governed Path)
                post_thinking_status(repo_name, item_number, f"⏳ **Analyzing code changes with Gemini 2.0...**")
                trigger_brain({
                    "repo_full_name": repo_name,
                    "pr_number": str(item_number),
                    "user_comment": user_text,
                    "sender_name": sender_name,
                    "is_pull_request": True
                })
                return {'statusCode': 200}  # Early return after compound command

            # PRIORITY 1: CODE CHANGES (Governed Path - Always use AI)
            elif has_code_change:
                post_thinking_status(repo_name, item_number, "⏳ **Analyzing Risk with Gemini 2.0...**")
                trigger_brain({
                    "repo_full_name": repo_name,
                    "pr_number": str(item_number),
                    "user_comment": user_text,
                    "sender_name": sender_name,
                    "is_pull_request": True
                })
                return {'statusCode': 200}  # Early return after AI analysis

            # PRIORITY 2a: BULK DELETE (delete all except ...)
            elif "delete" in user_text and "all" in user_text and ("branch" in user_text or "branches" in user_text):
                # Extract exceptions
                keep_branches = ["main", "master"] # Always keep main
                if "except" in user_text:
                    try:
                        except_part = user_text.split("except")[1]
                        # split by comma or space
                        extras = [b.strip() for b in except_part.replace(',', ' ').split() if b.strip()]
                        keep_branches.extend(extras)
                    except:
                        pass
                
                print(f"DEBUG: Bulk Delete triggered. Keeping: {keep_branches}")
                
                # Trigger Writer for Bulk Delete
                client = boto3.client('lambda')
                client.invoke(
                    FunctionName='PR-Agent-GitHub-Writer',
                    InvocationType='Event',
                    Payload=json.dumps({
                        "function": "delete_all_branches",
                        "repo_full_name": repo_name,
                        "parameters": {
                            "keep_branches": keep_branches,
                            "pr_number": str(item_number)
                        }
                    })
                )
                return {'statusCode': 200}  # Early return after bulk delete

            # PRIORITY 2b: FAST PATH - Delete Specific Branches  
            elif has_delete:
                branches_to_delete = extract_branch_names(user_text)
                print(f"DEBUG: Fast Path DELETE triggered for branches: {branches_to_delete}")
                trigger_writer_delete_branches(repo_name, item_number, branches_to_delete)
                return {'statusCode': 200}  # Early return after delete

            # PRIORITY 3: FAST PATH - Create Branch (Simple, no code changes)
            elif has_create:
                branch_name = f"ai-branch-{item_number}"  # Default
                
                # Improved Parsing using Regex
                import re
                # Matches: create [a] [branch] [named] <name>
                # Handles: "create fix-1", "create branch fix-1", "create fix-1 branch"
                # Excludes the word "branch" from capture if it's used as a keyword
                match = re.search(r'create(?:\s+a)?(?:\s+branch)?(?:\s+named)?\s+([a-zA-Z0-9\-_]+)', user_text, re.IGNORECASE)
                
                if match:
                    extracted = match.group(1)
                    # If we accidentally captured "branch" (e.g. from "create branch"), try to find name before "branch"
                    if extracted.lower() == 'branch':
                         # Try pattern "create <name> branch"
                         suffix_match = re.search(r'create\s+([a-zA-Z0-9\-_]+)\s+branch', user_text, re.IGNORECASE)
                         if suffix_match:
                             branch_name = suffix_match.group(1)
                    else:
                        branch_name = extracted
                
                branch_name = "".join(char for char in branch_name if char.isalnum() or char in "-_")
                print(f"DEBUG: Fast Path CREATE triggered for branch: {branch_name}")
                trigger_writer_direct_branch(repo_name, item_number, branch_name)
                return {'statusCode': 200}  # Early return after create

            # PRIORITY 4: FAST PATH - List Branches
            elif has_list:
                print(f"DEBUG: Fast Path LIST triggered")
                trigger_writer_list_branches(repo_name, item_number)
                return {'statusCode': 200}  # Early return after list

            # DEFAULT: Use Brain for anything unclear
            else:
                trigger_brain({
                    "repo_full_name": repo_name,
                    "pr_number": str(item_number),
                    "user_comment": user_text,
                    "sender_name": sender_name,
                    "is_pull_request": True
                })

        return {'statusCode': 200}
    except Exception as e:
        print(f"GATEWAY ERR: {e}")
        return {'statusCode': 200}

def trigger_writer_direct_branch(repo, num, branch):
    client = boto3.client('lambda')
    # Use InvokeType='RequestResponse' for the first one so we can catch errors if needed, 
    # but 'Event' is fine for async flow.
    client.invoke(
        FunctionName='PR-Agent-GitHub-Writer',
        InvocationType='Event',
        Payload=json.dumps({
            "function": "create_branch",
            "repo_full_name": repo,
            "parameters": {"branch_name": branch, "base_branch": "main"}
        })
    )
    client.invoke(
        FunctionName='PR-Agent-GitHub-Writer',
        InvocationType='Event',
        Payload=json.dumps({
            "function": "post_comment",
            "repo_full_name": repo,
            "parameters": {
                "pr_number": str(num),
                "comment_text": f"✅ I've created the branch `{branch}` directly for you."
            }
        })
    )

def trigger_brain(payload):
    client = boto3.client('lambda')
    client.invoke(FunctionName='PR-Agent-Brain-LangGraph', InvocationType='Event', Payload=json.dumps(payload))

def post_thinking_status(repo, num, msg):
    client = boto3.client('lambda')
    client.invoke(
        FunctionName='PR-Agent-GitHub-Writer',
        InvocationType='Event',
        Payload=json.dumps({
            "function": "post_comment",
            "repo_full_name": repo,
            "parameters": {"pr_number": str(num), "comment_text": msg}
        })
    )

def extract_branch_names(text):
    """Extract branch names from delete command"""
    import re
    
    # Remove @pr-agent and command words at word boundaries only
    # FIX: Added 'branch' explicitly to prevent it from being extracted as a branch name
    text = re.sub(r'\b(pr-agent|delete|remove|branch|branches|the)\b', '', text, flags=re.IGNORECASE)
    text = text.replace('@', '').replace(',', ' ')
    
    # Split and filter out empty strings and very short words
    branches = [b.strip() for b in text.split() if b.strip() and len(b.strip()) > 2]
    return branches if branches else ["unknown-branch"]

def trigger_writer_delete_branches(repo, num, branches):
    """Trigger direct deletion of branches via Writer Lambda"""
    client = boto3.client('lambda')
    
    for branch in branches:
        client.invoke(
            FunctionName='PR-Agent-GitHub-Writer',
            InvocationType='Event',
            Payload=json.dumps({
                "function": "delete_branch",
                "repo_full_name": repo,
                "parameters": {"branch_name": branch}
            })
        )
    
    # Post confirmation
    branch_list = ", ".join([f"`{b}`" for b in branches])
    client.invoke(
        FunctionName='PR-Agent-GitHub-Writer',
        InvocationType='Event',
        Payload=json.dumps({
            "function": "post_comment",
            "repo_full_name": repo,
            "parameters": {
                "pr_number": str(num),
                "comment_text": f"✅ Deleted branch(es): {branch_list}"
            }
        })
    )



def check_pr_exists(repo, branch):
    """Check if a PR already exists for the given branch."""
    url = f"https://api.github.com/repos/{repo}/pulls?head={repo.split('/')[0]}:{branch}&state=open"
    try:
        req = urllib.request.Request(
            url, 
            headers={"Authorization": f"token {os.environ.get('GITHUB_TOKEN')}"}
        )
        with urllib.request.urlopen(req) as res:
            prs = json.loads(res.read().decode('utf-8'))
            return len(prs) > 0
    except Exception as e:
        print(f"WARN: Failed to check PR: {e}")
        return False

def create_pull_request(repo, branch):
    """Create a new PR for the branch."""
    url = f"https://api.github.com/repos/{repo}/pulls"
    data = {
        "title": f"Auto-PR: {branch}",
        "body": f"Triggered by push event on branch `{branch}`.\n\n@pr-agent analyze",
        "head": branch,
        "base": "main"
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Authorization": f"token {os.environ.get('GITHUB_TOKEN')}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28"
            },
            method='POST'
        )
        with urllib.request.urlopen(req) as res:
            print(f"DEBUG: Created Auto-PR for {branch}")
            return True
    except Exception as e:
        print(f"WARN: Failed to create PR: {e}")
        return False