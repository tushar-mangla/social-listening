import os

function_code = """
def fetch_facebook_feed(lookback_hours: int = 48, limit: int = 25) -> list[dict]:
    import subprocess
    import json
    import re
    from datetime import datetime, timedelta, timezone
    
    command = ["opencli", "facebook", "feed", "--limit", str(limit), "--format", "json"]
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            timeout=90,
        )
        combined = (process.stdout or "") + (process.stderr or "")

        if process.returncode != 0:
            if re.search(r"(?i)\b(c_user|cookie|login|log in|sign in|session|authenticate|not logged in|captcha|challenge)\b", combined):
                raise OpenCLIAuthenticationError(
                    f"facebook feed failed (Auth/Session error returncode={process.returncode})"
                )
            if re.search(r"(?i)\b(Failed to fetch|fetch failed|ERR_[A-Z_]+|connection|timed out|timeout|Navigation rejected)\b", combined):
                raise OpenCLIFetchError(
                    f"facebook feed failed (Fetch error returncode={process.returncode})"
                )
            if re.search(r"(?i)(?:\bhttp\s*)?\b429\b|\btoo many requests\b|\brate.?limit\b", combined):
                raise OpenCLIRateLimitError(
                    f"facebook feed rate-limited (returncode={process.returncode})"
                )
            raise OpenCLIExecutionError(
                f"facebook feed failed with returncode {process.returncode}"
            )

        output = process.stdout.strip()
        if not output:
            return []

        try:
            raw_posts = json.loads(output)
            if not isinstance(raw_posts, list):
                raw_posts = [raw_posts]
            raw_posts = [p for p in raw_posts if isinstance(p, dict)]
        except json.JSONDecodeError:
            raw_posts = []
            for line in output.splitlines():
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        raw_posts.append(item)
                except json.JSONDecodeError:
                    pass

    except subprocess.TimeoutExpired as exc:
        raise OpenCLIExecutionError("opencli facebook feed timed out after 90 seconds.") from exc

    leads = []
    retrieved_at = datetime.now(timezone.utc)

    for post in raw_posts:
        content = post.get("content") or post.get("text") or ""
        author = post.get("author") or ""
        url = post.get("url") or ""
        
        if not content:
            continue
            
        if author == "Fallback Facebook Feed" or author == "Fallback":
            chunks = re.split(r'(?i)Shared post|(?i)Like\s*Comment\s*Share', content)
            for chunk in chunks:
                chunk = chunk.replace('Facebook', '').strip()
                if len(chunk) < 40:
                    continue
                
                fingerprint = f"FacebookUser:{chunk[:80]}"
                leads.append({
                    "post_id": fingerprint,
                    "source": "facebook",
                    "content": chunk,
                    "url": None,
                    "posted_at": retrieved_at,
                    "author": "Facebook User",
                    "platform": "facebook",
                    "community": None,
                    "query_family": "feed",
                    "exact_query": "feed",
                    "retrieved_at": retrieved_at,
                    "posted_at_fallback": "retrieved_at",
                })
            continue

        fingerprint = f"{author}:{content[:80]}"
        post_id = url if url else fingerprint

        if not post_id:
            continue

        leads.append({
            "post_id": post_id,
            "source": "facebook",
            "content": content,
            "url": url or None,
            "posted_at": retrieved_at,
            "author": author or None,
            "platform": "facebook",
            "community": None,
            "query_family": "feed",
            "exact_query": "feed",
            "retrieved_at": retrieved_at,
            "posted_at_fallback": "retrieved_at",
        })

    return leads
"""

with open("listening_loop/opencli_adapter.py", "a") as f:
    f.write("\n" + function_code)
