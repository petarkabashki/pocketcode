from __future__ import annotations

from pocketcode.core.prompt_loader import load_prompt_markdown


class TestPromptLoader:
    def test_load_prompt_markdown_resolves_resource_root_relative_prompts_path(self, tmp_path):
        modes_dir = tmp_path / ".pocketcode" / "modes"
        prompts_dir = tmp_path / ".pocketcode" / "prompts"
        modes_dir.mkdir(parents=True, exist_ok=True)
        prompts_dir.mkdir(parents=True, exist_ok=True)
        (prompts_dir / "review.md").write_text("Review prompt", encoding="utf-8")

        text, sources = load_prompt_markdown(
            base_dir=modes_dir,
            prompt_file="prompts/review.md",
            fallback_dirs=(prompts_dir,),
        )

        assert text == "Review prompt"
        assert sources == [str((prompts_dir / "review.md").resolve())]
