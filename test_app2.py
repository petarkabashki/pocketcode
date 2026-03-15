from textual.app import App, ComposeResult
from textual.widgets import Static
from rich.panel import Panel

class TestApp(App):
    def compose(self) -> ComposeResult:
        # yield several to test
        yield Static(Panel("Can you copy me?"))
        yield Static("Plain text can be selected")

if __name__ == "__main__":
    app = TestApp()
    for child in app.compose():
        print(type(child), getattr(child, "ALLOW_SELECT", None))
