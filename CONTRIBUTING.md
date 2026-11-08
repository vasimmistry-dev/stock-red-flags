# Contributing

Thanks for helping! Issues and pull requests are welcome.

1. Fork the repository and create a branch.
2. Set it up with `pip install -e ".[test]"`, then run `pytest -q`. All tests must pass.
3. If you add or change a check:
   - add tests showing it **fires** and that it does **not** fire just inside its threshold (see `tests/conftest.py` for the `clean_years()` and `modified()` helpers);
   - put new limits in `Thresholds` rather than hard-coding them;
   - make the explanation plain English and put the triggering numbers in `evidence`;
   - document the rule in the README tables.
4. If you change a score formula, cite the source and update the hand-computed tests.
5. Keep the runtime free of dependencies (standard library only).

Please do not add buy or sell recommendations, or data about real companies presented as a verdict on them.
