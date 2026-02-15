import pytest

# Skip all tests in this directory by default. Docker-dependent tests should
# not run in unit/integration pipelines to avoid external environmental coupling.
pytestmark = pytest.mark.skip(reason="Docker-dependent tests disabled by default")

