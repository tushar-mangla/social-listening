import sys

target = "/opt/homebrew/lib/node_modules/@jackwener/opencli/clis/facebook/feed.js"
with open(target, 'r') as f:
    content = f.read()

# We need to replace the extractPost function. We'll use regex.
import re
new_func = """function extractPost(root, index) {
      const fullText = textOf(root);
      if (!fullText || fullText.length < 20) return null;
      if (isSuggestionOrChrome(fullText) || isSponsored(fullText)) return null;

      const postUrl = postUrlFrom(root);
      
      return {
        index,
        author: findAuthor(root) || "",
        content: fullText,
        url: postUrl || undefined,
        likes: '-',
        comments: '-',
        shares: '-',
      };
    }"""

pattern = r"function extractPost\(root, index\)\s*\{.*?return \{\s*index,.*?shares: sharesMatch \? clean\(sharesMatch\[1\]\) : '-',\s*\};\s*\}"

patched = re.sub(pattern, new_func, content, flags=re.DOTALL)

if patched != content and new_func in patched:
    with open(target, 'w') as f:
        f.write(patched)
    print("Successfully patched feed.js")
else:
    print("Patch failed.")
