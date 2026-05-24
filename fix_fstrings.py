import re

with open('etl/derive_outlook_action.py', 'r') as f:
    content = f.read()

# Find all f-strings and replace %(name)s with %%(name)s
# Match text(f"""...""") and replace %(xxx)s with %%(xxx)s
pattern = r'text\(f"""([\s\S]*?)"""'
def replace_func(match):
    inner = match.group(1)
    # Replace %(name)s with %%(name)s
    inner = re.sub(r'%\((\w+)\)s', r'%%(\1)s', inner)
    return f'text(f"""{inner}"""'

new_content = re.sub(pattern, replace_func, content, flags=re.DOTALL)

with open('etl/derive_outlook_action.py', 'w') as f:
    f.write(new_content)

print("Fixed all f-strings with parameter syntax")
