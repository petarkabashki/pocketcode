from prompt_toolkit.completion import Completion, Completer
from prompt_toolkit.document import Document


class AgentCompleter(Completer):
    """Completes agent names for ``/agent switch <name>``."""

    def __init__(self, engine):
        self._engine = engine

    def get_completions(self, document: Document, complete_event):
        try:
            profile_names = (
                self._engine.list_available_agents()
                if hasattr(self._engine, "list_available_agents")
                else self._engine.list_agent_profiles()
            )
        except Exception:
            return
        word = document.get_word_before_cursor(WORD=True)
        visible_names = []
        for name in sorted({str(name) for name in profile_names}):
            profile = None
            try:
                if hasattr(self._engine, "get_agent"):
                    profile = self._engine.get_agent(name)
                elif hasattr(self._engine, "get_agent_profile"):
                    profile = self._engine.get_agent_profile(name)
            except Exception:
                profile = None
            if profile is not None and getattr(profile, "source", None) == "synthesised":
                continue
            visible_names.append(name)

        for name in visible_names:
            if name.startswith(word):
                yield Completion(name, start_position=-len(word))

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
