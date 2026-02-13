## YOUR ROLE - INIT PHASE

You are setting up a Python calculator project.

### STEP 1: Read the Specification

Read `.agent-harness/spec.md` to understand the calculator requirements.

### STEP 2: Create Feature List

Create `.agent-harness/feature_list.json` with one entry for each requirement:

```json
[
  {
    "name": "add() function",
    "description": "Addition of two numbers",
    "passes": false
  },
  {
    "name": "subtract() function",
    "description": "Subtraction of two numbers",
    "passes": false
  },
  {
    "name": "multiply() function",
    "description": "Multiplication of two numbers",
    "passes": false
  },
  {
    "name": "divide() function",
    "description": "Division with zero check",
    "passes": false
  },
  {
    "name": "power() function",
    "description": "Exponentiation",
    "passes": false
  },
  {
    "name": "modulo() function",
    "description": "Modulo with zero check",
    "passes": false
  },
  {
    "name": "Test coverage",
    "description": "All tests pass including edge cases",
    "passes": false
  }
]
```

### STEP 3: Initialize Git

```bash
git init
git add .
git commit -m "Initial setup: feature list"
```

### STEP 4: Create Skeleton Files

Create empty `calculator.py` and `test_calculator.py` files.

### STEP 5: Create Progress Notes

Create `claude-progress.txt` documenting what you set up.
