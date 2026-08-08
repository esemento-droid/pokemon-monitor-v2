---
inclusion: always
---

# VPS Command Execution Pattern

The user cannot easily copy-paste long commands. When providing VPS commands for the user to run:

1. **Always wrap commands in a paste.rs-friendly format** — give the user a single command that:
   - Runs the actual command on VPS
   - Pipes the output to `curl -s -d @- https://paste.rs/` 
   - This generates a paste.rs URL the user can share back

2. **Format:**
```bash
COMMAND_HERE 2>&1 | curl -s -d @- https://paste.rs/
```

3. **For multi-line or complex commands:**
```bash
bash -c 'COMMANDS_HERE' 2>&1 | curl -s -d @- https://paste.rs/
```

4. **The user will paste back the paste.rs URL** — fetch it to see the output.

5. **This applies to ALL commands meant for the VPS** — never give raw commands without the paste.rs pipe.
