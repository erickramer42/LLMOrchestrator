# Portability Guide: Using This Tribunal on Other Codebases

This document explains how to repurpose the tribunal for a different domain or codebase. The core patterns are universal; only domain expertise needs customization.

## Quick Start

Clone this repo and update these three places:

### Step 1: Update Models

Edit MODELS in orchestrator.py:

MODELS = {
    "code_reviewer": "your-reviewer-model",
    "domain_expert": "your-domain-model",
}

### Step 2: Configure Domain Expert Prompt

Edit AUTO_ENGINEER_PROMPT in reviewer_prompt.py. Replace domain-specific criteria with your domain's concerns:

DOMAIN_SPECIFIC_CRITERIA = """
1. Alignment with project goals and roadmap priorities
2. Domain-specific risks unique to your field
3. Extensibility considerations for future evolution
4. Regulatory/compliance/safety considerations requiring documentation
"""

The blockers, concerns, questions, and reasoning fields remain unchanged.

### Step 3: Adapt Eval Harness Fixtures

Copy eval_harness/probe.py and eval_harness/bakeoff.py into your repo, update the test cases:

CASES = [
    ("your_failure_mode_1", True, "code snippet with bug", False),
    ("your_clean_pattern", False, "clean reference code", True),
]

### Step 4: Verify with Multi-Run Probes

Run the probe against a clean artifact from your codebase:

python -m eval_harness.probe --model your-reviewer-model --fixture path/to/clean/file.h

Target thresholds: blocker-FP rate < 5%, timeout rate < 20%.

## Universal Patterns (Don't Change These)

- Derived verdicts — Never trust model self-reported labels; derive from content
- Prompt versioning — Stamp PROMPT_VERSION in every decision record
- Multi-run probes — Single runs are anecdotes; aggregates are data
- Parse failures fail closed — Unusable reviews block rather than slip through
- Artifact-type scoping — Different standards for interfaces vs. implementations

## Domain-Specific Customization (Only These Need Changes)

Element | Customize For Your Domain
--------|--------------------------
DOMAIN_SPECIFIC_CRITERIA | Your domain's risks and priorities
CASES in bakeoff.py | Your codebase's failure modes
Fixture files | Your codebase's clean reference patterns
Model selections | Models appropriate for your compute budget

## Example: Adapting for Web Application Review

Domain expert prompt changes:

DOMAIN_SPECIFIC_CRITERIA = """
1. Security vulnerabilities (SQL injection, XSS, CSRF, auth bypass)
2. Performance anti-patterns (N+1 queries, unindexed lookups, sync blocking)
3. API contract violations (breaking changes, undocumented deprecations)
4. Accessibility and WCAG compliance concerns
"""

Bakeoff fixture changes:

CASES = [
    ("sql_injection", True, "SELECT * FROM users WHERE id = '" + user_input + "'", False),
    ("clean_api_route", False, "@app.route('/users', methods=['GET'])\ndef get_users():\n    return jsonify(User.query.all())", True),
]

## Timeline Expectation

For a new domain adaptation:
- Day 1: Update prompts, run initial probes, adjust scope clauses
- Day 2: Bake-off against 5–10 custom fixtures, iterate prompt tweaks
- Day 3: First production debate on real code, validate decision quality

Total: 3 days from clone to working tribunal in new domain.

## Troubleshooting

Problem | Likely Cause | Fix
--------|--------------|-----
High blocker-FP rate on clean code | Domain expert prompt too aggressive | Add "Do not flag missing implementation as blocker" clause
Timeout rate > 20% | Context window too large for GPU | Reduce NUM_CTX from 16384 to 8192
Parse failures frequent | Thinking tokens exhausting budget | Increase num_ctx or reduce system prompt length
Detection rate < 80% | Model too small for task | Upgrade to frontier model or increase context

## Questions?

The eval harness is designed to catch these issues automatically. If your first probe run shows problems, iterate using the troubleshooter table above — you're measuring your way to a working configuration, not starting with one.