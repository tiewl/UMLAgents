import json
with open('architect_function.py', 'r') as f:
    func = f.read()

old = '    finally:\n        session.close()\n\ndef main():\n'
new = '    finally:\n        session.close()\n\n' + func + '\n\ndef main():\n'
print(json.dumps(new))