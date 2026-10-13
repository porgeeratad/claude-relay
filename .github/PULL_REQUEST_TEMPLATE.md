## What and why

## How I checked it
- [ ] `python3 tests/test_bash_guard.py` and `python3 tests/test_bash_guard_battery.py`
- [ ] `python3 tests/test_relay_dir.py`
- [ ] `scripts/leak-check.sh all` and `bash tests/test_leak_check.sh`
- [ ] `claude plugin validate --strict .claude-plugin/plugin.json`
- [ ] New guard rule or change: a deny case **and** an allow case in the tests
