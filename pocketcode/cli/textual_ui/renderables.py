from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from .shared import TextualThemePalette
from .store import OutputBlock

DEFAULT_MAX_LINES = 24
DIFF_MAX_LINES = 40
YAML_MAX_LINES = 30
TEXT_PREVIEW_MAX_LINES = 20
DEFAULT_MAX_CHARS = 4000


@dataclass(frozen=True)
class CompactionResult:
    text: str
    summary: str | None
    truncated: bool


@dataclass(frozen=True)
class RenderedBlockSpan:
    block_index: int
    start_line: int
    end_line: int


def _compact_text(
    text: str,
    *,
    max_lines: int,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> CompactionResult:
    lines = str(text).splitlines()
    original_line_count = len(lines)
    truncated = False

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    compacted = "\n".join(lines)
    original_char_count = len(str(text))
    if len(compacted) > max_chars:
        compacted = compacted[: max_chars - 3].rstrip() + "..."
        truncated = True

    if not truncated:
        return CompactionResult(text=compacted, summary=None, truncated=False)

    if original_line_count > max_lines:
        return CompactionResult(
            text=compacted,
            summary=f"showing first {len(lines)} of {original_line_count} lines",
            truncated=True,
        )
    return CompactionResult(
        text=compacted,
        summary=f"showing first {len(compacted)} of {original_char_count} chars",
        truncated=True,
    )


def _subtitle_for_compaction(result: CompactionResult, *, expanded: bool, hovered: bool = False) -> str | None:
    if expanded and result.truncated:
        return "expanded view | Ctrl+E restores | Ctrl+Left/Right moves"
    if result.truncated:
        base = (
            f"{result.summary} | Ctrl+E expands | Ctrl+Left/Right moves"
            if result.summary
            else "Ctrl+E expands | Ctrl+Left/Right moves"
        )
        if hovered:
            return f"{base} | click to select"
        return base
    return None


def _block_title(title: str, *, selected: bool, hovered: bool) -> str:
    if not selected:
        if hovered:
            return f"~ {title}"
        return title
    return f"> {title}"


def _block_max_lines(block: OutputBlock) -> int:
    language = (block.language or "").lower()
    if block.kind == "tool_call":
        return TEXT_PREVIEW_MAX_LINES
    if block.kind == "tool_result" and not block.language:
        return TEXT_PREVIEW_MAX_LINES
    if block.kind != "code":
        return DEFAULT_MAX_LINES
    if language == "diff":
        return DIFF_MAX_LINES
    if language in {"yaml", "yml", "json"}:
        return YAML_MAX_LINES
    if language == "text":
        return TEXT_PREVIEW_MAX_LINES
    return DEFAULT_MAX_LINES


def _has_manual_summary(block: OutputBlock) -> bool:
    summary_text = str(block.summary_text or "").strip()
    return bool(summary_text) and summary_text != str(block.text)


def _preview_result(block: OutputBlock) -> CompactionResult:
    if _has_manual_summary(block):
        return CompactionResult(
            text=str(block.summary_text or ""),
            summary="click to expand",
            truncated=True,
        )
    return _compact_text(block.text, max_lines=_block_max_lines(block), max_chars=DEFAULT_MAX_CHARS)


def block_is_compactable(block: OutputBlock) -> bool:
    if _has_manual_summary(block):
        return True
    if block.kind == "code" and str(block.title or "").startswith("Breakpoint #"):
        return True
    if block.kind not in {"code", "tool_call", "tool_result"}:
        return False
    result = _compact_text(block.text, max_lines=_block_max_lines(block), max_chars=DEFAULT_MAX_CHARS)
    return result.truncated


def has_compactable_output_blocks(blocks: Iterable[OutputBlock]) -> bool:
    return any(block_is_compactable(block) for block in blocks)


def _make_text(text: str, style: str) -> Text:
    rendered = Text(style=style)
    rendered.append(str(text))
    return rendered


def _make_diff_renderable(
    block: OutputBlock,
    palette: TextualThemePalette,
    *,
    expanded: bool,
    selected: bool,
    hovered: bool,
) -> Panel:
    result = _preview_result(block)
    diff_source = block.text if expanded else result.text
    diff_text = Text()
    for line in diff_source.splitlines() or [""]:
        if line.startswith("+++") or line.startswith("---"):
            diff_text.append(line, style=f"bold {palette.accent}")
        elif line.startswith("@@"):
            diff_text.append(line, style=f"bold {palette.info}")
        elif line.startswith("+"):
            diff_text.append(line, style=f"bold {palette.success}")
        elif line.startswith("-"):
            diff_text.append(line, style=f"bold {palette.error}")
        else:
            diff_text.append(line, style=palette.text_primary)
        diff_text.append("\n")
    if diff_text.plain.endswith("\n"):
        diff_text = diff_text[:-1]
    return Panel(
        diff_text,
        title=_block_title(block.title or "Diff", selected=selected, hovered=hovered),
        title_align="left",
        border_style=palette.accent if selected else (palette.info if hovered else palette.info),
        subtitle=_subtitle_for_compaction(result, expanded=expanded, hovered=hovered),
        subtitle_align="right",
    )


def _make_code_renderable(
    block: OutputBlock,
    palette: TextualThemePalette,
    *,
    expanded: bool,
    selected: bool,
    hovered: bool,
) -> Panel:
    language = block.language or "text"
    if language.lower() == "diff":
        return _make_diff_renderable(block, palette, expanded=expanded, selected=selected, hovered=hovered)
    result = _preview_result(block)
    syntax = Syntax(
        block.text if expanded else result.text,
        language,
        word_wrap=True,
        line_numbers=False,
        theme="monokai",
    )
    return Panel(
        syntax,
        title=_block_title(block.title or f"Code ({language})", selected=selected, hovered=hovered),
        title_align="left",
        border_style=palette.accent if selected else (palette.info if hovered else palette.border),
        subtitle=_subtitle_for_compaction(result, expanded=expanded, hovered=hovered),
        subtitle_align="right",
    )


def render_output_block(
    block: OutputBlock,
    palette: TextualThemePalette,
    *,
    expanded: bool = False,
    selected: bool = False,
    hovered: bool = False,
) -> Text | Panel:
    title = block.title or block.kind.capitalize()
    if block.kind == "code":
        return _make_code_renderable(block, palette, expanded=expanded, selected=selected, hovered=hovered)
    if block.kind == "tool_call":
        result = _preview_result(block)
        return Panel(
            _make_text(block.text if expanded else result.text, palette.text_primary),
            title=_block_title(title, selected=selected, hovered=hovered),
            title_align="left",
            border_style=palette.accent if selected else (palette.info if hovered else palette.warning),
            subtitle=_subtitle_for_compaction(result, expanded=expanded, hovered=hovered),
            subtitle_align="right",
        )
    if block.kind == "tool_result":
        if block.language:
            return _make_code_renderable(block, palette, expanded=expanded, selected=selected, hovered=hovered)
        result = _preview_result(block)
        return Panel(
            _make_text(block.text if expanded else result.text, palette.text_primary),
            title=_block_title(title, selected=selected, hovered=hovered),
            title_align="left",
            border_style=palette.accent if selected else (palette.info if hovered else palette.success),
            subtitle=_subtitle_for_compaction(result, expanded=expanded, hovered=hovered),
            subtitle_align="right",
        )

    tone = {
        "error": palette.error,
        "warning": palette.warning,
        "runtime": palette.info,
        "info": palette.text_muted,
        "user": palette.success,
        "assistant": palette.accent,
    }.get(block.kind, palette.text_primary)
    text = Text(style=palette.text_primary)
    
    if block.kind == "user":
        text.append("You>> ", style=f"bold {tone}")
    elif block.kind == "assistant":
        text.append("Assistant>> ", style=f"bold {tone}")
    else:
        text.append(f"{title.lower()}> ", style=f"bold {tone}")
        
    text.append(block.text, style=palette.text_primary)
    return text


def render_output_blocks(
    blocks: Iterable[OutputBlock],
    palette: TextualThemePalette,
    *,
    surface_id: str,
    selected_block_index: int | None = None,
    hovered_block_index: int | None = None,
    expanded_block_refs: Iterable[str] = (),
) -> list[Text | Panel]:
    expanded_refs = set(str(item) for item in expanded_block_refs)
    rendered: list[Text | Panel] = []
    for index, block in enumerate(blocks):
        block_ref = f"{surface_id}:{index}"
        rendered.append(
            render_output_block(
                block,
                palette,
                expanded=block_ref in expanded_refs,
                selected=(selected_block_index == index and block_is_compactable(block)),
                hovered=(hovered_block_index == index and block_is_compactable(block)),
            )
        )
    return rendered


def measure_rendered_block_spans(
    renderables: Iterable[Text | Panel],
    *,
    width: int,
) -> tuple[RenderedBlockSpan, ...]:
    console = Console(width=max(1, int(width)), record=False, force_terminal=False)
    spans: list[RenderedBlockSpan] = []
    start_line = 0
    for block_index, renderable in enumerate(renderables):
        line_count = max(1, len(console.render_lines(renderable, pad=False)))
        spans.append(
            RenderedBlockSpan(
                block_index=block_index,
                start_line=start_line,
                end_line=start_line + line_count - 1,
            )
        )
        start_line += line_count
    return tuple(spans)
