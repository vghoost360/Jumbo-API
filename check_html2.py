import re

html = open('/app/templates/index.html').read()
lines = html.split('\n')

# Check ALL tag balance
for tag in ['div', 'section', 'main', 'nav', 'aside', 'header', 'a', 'span', 'button', 'p', 'h1', 'h2', 'h3', 'ul', 'li', 'form', 'input', 'label', 'select', 'option', 'table', 'tr', 'td', 'th', 'thead', 'tbody']:
    opens = len(re.findall(f'<{tag}[\\s>/]', html))
    closes = len(re.findall(f'</{tag}>', html))
    # Self-closing tags don't need closes
    self_closing = len(re.findall(f'<{tag}[^>]*/>', html))
    effective_opens = opens - self_closing
    if effective_opens != closes:
        print(f"MISMATCH: <{tag}> opens={opens} self_closing={self_closing} effective={effective_opens} closes={closes} diff={effective_opens-closes}")

# Check for unclosed comments
comments_open = html.count('<!--')
comments_close = html.count('-->')
print(f"Comments: open={comments_open} close={comments_close}")

# Check for stray < or > that might break parsing
# Look for < not followed by a valid tag or /
stray = re.findall(r'<(?![a-zA-Z/!])', html)
print(f"Stray '<' characters: {len(stray)}")

# Check for unclosed style or class attributes
# Find all attribute values and check they're properly quoted
broken_attrs = re.findall(r'(?:class|style|id|href|src|onclick|data-\w+)=["\'][^"\']*(?:\n)', html)
if broken_attrs:
    print(f"Potentially broken attributes spanning newlines: {len(broken_attrs)}")
    for a in broken_attrs[:5]:
        print(f"  {a.strip()[:80]}")

# Check for invisible characters
for i, line in enumerate(lines):
    for j, c in enumerate(line):
        if ord(c) > 127 and ord(c) not in [160, 8211, 8212, 8216, 8217, 8220, 8221, 8226, 8230, 169, 174, 8364]:
            print(f"Unusual char U+{ord(c):04X} at line {i+1} col {j+1}: ...{line[max(0,j-10):j+10]}...")

# Check the full document structure
print("\n--- Document structure (first 5 and last 5 non-empty lines) ---")
non_empty = [(i+1, l.strip()) for i, l in enumerate(lines) if l.strip()]
for ln, content in non_empty[:5]:
    print(f"L{ln}: {content[:100]}")
print("...")
for ln, content in non_empty[-5:]:
    print(f"L{ln}: {content[:100]}")
