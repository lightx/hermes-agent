# Hermes Agent: Merge Upstream + Preserve PUSHOVER Plan

> **Goal:** Merge upstream/main (with minimal `tools/__init__.py`) while preserving your PUSHOVER integration and NixOS functionality.

**Architecture:**
- Accept upstream's lazy import philosophy for `tools/__init__.py` (avoids circular deps during hermes_cli.config init)
- Keep PUSHOVER as a clean feature addition (new files + targeted changes)
- Keep NixOS homeModules.nix and docs (these are independent)
- Your Obsidian search tool is optional to keep — decide during execution

---

## Task 1: Create Working Branch from Upstream

**Objective:** Create a clean branch based on upstream/main as the foundation

**Step 1: Fetch upstream and create branch**

```bash
cd ~/source/hermes-agent
git fetch upstream
git checkout -b merge-upstream-pushover upstream/main
```

**Step 2: Verify minimal tools/__init__.py**

```bash
head -20 tools/__init__.py
```

Expected output:
```python
#!/usr/bin/env python3
"""Tools package namespace.

Keep package import side effects minimal. Importing ``tools`` should not
eagerly import the full tool stack, because several subsystems load tools while
``hermes_cli.config`` is still initializing.
...
```

**Step 3: Run tests to verify upstream works**

```bash
python -c "import hermes_cli.config; print('Config loads OK')"
pytest tests/test_cli*.py -v -x --tb=short 2>&1 | head -50
```

Expected: Tests pass (or at least config loads without circular import errors)

**Step 4: Commit checkpoint**

```bash
git add -A
git commit -m "checkpoint: upstream/main baseline verified"
```

---

## Task 2: Cherry-Pick PUSHOVER Platform Files (Clean Additions)

**Objective:** Add your PUSHOVER platform adapter (new file, no conflicts)

**Step 1: Cherry-pick PUSHOVER platform file**

```bash
cd ~/source/hermes-agent
git cherry-pick 6745ade0 --no-commit
```

**Step 2: Check only expected files staged**

```bash
git diff --cached --stat
```

Expected files:
- `gateway/platforms/pushover.py` (NEW - keep)
- `gateway/config.py` (MOD - verify Platform.PUSHOVER added)
- `gateway/run.py` (MOD - verify PUSHOVER routing)
- `gateway/channel_directory.py` (MOD - minor)
- `tools/send_message_tool.py` (MOD - verify _send_pushover)
- `toolsets.py` (MOD - verify hermes-pushover toolset)
- `agent/prompt_builder.py` (MOD - verify PLATFORM_HINTS)
- `hermes_cli/gateway.py` (MOD - verify CLI entries)
- `hermes_cli/plugins.py` (MOD - verify plugin hook)
- `hermes_cli/status.py` (MOD - verify status entry)
- `cron/scheduler.py` (MOD - minor)

**Step 3: Verify Obsidian search additions are preserved**

The Obsidian search tool and skill should be kept:
- `skills/productivity/obsidian-chroma/SKILL.md`
- `tools/obsidian_search_tool.py`

Verify they are staged:
```bash
git diff --cached --name-only | grep -E "(obsidian|chroma)"
```

Expected output:
```
skills/productivity/obsidian-chroma/SKILL.md
tools/obsidian_search_tool.py
```

**Step 4: Run tests**

```bash
pytest tests/gateway/test_pushover.py -v
python -c "from gateway.platforms.pushover import PushoverAdapter; print('Pushover imports OK')"
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add Pushover platform integration"
```

---

## Task 3: Handle tools/__init__.py Divergence Properly

**Objective:** Ensure your eager imports in tools/__init__.py are resolved without breaking upstream's lazy philosophy

**Analysis:**

Your branch's `tools/__init__.py` has 150+ lines of eager imports:
```python
from .terminal_tool import terminal_tool, ...
from .vision_tools import vision_analyze_tool, ...
# ... etc
```

Upstream's version is minimal (prevents circular imports during config init).

**Decision matrix:**

| Import | Likely Used By | Action |
|--------|---------------|--------|
| `terminal_tool` | acp_adapter/server.py | Already uses `from tools import terminal_tool` |
| `browser_tool` | tests/ | Tests import directly |
| `vision_analyze_tool` | ? | Check usage |
| `obsidian_search_tool` | Your addition | If keeping Obsidian, needs import |
| Other tools | Various | Check actual usage |

**Step 1: Check which imports are actually required**

```bash
cd ~/source/hermes-agent

# Check for direct tools.X imports
grep -r "from tools import" --include="*.py" | grep -v test | grep -v __pycache__ | sort | uniq

# Check tools.X direct attribute access
grep -r "tools\." --include="*.py" | grep -v "tools\." | head -30
```

**Step 2: If circular import errors occur, identify the minimal fix**

Common pattern causing circular import:
```python
# hermes_cli/config.py imports something
# -> that imports tools
# -> tools/__init__.py imports something
# -> that imports hermes_cli/config.py (CIRCULAR!)
```

The fix is usually **lazy import inside functions**, not eager imports at module level.

**Step 3: If needed, add selective exports to tools/__init__.py**

Only if actually needed, add to `tools/__init__.py` (keep minimal!):

```python
# Add ONLY what's needed for PUSHOVER integration
# If obsidian_search_tool needs to be accessible:
def get_obsidian_search_tool():
    """Lazy import obsidian search tool."""
    from .obsidian_search_tool import obsidian_search_tool
    return obsidian_search_tool
```

But prefer: Let consumers import directly from submodules.

**Step 4: Test circular import**

```bash
python -c "
import sys
# This is what happens when hermes starts
import hermes_cli.config
import tools
print('No circular import!')
"
```

**Step 5: Commit**

```bash
git add tools/__init__.py
git commit -m "fix: resolve tools/__init__.py for upstream compatibility"
```

---

## Task 4: Re-apply NixOS Home Modules

**Objective:** Keep your NixOS home-manager integration

**Step 1: Verify nix files are present**

```bash
ls -la nix/homeModules.nix docs/nixos-setup.md 2>/dev/null || echo "Need to restore from original branch"
```

**Step 2: If missing, copy from original branch**

```bash
git show nix-add-uv-runtime-v2:nix/homeModules.nix > nix/homeModules.nix
git show nix-add-uv-runtime-v2:docs/nixos-setup.md > docs/nixos-setup.md
```

**Step 3: Verify flake.nix includes homeModules**

```bash
grep -A5 "homeManagerModules" flake.nix
```

Expected: `homeManagerModules.default = import ./nix/homeModules.nix { inputs = self; };`

**Step 4: Commit**

```bash
git add nix/homeModules.nix docs/nixos-setup.md
git commit -m "feat(nix): add Home Manager module for persistent gateway"
```

---

## Task 5: Final Verification

**Objective:** Ensure everything works together

**Step 1: Run full test suite**

```bash
cd ~/source/hermes-agent
pytest tests/ -x --tb=short -q 2>&1 | tail -20
```

**Step 2: Verify PUSHOVER tool availability**

```bash
python -c "
from toolsets import TOOLSETS
print('hermes-pushover in toolsets:', 'hermes-pushover' in TOOLSETS)
print('hermes-gateway includes pushover:', any('pushover' in str(t) for t in TOOLSETS['hermes-gateway'].get('includes', [])))
"
```

**Step 3: Verify CLI integration**

```bash
python -m hermes_cli status 2>&1 | head -20
```

**Step 4: Commit final checkpoint**

```bash
git add -A
git commit -m "checkpoint: merge complete, ready for testing"
```

---

## Task 6: Update Main Branch

**Objective:** Replace your nix-add-uv-runtime-v2 with the cleaned merge branch

**Step 1: Backup current branch**

```bash
cd ~/source/hermes-agent
git branch -m nix-add-uv-runtime-v2 nix-add-uv-runtime-v2-backup
```

**Step 2: Rename merge branch to main feature branch**

```bash
git checkout merge-upstream-pushover
git branch -m nix-add-uv-runtime-v2
```

**Step 3: Force push to origin (if needed)**

```bash
# WARNING: This rewrites history on origin
git push origin nix-add-uv-runtime-v2 --force-with-lease
```

**Step 4: Open PR (if applicable)**

Your branch now:
- Is based on latest upstream/main
- Contains only your intentional changes (PUSHOVER + NixOS)
- Has clean history (no merge commits from outdated upstream)

---

## Rollback Plan

If anything goes wrong:

```bash
cd ~/source/hermes-agent
git checkout nix-add-uv-runtime-v2-backup
git branch -D nix-add-uv-runtime-v2
git branch -m nix-add-uv-runtime-v2-backup nix-add-uv-runtime-v2
```

---

## Files Summary

### Will be KEPT from your branch:
- `gateway/platforms/pushover.py` (NEW)
- `nix/homeModules.nix` (NEW)
- `docs/nixos-setup.md` (NEW)
- `tools/obsidian_search_tool.py` (NEW)
- `skills/productivity/obsidian-chroma/SKILL.md` (NEW)
- Modified: `gateway/config.py`, `gateway/run.py`, `gateway/channel_directory.py`
- Modified: `tools/send_message_tool.py`
- Modified: `toolsets.py`
- Modified: `agent/prompt_builder.py`
- Modified: `hermes_cli/gateway.py`, `hermes_cli/plugins.py`, `hermes_cli/status.py`
- Modified: `cron/scheduler.py`

### Will be RESET to upstream:
- `tools/__init__.py` (accept upstream's minimal version)
- `flake.nix` (verify homeModules import)
- Various other files that were auto-modified by merges

### Verification Checklist:

- [ ] PUSHOVER platform adapter exists and imports
- [ ] `hermes-pushover` toolset is defined
- [ ] `hermes-gateway` includes `hermes-pushover`
- [ ] `send_message_tool.py` has `_send_pushover()` function
- [ ] `nix/homeModules.nix` exists
- [ ] `docs/nixos-setup.md` exists
- [ ] `hermes_cli/config.py` loads without circular import
- [ ] Tests pass (or at least PUSHOVER-specific tests pass)

---

*Plan created: Ready for execution via subagent or manual implementation.*