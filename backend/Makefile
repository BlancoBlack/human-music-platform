.PHONY: seed-v2 run test reset-db

run:
	./.venv/bin/python -m uvicorn app.main:app --reload

seed-v2:
	./.venv/bin/python scripts/seed_data_v2.py --events 500 --no-reset --seed 42

reset-db:
	rm -f test.db

test:
	./.venv/bin/python scripts/test_distribution_vs_ledger_parity.py
