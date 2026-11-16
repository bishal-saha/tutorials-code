from main import main


def test_main_runs() -> None:
    assert main() == "hello from the template"
