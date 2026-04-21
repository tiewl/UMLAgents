#!/usr/bin/env python3
import re
import sys

with open('cli.py', 'r') as f:
    content = f.read()

# 1. Add architect command function before main()
# Find the pattern: 'finally:\n        session.close()\n\ndef main():'
pattern = r'(\s+finally:\s*\n\s+session\.close\(\)\s*\n\s*\n)(def main\(\):)'
match = re.search(pattern, content, re.MULTILINE)
if not match:
    print("Pattern not found")
    sys.exit(1)

indent = match.group(1)  # includes blank line before def main
# Read architect function from file
with open('architect_function.py', 'r') as f:
    arch_func = f.read()

# Insert architect function
new_section = match.group(1) + arch_func + '\n\n' + match.group(2)
content = content[:match.start()] + new_section + content[match.end():]

# 2. Add subparser for architect command
# Find subparsers section after '# list command'
list_parser_pattern = r'(\s*# list command\s*\n\s*subparsers\.add_parser\("list", help="List projects in database"\))'
match2 = re.search(list_parser_pattern, content, re.MULTILINE)
if match2:
    # Insert architect parser after list parser
    arch_parser = '\n    # architect command\n    parser_arch = subparsers.add_parser("architect", help="Generate UML diagrams")\n    parser_arch.add_argument("project_id", type=int, help="Project ID")\n    parser_arch.add_argument("--diagram-types", help="Comma-separated diagram types (domain,sequence)")'
    new_subparsers = match2.group(1) + arch_parser
    content = content[:match2.start()] + new_subparsers + content[match2.end():]
else:
    print("List parser pattern not found")
    sys.exit(1)

# 3. Update commands dictionary
# Find commands dict: 'commands = {'
commands_pattern = r'(commands = \{)\s*("load-yaml": command_load_yaml,\s*"interactive": command_interactive,\s*"validate": command_validate,\s*"export": command_export,\s*"list": command_list\s*)'
match3 = re.search(commands_pattern, content, re.MULTILINE | re.DOTALL)
if match3:
    # Add architect entry before the closing brace
    new_dict = match3.group(1) + match3.group(2).rstrip() + ',\n    "architect": command_architect\n}'
    content = content[:match3.start()] + new_dict + content[match3.end():]
else:
    print("Commands dict pattern not found")
    sys.exit(1)

# Write updated content
with open('cli.py', 'w') as f:
    f.write(content)

print("Updated cli.py successfully")