from pathlib import Path


def test_visible_branding_is_mericrawler():
    files = [Path(__file__).parents[1] / "src/app.py", Path(__file__).parents[1] / "src/ui_styles.py"]
    text = "\n".join(path.read_text() for path in files).lower()
    assert "dravastudio" not in text
    assert "mericrawler" in text
