## YOUR ROLE - BUILD PHASE

You are implementing a Python calculator module. Each session starts fresh.

### STEP 1: Get Your Bearings

```bash
pwd && ls -la
cat .agent-harness/spec.md
cat .agent-harness/feature_list.json
cat claude-progress.txt
git log --oneline -5
```

### STEP 2: Choose One Feature

Find a feature with `"passes": false` in feature_list.json and implement it.

### STEP 3: Implement & Test

1. Add the function to `calculator.py`
2. Add comprehensive tests to `test_calculator.py`
3. Run tests: `python -m unittest test_calculator -v`
4. Verify all tests pass before continuing

### STEP 4: Update Progress

- Mark feature as `"passes": true` in feature_list.json
- Update `claude-progress.txt` with what you implemented
- Commit your changes

```bash
git add . && git commit -m "Implement [feature name]"
```

### Notes

- Focus on one function at a time
- Test edge cases (zero, negatives, errors)
- All functions should have type hints
- Keep code simple and readable
