1. Run existing tests or create your own
python tests/run_tests.py --verbose

First, generate context for each service
cd auth-service && python ../../../../llm-context-setup.py && cd ..
cd user-service && python ../../../../llm-context-setup.py && cd ..
cd api-gateway && python ../../../../llm-context-setup.py && cd ..

Now detect conflicts
python ../../../llm-context-setup.py workspace conflicts

View the report
cat workspace-context/conflicts-report.md



3. Test workspace mode on the fixture
cd tests/fixtures/multi-repo
python ../../../llm-context-setup.py workspace list
python ../../../llm-context-setup.py workspace query --tags core
python ../../../llm-context-setup.py workspace query --tags auth
python ../../../llm-context-setup.py workspace validate

4. Generate context for each service
cd auth-service
python ../../../../llm-context-setup.py
cat .llm-context/external-dependencies.json

cd ../user-service
python ../../../../llm-context-setup.py
cat .llm-context/external-dependencies.json

cd ../api-gateway
python ../../../../llm-context-setup.py
cat .llm-context/external-dependencies.json

4. Generate workspace context
cd ..
python ../../../llm-context-setup.py workspace query --tags core --generate

# 5. Check generated workspace context
cat workspace-context/WORKSPACE.md
cat workspace-context/change-sequence.md
cat workspace-context/dependency-graph.md


/*
Step 1 — Add “Intent → tags” tests (highest ROI)

Example:

{
  "input": "add new platform integration",
  "expectedTags": ["platforms"]
}

Step 2 — Add “capability inference tests”
{
  "repo": "repo-a",
  "expectedCapabilities": ["platform-management"]
}

Step 3 — Add “workspace expansion correctness”
{
  "seedTags": ["platforms"],
  "expectedRepos": ["repo-a", "repo-b", "repo-c"]
}

Step 4 — Add impact simulation tests
{
  "changedApi": "POST /platform",
  "expectedImpactedRepos": ["repo-b", "repo-c"]
}

Step 5 — Add drift detection tests

{
  "astApi": ["POST /platform"],
  "declaredApi": [],
  "expectedFix": "missing-declaration"
}

Core idea

Each test describes a reasoning scenario, not a unit function.

⸻

Suggested format: ccc-test.json
{
  "name": "add platform integration",
  "input": {
    "intent": "add new platform integration"
  },

  "expected": {
    "tags": ["platforms"],

    "repos": ["repo-a", "repo-b", "repo-c"],

    "capabilities": [
      {
        "repo": "repo-a",
        "mustInclude": ["platform-management"]
      }
    ],

    "impact": {
      "changedApi": "POST /platform",
      "impactedRepos": ["repo-b", "repo-c"]
    }
  }
}

Why this matters

You now test:
	•	semantic correctness
	•	structural correctness
	•	propagation correctness
	•	system-level reasoning

Not just “function outputs”.


*/