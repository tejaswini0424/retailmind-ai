from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_all_pages_render():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=40).run()
    assert not app.exception
    for page in ['Products & stores','Customers','Data studio','Ask RetailMind','Overview']:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, str(app.exception)
    app.sidebar.radio[0].set_value('Ask RetailMind').run()
    next(button for button in app.button if button.label=='Ask selected question').click().run()
    assert not app.exception
    assert len(app.chat_message)==2
