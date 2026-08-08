---
inclusion: always
---

# VPS Command Execution Pattern

The user runs commands on VPS from their PHONE. They cannot copy-paste multiline commands.

## Rules:

1. **NEVER give multiline commands in chat** — they break on mobile paste
2. **For anything longer than one line** — save it as a .py or .sh script file in the repo, push to main, then tell user to git pull and run it
3. **Always pipe output to paste.rs** so user can share results back
4. **Format for simple commands:**

```
git pull && DISPLAY=:99 /opt/pokemon-monitor-v2/venv/bin/python3 SCRIPT.py 2>&1 | curl -s -d @- https://paste.rs/
```

5. **User will paste back the paste.rs URL** — fetch it with web_fetch to see output
6. **NEVER use `curl paste.rs | bash`** — newlines get mangled and it breaks
7. **Always use the venv python:** `/opt/pokemon-monitor-v2/venv/bin/python3`
8. **Always prefix with `DISPLAY=:99`** for any browser automation
