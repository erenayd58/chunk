from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from amsc.checkpoint_adapter import PyMuPDF4LLMExtractor, load_layout_backend


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pymupdf.layout") is None,
    reason='checkpoint extra is not installed; use pip install -e ".[checkpoint]"',
)


def test_real_checkpoint_layout_dependency_is_active(tmp_path: Path) -> None:
    backend = load_layout_backend()
    assert backend.pymupdf4llm.__version__ == "0.3.4"
    assert backend.pymupdf._get_layout is not None
    assert hasattr(backend.pymupdf4llm, "document_layout")
    assert not hasattr(backend.pymupdf4llm, "IdentifyHeaders")

    source = tmp_path / "layout-smoke.pdf"
    document = backend.pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Checkpoint Heading", fontsize=20)
    page.insert_text((72, 110), "Checkpoint paragraph content.", fontsize=11)
    document.save(str(source))
    document.close()

    result = PyMuPDF4LLMExtractor(lambda: backend).extract(source, pages="1")
    assert result.selected_pages == (1,)
    assert len(result.pages) == 1
    assert "Checkpoint" in result.pages[0].markdown


def test_real_layout_extraction_splits_landscape_spread_left_then_right(
    tmp_path: Path,
) -> None:
    backend = load_layout_backend()
    source = tmp_path / "landscape-spread.pdf"
    document = backend.pymupdf.open()
    page = document.new_page(width=900, height=600)
    page.insert_textbox(
        backend.pymupdf.Rect(72, 160, 390, 360),
        "Left logical page. This paragraph contains enough text for layout "
        "classification and remains entirely inside the left half.",
        fontsize=12,
    )
    page.insert_textbox(
        backend.pymupdf.Rect(540, 160, 850, 360),
        "Right logical page. This paragraph contains enough text for layout "
        "classification and remains entirely inside the right half.",
        fontsize=12,
    )
    document.save(str(source))
    document.close()

    result = PyMuPDF4LLMExtractor(lambda: backend).extract(source, pages="1")

    assert result.selected_pages == (1,)
    assert [page.logical_page_side for page in result.pages] == ["left", "right"]
    assert "Left logical page" in result.pages[0].markdown
    assert "Right logical page" in result.pages[1].markdown
    assert all(page.page == 1 for page in result.pages)
