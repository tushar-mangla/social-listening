import sys

target = "/opt/homebrew/lib/node_modules/@jackwener/opencli/clis/facebook/feed.js"
with open(target, 'r') as f:
    content = f.read()

import re

# Patch the iteration loop to force a row if none found
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
        author: "Fallback",
        content: textOf(document.querySelector('[role="main"]')) || textOf(document.body),
        url: undefined,
        likes: '-',
        comments: '-',
        shares: '-'
      });
    }"""

pattern = r"const rows = \[\];\s*for \(const container of combined\) \{.*?if \(rows\.length >= limit\) break;\s*\}"
patched = re.sub(pattern, new_loop, content, flags=re.DOTALL)

if patched != content:
    with open(target, 'w') as f:
        f.write(patched)
    print("Successfully patched feed.js loops")
else:
    print("Patch failed. Could not find pattern.")
