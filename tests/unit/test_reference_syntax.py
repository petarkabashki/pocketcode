from pocketcode.core.reference_syntax import (
    parse_prompt_reference,
    parse_reference,
    typed_reference_kind,
)


class TestParseReference:
    def test_parses_typed_registry_reference(self):
        reference = parse_reference("tool:core.read_file", allowed_kinds={"tool"})

        assert reference.kind == "tool"
        assert reference.target == "core.read_file"
        assert reference.container == "core"
        assert reference.name == "read_file"
        assert reference.is_qualified is True
        assert reference.as_registry_key() == "core.read_file"
        assert reference.as_typed() == "tool:core.read_file"

    def test_normalizes_old_hash_and_typed_forms(self):
        reference = parse_reference("prompt:resource_root.pocketcode#review", allowed_kinds={"prompt"})

        assert reference.kind == "prompt"
        assert reference.target == "resource_root.pocketcode.review"
        assert reference.container == "resource_root.pocketcode"
        assert reference.name == "review"

    def test_rejects_disallowed_kind(self):
        try:
            parse_reference("prompt:core.review", allowed_kinds={"tool"})
        except ValueError as exc:
            assert "not allowed here" in str(exc)
        else:
            raise AssertionError("Expected ValueError for disallowed typed kind")

    def test_tracks_unqualified_reference(self):
        reference = parse_reference("read_file")

        assert reference.kind is None
        assert reference.target == "read_file"
        assert reference.container is None
        assert reference.name == "read_file"
        assert reference.is_qualified is False


class TestParsePromptReference:
    def test_requires_prompt_prefix(self):
        try:
            parse_prompt_reference("core.review")
        except ValueError as exc:
            assert "must start with 'prompt:'" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing prompt prefix")

    def test_accepts_prompt_reference(self):
        reference = parse_prompt_reference("prompt:core.review")

        assert reference.kind == "prompt"
        assert reference.target == "core.review"
        assert reference.as_typed() == "prompt:core.review"


class TestTypedReferenceKind:
    def test_returns_none_for_untyped_reference(self):
        assert typed_reference_kind("core.review") is None

    def test_detects_known_prefix(self):
        assert typed_reference_kind("agent:core.react") == "agent"


class TestStrictNormalization:
    def test_rejects_double_colon_references(self):
        try:
            parse_reference("core::read_file", allowed_kinds={"tool"})
        except ValueError as exc:
            assert "unsupported '::' separators" in str(exc)
        else:
            raise AssertionError("Expected ValueError for unsupported :: separator")
