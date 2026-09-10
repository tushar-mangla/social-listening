import subprocess
import json
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union


class OpenCLIExecutionError(RuntimeError):
    """Raised when an OpenCLI work item cannot be executed."""


class OpenCLIRateLimitError(OpenCLIExecutionError):
    """Raised when OpenCLI reports an HTTP 429 response."""


class UnsupportedSubredditScopeError(OpenCLIExecutionError):
    """Raised when the installed OpenCLI cannot scope Reddit searches."""


_SUBREDDIT_SCOPE_SUPPORTED: Optional[bool] = None


def _safe_error(value: object) -> str:
    """Canonical redaction + bound for logged subprocess diagnostics."""
    try:
        from listening_loop.qualification import sanitize_error_message

        return sanitize_error_message(value)
    except Exception:
        return str(value).replace("\n", " ").replace("\r", " ")[:300]

def verify_subreddit_scoping_supported() -> None:
    """Verify and cache that the installed OpenCLI documents ``--subreddit``."""
    global _SUBREDDIT_SCOPE_SUPPORTED
    if _SUBREDDIT_SCOPE_SUPPORTED is True:
        return

    command = ["opencli", "reddit", "search", "--help"]
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise UnsupportedSubredditScopeError(
            "OpenCLI Reddit subreddit scope could not be verified."
        ) from exc
    except Exception as exc:
        raise UnsupportedSubredditScopeError(
            f"OpenCLI Reddit subreddit scope verification failed: {_safe_error(exc)}"
        ) from exc

    help_text = process.stdout or ""
    subreddit_option_pattern = r"(?m)^\s*--subreddit(?:\s|=|$)"
    if process.returncode != 0 or not re.search(subreddit_option_pattern, help_text):
        _SUBREDDIT_SCOPE_SUPPORTED = False
        raise UnsupportedSubredditScopeError(
            "Installed OpenCLI does not document --subreddit for Reddit search."
        )
    _SUBREDDIT_SCOPE_SUPPORTED = True


def run_opencli(platform: str, query: str, community: Optional[str] = None) -> list[dict]:
    """
    Runs the opencli command with the specified platform and query,
    and returns the parsed JSON output.
    """
    command = ["opencli", platform, "search", query]
    if platform == "reddit":
        command.extend(["--sort", "new"])
        if community:
            verify_subreddit_scoping_supported()
            command.extend(["--subreddit", community])
    command.extend(["--format", "json"])
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8',
            timeout=60,
        )
        if process.returncode != 0:
            combined = (process.stdout or "") + (process.stderr or "")
            if re.search(r"(?i)(?:\bhttp\s*)?\b429\b|\btoo many requests\b", combined):
                raise OpenCLIRateLimitError(
                    f"{platform} process failed with returncode {process.returncode} (HTTP 429)"
                )
            detail = ""
            if "Failed to fetch" in combined:
                detail = " (fetch failed)"
            raise OpenCLIExecutionError(
                f"{platform} process failed with returncode {process.returncode}{detail}"
            )
        
        output = process.stdout.strip()
        if not output:
            return []

        try:
            parsed = json.loads(output)
            candidates = parsed if isinstance(parsed, list) else [parsed]
            return [item for item in candidates if isinstance(item, dict)]
        except json.JSONDecodeError:
            # Some OpenCLI versions emit one JSON object per line.
            results = []
            for line in output.splitlines():
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        results.append(item)
                except json.JSONDecodeError:
                    # Never dump raw malformed JSON (may contain post content).
                    print("Warning: Could not decode JSON line; skipping malformed line.")
            return results

    except FileNotFoundError as exc:
        raise OpenCLIExecutionError(
            "'opencli' command not found. Make sure it is installed and in your PATH."
        ) from exc
    except subprocess.CalledProcessError as e:
        raise OpenCLIExecutionError(f"Error executing opencli: {_safe_error(e)}") from e
    except subprocess.TimeoutExpired as exc:
        raise OpenCLIExecutionError("opencli timed out after 60 seconds.") from exc
    except Exception as e:
        if isinstance(e, OpenCLIExecutionError):
            raise
        raise OpenCLIExecutionError(f"Unexpected OpenCLI error: {_safe_error(e)}") from e

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

    print("Warning: Could not parse timestamp; skipping unsupported timestamp format.")
    return None

def fetch_leads(
    platform: str,
    query: Union[str, List[str]],
    lookback_hours: int = 5,
    community: Optional[str] = None,
    query_family: Optional[str] = None,
) -> list[dict]:
    """
    Fetches leads from a given platform using opencli, filtering by keywords and time.
    """
    # Accept the old single-item list shape for callers outside the scheduler,
    # but never turn multiple terms into an aggregate query.
    if isinstance(query, list):
        if not query:
            raise ValueError("Query list cannot be empty")
        if len(query) > 1:
            raise ValueError(
                "fetch_leads accepts a single query string; "
                "multiple queries must be executed as discrete query calls"
            )
        exact_query = query[0]
    else:
        exact_query = query
    if not isinstance(exact_query, str) or not exact_query.strip():
        return []
    raw_posts = run_opencli(platform, exact_query, community)
    
    leads = []
    time_limit = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    
    for post in raw_posts:
        if not isinstance(post, dict):
            continue
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
            
        user = post.get("user")
        author = post.get("author") or post.get("username")
        if not author and isinstance(user, dict):
            author = user.get("name") or user.get("username")

        leads.append({
            "post_id": str(post_id),
            "source": platform,
            "content": content,
            "url": post.get("url"),
            "posted_at": posted_at,
            "author": author,
            "platform": platform,
            "community": community,
            "query_family": query_family,
            "exact_query": exact_query,
            "retrieved_at": datetime.now(timezone.utc),
        })
            
    return leads
