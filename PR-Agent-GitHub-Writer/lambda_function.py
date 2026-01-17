import json
import os
import urllib.request
import base64
import urllib.error
import boto3
import re
from botocore.exceptions import ClientError

def send_actual_email(recipient, subject, body):
    ses_client = boto3.client('ses', region_name='us-east-1') 
    SENDER = "lmudu95@gmail.com" 
    try:
        ses_client.send_email(
            Source=SENDER,
            Destination={'ToAddresses': [recipient]},
            Message={'Subject': {'Data': subject}, 'Body': {'Html': {'Data': body}}}
        )
        return True
    except Exception as e:
        print(f"SES ERROR: {str(e)}")
        return False

def lambda_handler(event, context):
    func_name = event.get('function')
    action_group = event.get('actionGroup')
    github_token = os.environ.get('GITHUB_TOKEN')
    
    # 1. ROBUST PARAMETER PARSING
    params = {}
    raw_params = event.get('parameters', {})
    if isinstance(raw_params, list):
        params = {p['name']: p['value'] for p in raw_params}
    else:
        params = raw_params
            
    repo = event.get('repo_full_name') or params.get('repo_full_name')
    if repo: repo = repo.strip().strip('/')
    
    # Extract PR number from event or parameters
    pr_number_from_event = event.get('pr_number') or params.get('pr_number')

    def clean_num(n):
        try: return str(int(float(n)))
        except: return str(n)

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AWS-Lambda-Writer",
        "Content-Type": "application/json"
    }

    response_text = ""
    
    try:
        # --- NEW: GITHUB CREATE BRANCH ---
        if func_name == 'create_branch':
            new_branch = params.get('branch_name')
            base = params.get('base_branch', 'main')
            
            if not new_branch:
                raise Exception("Missing 'branch_name' parameter.")

            # Step A: Get SHA of the base branch
            sha_url = f"https://api.github.com/repos/{repo}/git/refs/heads/{base}"
            sha_req = urllib.request.Request(sha_url, headers=headers)
            with urllib.request.urlopen(sha_req) as res:
                sha = json.loads(res.read())['object']['sha']
            
            # Step B: Create the new reference
            create_url = f"https://api.github.com/repos/{repo}/git/refs"
            payload = json.dumps({
                "ref": f"refs/heads/{new_branch}",
                "sha": sha
            }).encode()
            
            urllib.request.urlopen(urllib.request.Request(create_url, data=payload, headers=headers, method='POST'))
            response_text = f"SUCCESS: Branch '{new_branch}' created."

        # --- NEW: GITHUB DELETE BRANCH ---
        elif func_name == 'delete_branch':
            branch_to_del = params.get('branch_name')
            if not branch_to_del:
                response_text = "ERROR: No branch name provided for deletion."
            else:
                url = f"https://api.github.com/repos/{repo}/git/refs/heads/{branch_to_del}"
                try:
                    # FIXED INDENTATION HERE
                    req = urllib.request.Request(url, headers=headers, method='DELETE')
                    urllib.request.urlopen(req)
                    response_text = f"SUCCESS: Branch '{branch_to_del}' deleted."
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        response_text = f"SUCCESS: Branch '{branch_to_del}' already deleted."
                    else:
                        response_text = f"ERROR: Delete failed with code {e.code}"

        # --- NEW: DELETE ALL BRANCHES ---
        elif func_name == 'delete_all_branches':
            keep = params.get('keep_branches', [])
            # Standardize keep list
            keep_set = {k.lower() for k in keep}
            keep_set.add('main')
            keep_set.add('master')
            
            # 1. List all branches
            list_url = f"https://api.github.com/repos/{repo}/git/refs/heads"
            try:
                with urllib.request.urlopen(urllib.request.Request(list_url, headers=headers)) as res:
                    all_refs = json.loads(res.read())
                    
                    deleted_count = 0
                    deleted_names = []
                    
                    for ref in all_refs:
                        # ref['ref'] is like "refs/heads/feature-1"
                        branch_name = ref['ref'].replace('refs/heads/', '')
                        
                        if branch_name.lower() not in keep_set:
                            # Delete it
                            del_url = f"https://api.github.com/repos/{repo}/git/refs/heads/{branch_name}"
                            try:
                                urllib.request.urlopen(urllib.request.Request(del_url, headers=headers, method='DELETE'))
                                deleted_count += 1
                                deleted_names.append(branch_name)
                            except Exception as e:
                                print(f"Failed to delete {branch_name}: {e}")
                    
                    if deleted_count > 0:
                        names_str = ", ".join(deleted_names[:5]) + ("..." if len(deleted_names) > 5 else "")
                        response_text = f"✅ Bulk Cleanup: Deleted {deleted_count} branches ({names_str}). Kept: {', '.join(keep)}"
                    else:
                        response_text = "✅ Bulk Cleanup: No branches needed deletion."

                    # Post comment about result
                    pr_num = clean_num(params.get('pr_number'))
                    if pr_num and pr_num != 'None':
                         post_url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments"
                         post_data = json.dumps({"body": response_text}).encode()
                         urllib.request.urlopen(urllib.request.Request(post_url, data=post_data, headers=headers, method='POST'))

            except Exception as e:
                response_text = f"ERROR: Failed to list/delete branches: {e}"

        # --- TOOL: POST COMMENT ---
        elif func_name == 'post_comment':
            pr_num = clean_num(params.get('pr_number'))
            url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments"
            data = json.dumps({"body": params.get('comment_text')}).encode()
            urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method='POST'))
            response_text = "SUCCESS: Comment posted."

        # --- TOOL: UPDATE FILE ---
        elif func_name == 'update_file':
            path = params.get('file_path', '').strip('/')
            content = params.get('new_content') or params.get('content', '')
            branch = params.get('branch_name')
            
            sha = None
            try:
                get_url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
                with urllib.request.urlopen(urllib.request.Request(get_url, headers=headers)) as res:
                    sha = json.loads(res.read())['sha']
            except: pass 

            payload = {
                "message": f"AI Update: {path}", 
                "content": base64.b64encode(content.encode()).decode(), 
                "branch": branch
            }
            if sha: payload["sha"] = sha 
            
            put_url = f"https://api.github.com/repos/{repo}/contents/{path}"
            urllib.request.urlopen(urllib.request.Request(put_url, data=json.dumps(payload).encode(), headers=headers, method='PUT'))
            response_text = f"SUCCESS: {path} updated on {branch}."

        # --- TOOL: MERGE PR ---
        elif func_name == 'merge_pull_request':
            pr_num = clean_num(params.get('pr_number'))
            url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/merge"
            data = json.dumps({"merge_method": "squash"}).encode()
            urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method='PUT'))
            response_text = f"SUCCESS: PR #{pr_num} merged."

        # --- TOOL: JIRA TICKET ---
        elif func_name == 'manage_jira_governance':
            jira_email = os.environ.get('JIRA_EMAIL')
            jira_token = os.environ.get('JIRA_TOKEN')
            auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
            
            # Build detailed description
            risk_level = params.get('risk_level', 'UNKNOWN')
            service_name = params.get('service_name', 'System')
            approval_comment = params.get('approval_comment', 'Action needed.')
            action_type = params.get('action_type', '')
            # Use pr_number from event if available, otherwise from params
            pr_num = pr_number_from_event or params.get('pr_number', 'N/A')
            
            # DEBUG: Log what we're receiving
            print(f"DEBUG Jira: repo={repo}, pr_number_from_event={pr_number_from_event}, pr_num={pr_num}")
            
            # Fallback: Try to extract repo and PR from approval_comment if not already set
            if (not repo or repo == 'Not specified') and 'lmudu2/risk-analyzer-poc' in approval_comment:
                repo = 'lmudu2/risk-analyzer-poc'
                print(f"DEBUG Jira: Extracted repo from comment: {repo}")
            
            # Create rich description with all details
            from datetime import datetime
            import re
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            
            description_text = f"""Risk Analysis Report

📋 Repository: {repo or 'Not specified'}
🔢 PR Number: #{pr_num}
⚠️ Risk Level: {risk_level}
🔧 Affected Service: {service_name}

📝 Request Details:
{approval_comment}

🔍 Action Type: {action_type}
⏰ Created: {timestamp}
"""
            
            jira_url = "https://lmudu95.atlassian.net/rest/api/3/issue"
            payload = {
                "fields": {
                    "project": {"key": "SCRUM"},
                    "summary": f"[{risk_level}] Audit: {service_name} - PR #{pr_num}",
                    "description": {
                        "type": "doc", "version": 1, 
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": description_text}]}]
                    },
                    "issuetype": {"name": "Task"}
                }
            }
            req = urllib.request.Request(jira_url, data=json.dumps(payload).encode(), method='POST')
            req.add_header('Authorization', f'Basic {auth}')
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req) as res:
                key = json.loads(res.read())['key']
                response_text = f"SUCCESS: Jira {key} created."

        # --- TOOL: APPROVAL EMAIL ---
        elif func_name == 'send_approval_email':
            pr_num = clean_num(params.get('pr_number'))
            risk_level = params.get('risk_level', 'UNKNOWN')
            service_name = params.get('service_name', 'System')
            details = params.get('details', 'No details provided')
            # Clean up details (remove internal metadata)
            # Use data splitting instead of regex for maximum robustness
            if "[ACTION:" in details:
                clean_details = details.split("[ACTION:")[0].strip()
            else:
                clean_details = details
            
            # Function URL for approval handler
            url = f"https://3cwkd327d3olonkvng7gpdhdk40hksog.lambda-url.us-east-1.on.aws/"
            
            # Build comprehensive email body with HTML
            email_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #f4f4f4; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
                    .risk-high {{ color: #d32f2f; font-weight: bold; }}
                    .risk-medium {{ color: #f57c00; font-weight: bold; }}
                    .risk-low {{ color: #388e3c; font-weight: bold; }}
                    .details {{ background: #fff; padding: 15px; border-left: 4px solid #2196F3; margin: 20px 0; }}
                    .actions {{ margin-top: 30px; text-align: center; }}
                    .btn {{ display: inline-block; padding: 12px 30px; margin: 0 10px; text-decoration: none; border-radius: 5px; font-weight: bold; }}
                    .btn-approve {{ background: #4CAF50; color: white; }}
                    .btn-reject {{ background: #f44336; color: white; }}
                    .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>🔔 PR Risk Analysis - Approval Required</h2>
                    </div>
                    
                    <p><strong>Repository:</strong> {repo}</p>
                    <p><strong>Pull Request:</strong> #{pr_num}</p>
                    <p><strong>Risk Level:</strong> <span class="risk-{risk_level.lower()}">{risk_level}</span></p>
                    <p><strong>Affected Service:</strong> {service_name}</p>
                    
                    <div class="details">
                        <h3>📝 Change Request Details:</h3>
                        <p>{clean_details}</p>
                    </div>
                    
                    <div class="actions">
                        <h3>Please review and take action:</h3>
                        <a href="{url}?decision=Approved&repo={repo}&pr_num={pr_num}" class="btn btn-approve">✅ APPROVE</a>
                        <a href="{url}?decision=Rejected&repo={repo}&pr_num={pr_num}" class="btn btn-reject">❌ REJECT</a>
                    </div>
                    
                    <div class="footer">
                        <p>This is an automated governance notification from the PR Risk Analysis Agent.</p>
                        <p>View on GitHub: https://github.com/{repo}/pull/{pr_num}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            subject = f"🔔 [{risk_level}] Approval Required - PR #{pr_num} ({service_name})"
            if send_actual_email("lmudu95@gmail.com", subject, email_body):
                response_text = "SUCCESS: Email sent."
            else:
                response_text = "ERROR: Email failed."

    except Exception as e:
        print(f"WRITER ERROR: {str(e)}")
        response_text = f"ERROR: {str(e)}"

    # 2. RETURN FORMAT FOR BEDROCK
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'function': func_name,
            'functionResponse': {
                'responseBody': {
                    'TEXT': {
                        'body': response_text
                    }
                }
            }
        }
    }