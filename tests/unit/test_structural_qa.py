from __future__ import annotations

from amsc.structural_qa import (
    HIGH,
    LOW,
    MEDIUM,
    lint,
    looks_like_title,
    render,
)


def unit(unit_id, order, text, unit_type="paragraph", section=("BOLUM",), page=1,
         side="single", heading_level=None, source=None):
    payload = {"page": page, "logical_page_side": side}
    payload.update(source or {})
    return {
        "unit_id": unit_id,
        "order": order,
        "text": text,
        "type": unit_type,
        "heading_level": heading_level,
        "section_path": list(section),
        "source": payload,
    }


def heading(unit_id, order, text, section=None, **kwargs):
    return unit(
        unit_id, order, text, "heading",
        section=(text,) if section is None else section,
        heading_level=2, **kwargs,
    )


def chunk(chunk_id, text, heading_text=None, paths=(("BOLUM",),), pages=(1,)):
    return {
        "chunk_id": chunk_id,
        "text": text,
        "heading": heading_text,
        "section_paths": [list(p) for p in paths],
        "pages": list(pages),
        "unit_ids": [],
        "token_count": 0,
    }


def rules_of(findings, rule):
    return [f for f in findings if f.rule == rule]


# --------------------------------------------------------------------- title


def test_a_numbered_caps_line_is_a_title():
    assert looks_like_title("7. ILISKILI TARAFLAR") == ("numbered", "7. ILISKILI TARAFLAR")
    assert looks_like_title("**9. MADDI DURAN VARLIKLAR**")[0] == "numbered"


def test_an_all_caps_line_is_a_title():
    assert looks_like_title("KREDILER ANALIZ PORTALI") == ("caps", "KREDILER ANALIZ PORTALI")


def test_prose_and_markup_are_not_titles():
    assert looks_like_title("Bu bir cumledir ve baslik degildir.") is None
    assert looks_like_title("||<br>T.C. ZIRAAT BANKASI A.S.|") is None
    assert looks_like_title("|---|---|") is None
    assert looks_like_title("") is None
    assert looks_like_title(" ".join(["KELIME"] * 20)) is None


# --------------------------------------------------------------- body_heading


def test_a_numbered_title_stuck_in_a_paragraph_is_high():
    units = [
        heading("h-1", 1, "DIPNOTLAR"),
        unit("p-1", 2, "7. ILISKILI TARAFLAR\n\nAciklama metni.", section=("DIPNOTLAR",)),
    ]
    findings = rules_of(lint(units, []).findings, "body_heading")
    assert [f.confidence for f in findings] == [HIGH]
    assert findings[0].target_id == "p-1"
    assert findings[0].evidence == "7. ILISKILI TARAFLAR"


def test_a_title_the_section_already_knows_is_not_flagged():
    units = [
        heading("h-1", 1, "7. ILISKILI TARAFLAR"),
        unit("p-1", 2, "7. ILISKILI TARAFLAR\n\nAciklama.", section=("7. ILISKILI TARAFLAR",)),
    ]
    assert rules_of(lint(units, []).findings, "body_heading") == []


def test_a_table_row_carrying_one_value_is_not_a_body_heading():
    table = "|A|B|\n|---|---|\n|<br>T.C. ZIRAAT BANKASI A.S.||"
    units = [unit("t-1", 1, table, "table")]
    assert rules_of(lint(units, []).findings, "body_heading") == []


# ------------------------------------------------- chunk_heading_mismatch


def test_a_chunk_body_carrying_a_foreign_title_is_flagged():
    rows = [
        chunk(
            "c-1",
            "8. STOKLAR\n\nGovde.\n\n9. MADDI DURAN VARLIKLAR\n\nDevam.",
            heading_text="8. STOKLAR",
            paths=(("8. STOKLAR",),),
        )
    ]
    findings = rules_of(lint([], rows).findings, "chunk_heading_mismatch")
    assert [f.evidence for f in findings] == ["9. MADDI DURAN VARLIKLAR"]
    assert findings[0].confidence == HIGH


def test_a_chunk_whose_body_only_repeats_its_own_heading_is_clean():
    rows = [
        chunk("c-1", "8. STOKLAR\n\nGovde metni.", heading_text="8. STOKLAR",
              paths=(("8. STOKLAR",),))
    ]
    assert rules_of(lint([], rows).findings, "chunk_heading_mismatch") == []


def test_table_rows_inside_a_chunk_are_not_foreign_titles():
    rows = [
        chunk("c-1", "UYELER\n\n|A|B|\n|---|---|\n|ZIRAAT BANKASI A.S.||",
              heading_text="UYELER", paths=(("UYELER",),))
    ]
    assert rules_of(lint([], rows).findings, "chunk_heading_mismatch") == []


# ------------------------------------------------- sentence_like_heading


def test_a_clause_final_heading_is_high():
    findings = rules_of(lint([heading("h-1", 1, "Uygulamayla;")], []).findings,
                        "sentence_like_heading")
    assert [f.confidence for f in findings] == [HIGH]


def test_section_numbering_without_a_title_is_high():
    findings = rules_of(lint([heading("h-1", 1, "24.")], []).findings,
                        "sentence_like_heading")
    assert [(f.confidence, f.reason) for f in findings] == [
        (HIGH, "section numbering with no title text")
    ]


def test_a_bare_year_is_only_worth_a_low_note():
    findings = rules_of(lint([heading("h-1", 1, "2024")], []).findings,
                        "sentence_like_heading")
    assert [f.confidence for f in findings] == [LOW]


def test_an_abbreviation_is_not_a_sentence():
    findings = rules_of(lint([heading("h-1", 1, "T. Garanti Bankasi A.S.")], []).findings,
                        "sentence_like_heading")
    assert [f.confidence for f in findings] == []


def test_a_rhetorical_title_is_medium_not_high():
    findings = rules_of(lint([heading("h-1", 1, "BIZ KIMIZ?")], []).findings,
                        "sentence_like_heading")
    assert [f.confidence for f in findings] == [MEDIUM]


def test_a_colon_heading_is_low():
    findings = rules_of(lint([heading("h-1", 1, "**b) Likidite riski:**")], []).findings,
                        "sentence_like_heading")
    assert LOW in {f.confidence for f in findings}


def test_a_truncated_lowercase_heading_is_medium():
    findings = rules_of(lint([heading("h-1", 1, "liyoruz")], []).findings,
                        "sentence_like_heading")
    assert [f.reason for f in findings] == ["starts lowercase"]


# ------------------------------------------------- section_inconsistency


def test_a_section_change_without_a_heading_is_high():
    units = [
        unit("p-1", 1, "birinci", section=("A",)),
        unit("p-2", 2, "ikinci", section=("B",)),
    ]
    findings = rules_of(lint(units, []).findings, "section_inconsistency")
    assert [f.target_id for f in findings] == ["p-2"]
    assert findings[0].confidence == HIGH


def test_a_heading_that_is_not_its_own_section_tail_is_high():
    units = [heading("h-1", 1, "BOLUM B", section=("BOLUM A",))]
    findings = rules_of(lint(units, []).findings, "section_inconsistency")
    assert [f.target_id for f in findings] == ["h-1"]


def test_a_chunk_spanning_two_sections_is_medium():
    rows = [chunk("c-1", "metin", heading_text="A", paths=(("A",), ("B",)))]
    findings = rules_of(lint([], rows).findings, "section_inconsistency")
    assert [f.confidence for f in findings] == [MEDIUM]


def test_a_consistent_stream_produces_nothing():
    units = [
        heading("h-1", 1, "BOLUM A"),
        unit("p-1", 2, "govde", section=("BOLUM A",)),
        heading("h-2", 3, "BOLUM B"),
        unit("p-2", 4, "govde", section=("BOLUM B",)),
    ]
    assert rules_of(lint(units, []).findings, "section_inconsistency") == []


# --------------------------------------- section_inconsistency and roles


def label(unit_id, order, text, section, **kwargs):
    """A heading the role pass said does not bear hierarchy."""
    row = heading(unit_id, order, text, section=section, **kwargs)
    row["semantic_role"] = "item"
    row["opens_section"] = False
    return row


def test_a_label_is_not_required_to_be_its_own_section_tail():
    """The whole point of the role model: an item title opens nothing."""
    units = [
        heading("h-1", 1, "5. ODULLER"),
        label("h-2", 2, "Bir odul", section=("5. ODULLER",)),
        unit("p-1", 3, "aciklama", section=("5. ODULLER",)),
    ]

    assert rules_of(lint(units, []).findings, "section_inconsistency") == []


def test_a_label_that_moved_the_section_path_is_still_high():
    """It may not be on the stack, but it may not change the stack either."""
    units = [
        heading("h-1", 1, "5. ODULLER"),
        label("h-2", 2, "Bir odul", section=("BASKA BOLUM",)),
    ]

    findings = rules_of(lint(units, []).findings, "section_inconsistency")

    assert [f.target_id for f in findings] == ["h-2"]
    assert findings[0].confidence == HIGH


def test_a_body_unit_that_moved_the_path_after_a_label_is_caught():
    """Previously invisible: the label counted as a heading and excused it."""
    units = [
        heading("h-1", 1, "5. ODULLER"),
        label("h-2", 2, "Bir odul", section=("5. ODULLER",)),
        unit("p-1", 3, "aciklama", section=("BASKA BOLUM",)),
    ]

    findings = rules_of(lint(units, []).findings, "section_inconsistency")

    assert [f.target_id for f in findings] == ["p-1"]


def test_a_heading_that_does_open_a_section_still_has_to_be_its_own_tail():
    units = [heading("h-1", 1, "BOLUM B", section=("BOLUM A",))]
    units[0]["semantic_role"] = "section"
    units[0]["opens_section"] = True

    findings = rules_of(lint(units, []).findings, "section_inconsistency")

    assert [f.target_id for f in findings] == ["h-1"]


def test_a_label_opening_the_corpus_with_a_path_out_of_nowhere_is_caught():
    """Nothing is open at the first unit, so any path it carries came from nowhere."""
    units = [label("h-1", 1, "Bir etiket", section=("HAYALET BOLUM",))]

    findings = rules_of(lint(units, []).findings, "section_inconsistency")

    assert [f.target_id for f in findings] == ["h-1"]


def test_the_first_unit_of_a_normal_corpus_carries_no_finding():
    units = [unit("p-1", 1, "kapak metni", section=())]

    assert rules_of(lint(units, []).findings, "section_inconsistency") == []


def test_a_corpus_carrying_no_role_decision_is_judged_exactly_as_before():
    """An older canonical must produce byte-identical findings."""
    units = [
        heading("h-1", 1, "BOLUM A"),
        heading("h-2", 2, "Bir etiket", section=("BOLUM A",)),
        unit("p-1", 3, "govde", section=("BOLUM A",)),
    ]

    findings = rules_of(lint(units, []).findings, "section_inconsistency")

    # h-2 carries no role, so it is read as opening a section and is flagged
    # for not being its own tail -- the pre-role verdict, unchanged.
    assert [f.target_id for f in findings] == ["h-2"]


# ------------------------------------------------------- running_header


def test_a_heading_leading_three_pages_is_high():
    units = []
    order = 0
    for page in (4, 5, 6):
        order += 1
        units.append(heading(f"h-{order}", order, "BANNER", page=page))
        order += 1
        units.append(unit(f"p-{order}", order, "govde", section=("BANNER",), page=page))
    findings = rules_of(lint(units, []).findings, "running_header")
    assert [f.confidence for f in findings] == [HIGH]
    assert "3 distinct physical pages" in findings[0].reason


def test_a_heading_leading_two_pages_is_not_furniture():
    units = []
    order = 0
    for page in (4, 5):
        order += 1
        units.append(heading(f"h-{order}", order, "BANNER", page=page))
        order += 1
        units.append(unit(f"p-{order}", order, "govde", section=("BANNER",), page=page))
    assert rules_of(lint(units, []).findings, "running_header") == []


def test_a_repeated_heading_that_never_leads_a_page_is_medium():
    units = []
    order = 0
    for page in (4, 5, 6):
        order += 1
        units.append(unit(f"p-{order}", order, "govde", page=page))
        order += 1
        units.append(heading(f"h-{order}", order, "TEKRAR", page=page))
    findings = rules_of(lint(units, []).findings, "running_header")
    assert [f.confidence for f in findings] == [MEDIUM]


# ----------------------------------------------------- unresolved_visual


def visual(unit_id, order, text, method="layout_text", page=1, side="single",
           section=("BOLUM",)):
    return unit(
        unit_id, order, text, section=section, page=page, side=side,
        source={"content_origin": "visual", "extraction_method": method},
    )


def test_an_unpaired_label_value_grid_is_high():
    text = "ETIKET BIR ETIKET IKI\n1.000\n2.000\nETIKET UC\n3.000"
    findings = rules_of(lint([visual("v-1", 1, text)], []).findings, "unresolved_visual")
    assert findings and findings[0].confidence == HIGH


def test_a_reconstructed_grid_is_not_flagged():
    text = "ETIKET BIR | 1.000\nETIKET IKI | 2.000"
    findings = [
        f
        for f in rules_of(
            lint([visual("v-1", 1, text, method="layout_text_card_grid")], []).findings,
            "unresolved_visual",
        )
        if "pairing" in f.reason
    ]
    assert findings == []


def test_a_visual_inheriting_a_heading_from_the_other_half_is_medium():
    units = [
        heading("h-1", 1, "BOLUM", page=7, side="left"),
        visual("v-1", 2, "gorsel", page=7, side="right", section=("BOLUM",)),
    ]
    findings = [
        f
        for f in rules_of(lint(units, []).findings, "unresolved_visual")
        if "another logical page" in f.reason
    ]
    assert [f.confidence for f in findings] == [MEDIUM]


# ------------------------------------------------------------------ report


def test_the_report_is_deterministic_and_renders():
    units = [heading("h-1", 1, "Uygulamayla;"), heading("h-2", 2, "24.")]
    first = lint(units, [])
    second = lint(units, [])
    assert [f.sort_key() for f in first.findings] == [
        f.sort_key() for f in second.findings
    ]
    text = render(first)
    assert "Structural QA: 2 canonical units, 0 chunks" in text
    assert "=== HIGH" in text


def test_an_empty_corpus_produces_no_findings():
    report = lint([], [])
    assert report.findings == []
    assert "0 canonical units, 0 chunks, 0 findings" in render(report)
