# 1. Run existing tests or create your own
python tests/run_tests.py --verbose

# 2. Test workspace mode on the fixture
cd tests/fixtures/multi-repo
python ../../../llm-context-setup.py workspace list
python ../../../llm-context-setup.py workspace query --tags core
python ../../../llm-context-setup.py workspace query --tags auth
python ../../../llm-context-setup.py workspace validate

# 3. Generate context for each service
cd auth-service
python ../../../../llm-context-setup.py
cat .llm-context/external-dependencies.json

cd ../user-service
python ../../../../llm-context-setup.py
cat .llm-context/external-dependencies.json

cd ../api-gateway
python ../../../../llm-context-setup.py
cat .llm-context/external-dependencies.json

# 4. Generate workspace context
cd ..
python ../../../llm-context-setup.py workspace query --tags core --generate

# 5. Check generated workspace context
cat workspace-context/WORKSPACE.md
cat workspace-context/change-sequence.md
cat workspace-context/dependency-graph.md
