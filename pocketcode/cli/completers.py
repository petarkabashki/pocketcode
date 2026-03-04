from prompt_toolkit.completion import Completion, Completer
from prompt_toolkit.document import Document


class SnippetRemoveCompleter(Completer):
    """Completes snippet names for `/context remove snippet <name>`."""

    def __init__(self, cli_context):
        self._cli_context = cli_context

    def get_completions(self, document: Document, complete_event):
        snippet_names = list(self._cli_context.get("snippets", {}).keys())
        word_before_cursor = document.get_word_before_cursor()
        for name in snippet_names:
            if name.startswith(word_before_cursor):
                yield Completion(name, start_position=-len(word_before_cursor))
