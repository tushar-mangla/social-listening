import subprocess
import json
from datetime import datetime, timedelta, timezone
from typing import Union

def run_opencli(platform: str, query: str) -> list[dict]:
    """
    Runs the opencli command with the specified platform and query,
    and returns the parsed JSON output.
    """
    command = ["opencli", platform, "search", query]
    if platform == "reddit":
        command.extend(["--sort", "new"])
    command.extend(["--format", "json"])
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8'
        )
        
        output = process.stdout.strip()
        if not output:
            return []

        try:
            parsed = json.loads(output)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            # Some OpenCLI versions emit one JSON object per line.
            results = []
            for line in output.splitlines():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Warning: Could not decode JSON line: {line}")
            return results

    except FileNotFoundError:
        print("Error: 'opencli' command not found. Make sure it is installed and in your PATH.")
        return []
    except subprocess.CalledProcessError as e:
        print(f"Error executing opencli: {e}")
        print(f"Stderr: {e.stderr}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

def parse_timestamp(timestamp_val: Union[str, int, float, None]) -> Union[datetime, None]:
    """Parses a timestamp (ISO string, Twitter RFC 2822, epoch int/float) into a timezone-aware UTC datetime."""
    if timestamp_val is None or timestamp_val == "":
        return None

    # Epoch passed as int or float
    if isinstance(timestamp_val, (int, float)):
        try:
            return datetime.fromtimestamp(timestamp_val, tz=timezone.utc)
        except (ValueError, OSError):
            return None

    if isinstance(timestamp_val, str):
        val = timestamp_val.strip()
        # Epoch passed as string
        if val.isdigit():
            try:
                return datetime.fromtimestamp(float(val), tz=timezone.utc)
            except (ValueError, OSError):
                pass

        # ISO 8601
        try:
            iso_val = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass

        # Twitter / RFC 2822 format (e.g. "Sun Aug 30 23:13:49 +0000 2026")
        try:
            return datetime.strptime(val, "%a %b %d %H:%M:%S %z %Y")
        except (ValueError, TypeError):
            pass

        # Standard YYYY-MM-DD HH:MM:SS or YYYY-MM-DD
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

    print(f"Warning: Could not parse timestamp: {timestamp_val}")
    return None

def fetch_leads(platform: str, keywords: list[str], lookback_hours: int = 5) -> list[dict]:
    """
    Fetches leads from a given platform using opencli, filtering by keywords and time.
    """
    query = " OR ".join(f'"{k}"' for k in keywords)
    raw_posts = run_opencli(platform, query)
    
    leads = []
    time_limit = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    
    for post in raw_posts:
        post_id = post.get("id_str") or post.get("id") or post.get("url")
        if not post_id:
            continue

        # Extract content based on platform/field availability
        content = post.get("text") or post.get("content") or ""
        if not content and (post.get("title") or post.get("selftext")):
            title = post.get("title") or ""
            selftext = post.get("selftext") or ""
            content = f"{title}\n{selftext}".strip() if selftext else title

        # Extract timestamp based on platform/field availability
        raw_ts = post.get("timestamp") or post.get("created_at") or post.get("created_utc")
        posted_at = parse_timestamp(raw_ts)

        if not posted_at or posted_at < time_limit:
            continue
            
        leads.append({
            "post_id": str(post_id),
            "source": platform,
            "content": content,
            "url": post.get("url"),
            "posted_at": posted_at,
        })
            
    return leads
