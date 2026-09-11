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
      const allText = textOf(document.querySelector('[role="main"]')) || textOf(document.body);
      const splitTexts = allText.split(/Shared post/g).filter(t => t.length > 50);
      for (let i = 0; i < splitTexts.length && i < limit; i++) {
        rows.push({
          index: i + 1,
          author: "Facebook User",
          content: splitTexts[i].replace(/Facebook/g, '').trim(),
          url: undefined,
          likes: '-',
          comments: '-',
          shares: '-'
        });
      }
    }"""

pattern = r"if \(combined\.length === 0\) \{.*?\}\s*\}"""
patched = re.sub(pattern, new_loop, content, flags=re.DOTALL)

if patched != content:
    with open(target, 'w') as f:
        f.write(patched)
    print("Successfully patched feed.js loops with split")
else:
    print("Patch failed.")
