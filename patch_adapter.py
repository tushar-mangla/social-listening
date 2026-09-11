import re

with open("listening_loop/opencli_adapter.py", "r") as f:
    content = f.read()

target = """    for post in raw_posts:
        # Feed columns: index, author, content, likes, comments, shares
        content = post.get("content") or post.get("text") or ""
        if not content:
            continue
        # Build a stable synthetic post_id from author + content fingerprint
        author = post.get("author") or ""
        url = post.get("url") or ""
        fingerprint = f"{author}:{content[:80]}"
        post_id = url if url else fingerprint

        if not post_id:
            continue

        # Feed posts have no reliable timestamp; always use fallback
        leads.append({
            "post_id": post_id,
            "source": "facebook",
            "content": content,
            "url": url or None,
            "posted_at": retrieved_at,   # timestamp fallback (feed has no timestamp)
            "author": author or None,
            "platform": "facebook",
            "community": None,
            "query_family": "feed",
            "exact_query": "feed",
            "retrieved_at": retrieved_at,
            "posted_at_fallback": "retrieved_at",
        })"""

replacement = """    for post in raw_posts:
        # Feed columns: index, author, content, likes, comments, shares
        content = post.get("content") or post.get("text") or ""
        author = post.get("author") or ""
        url = post.get("url") or ""
        
        if not content:
            continue
            
        # Handle the custom opencli feed patch which returns a massive blob
        if author == "Fallback Facebook Feed":
            # Split by common post separators
            import re
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

        # Build a stable synthetic post_id from author + content fingerprint
        fingerprint = f"{author}:{content[:80]}"
        post_id = url if url else fingerprint

        if not post_id:
            continue

        # Feed posts have no reliable timestamp; always use fallback
        leads.append({
            "post_id": post_id,
            "source": "facebook",
            "content": content,
            "url": url or None,
            "posted_at": retrieved_at,   # timestamp fallback (feed has no timestamp)
            "author": author or None,
            "platform": "facebook",
            "community": None,
            "query_family": "feed",
            "exact_query": "feed",
            "retrieved_at": retrieved_at,
            "posted_at_fallback": "retrieved_at",
        })"""

if target in content:
    with open("listening_loop/opencli_adapter.py", "w") as f:
        f.write(content.replace(target, replacement))
    print("Patched opencli_adapter.py successfully!")
else:
    print("Failed to find target in opencli_adapter.py")
