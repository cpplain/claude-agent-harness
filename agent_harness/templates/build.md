## YOUR ROLE - BUILD PHASE

You are continuing work on a project. Each session starts fresh.

### STEP 1: Get Your Bearings

```bash
pwd && ls -la
cat .agent-harness/spec.md
cat .agent-harness/feature_list.json
cat claude-progress.txt
git log --oneline -10
```

### STEP 2: Choose One Feature

Find a feature with `"passes": false` in feature_list.json.

### STEP 3: Implement & Test

Implement the feature and verify it works.

### STEP 4: Update Progress

- Mark feature as `"passes": true` in feature_list.json
- Update `claude-progress.txt`
- Commit your changes

```bash
git add . && git commit -m "Implement [feature name]"
```
