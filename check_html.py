import re

html = open('/app/templates/index.html').read()
lines = html.split('\n')
print(f"Total lines: {len(lines)}")

# Find script tags
scripts = re.findall(r'<script[^>]*>', html)
print(f"Script tags: {len(scripts)}")
for s in scripts:
    print(f"  {s}")

# Check tag balance
for tag in ['div', 'section', 'main', 'nav', 'aside', 'header', 'a', 'span', 'button']:
    opens = len(re.findall(f'<{tag}[\\s>]', html))
    closes = len(re.findall(f'</{tag}>', html))
    status = "OK" if opens == closes else "MISMATCH"
    if opens != closes:
        print(f"  {status}: <{tag}> opens={opens} closes={closes} diff={opens-closes}")

# Check for unclosed quotes in attributes
print(f"Backslash-quotes: {html.count(chr(92) + chr(34))}")

# Look for any syntax issues around script tag
for i, line in enumerate(lines):
    if '<script' in line.lower() or '</script' in line.lower():
        print(f"Line {i+1}: {line.strip()}")

# Check last 20 lines
print("\n--- Last 20 lines ---")
for i, line in enumerate(lines[-20:]):
    print(f"Line {len(lines)-19+i}: {line}")
