with open('tools/sync-corp-style.js', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace("(['\"]@liderman", "(['\"])@liderman")
with open('tools/sync-corp-style.js', 'w', encoding='utf-8') as f:
    f.write(content)
