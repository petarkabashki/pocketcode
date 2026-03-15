from textual.app import App, ComposeResult
from textual.widgets import Static
from rich.panel import Panel

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield Static(Panel("Can you copy me?"))

if __name__ == "__main__":
    app = TestApp()
    print("Static markup:", hasattr(Static, "markup"))
    print("Static has text_selection:", hasattr(Static("test").styles, "text_selection"))
    print("Static ALLOW_SELECT:", getattr(Static, "ALLOW_SELECT", None))
