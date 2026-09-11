import sys
import re

target = "/opt/homebrew/lib/node_modules/@jackwener/opencli/clis/facebook/feed.js"
with open(target, 'r') as f:
    content = f.read()

new_loop = """    if (combined.length === 0) {
      combined.push(document.body);
    }
    const rows = [];
    for (const container of combined) {
      const row = extractPost(container, rows.length + 1);
      if (row) rows.push(row);
      if (rows.length >= limit) break;
    }
    
    if (rows.length === 0) {
      rows.push({
        index: 1,
        author: "Fallback Facebook Feed",
        content: textOf(document.body),
        url: "",
        likes: "-",
        comments: "-",
        shares: "-"
      });
    }"""

pattern = r"const rows = \[\];\s*for \(const container of combined\) \{.*?if \(rows\.length >= limit\) break;\s*\}"

patched = re.sub(pattern, new_loop, content, flags=re.DOTALL)

if patched != content:
    with open(target, 'w') as f:
        f.write(patched)
    print("Successfully applied safe fallback patch to feed.js")
else:
    print("Patch failed. Could not find pattern.")
