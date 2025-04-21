import pytest


@pytest.mark.xfail(reason="Intentional failure for testing setup")
def test_test_failure():
    pytest.fail("This test should fail.")


def test_test_success():
    assert True, "This test should pass."
