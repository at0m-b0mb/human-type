.PHONY: test test-engine test-ui run clean

# Everything. The interface tests skip themselves without a display.
test:
	@python3 tests/test_realism.py
	@python3 tests/test_docimport.py
	@python3 tests/test_theme.py
	@python3 tests/test_ui.py

# The parts that need neither a screen nor a keyboard — what CI runs.
test-engine:
	@python3 tests/test_realism.py
	@python3 tests/test_docimport.py
	@python3 tests/test_theme.py

test-ui:
	@python3 tests/test_ui.py

run:
	@python3 human-type.py

clean:
	@rm -rf __pycache__ tests/__pycache__ *.pyc
