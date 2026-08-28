"""Deterministic boundary quality, held to its contract.

Every predicate is shape-based (typography, punctuation, orthography, unit
type/role, adjacency); no lexicon. Smells attach to sections; the comparison
rule is a per-type ``<=``; change groups are spans between cuts common to
both partitions; nothing here reads a clock or a random source.
"""

from __future__ import annotations

import json

import pytest

from amsc.boundary_quality import (
    QualityConfig,
    VECTOR_KEYS,
    VERDICT_BETTER,
    VERDICT_TIE,
    VERDICT_WORSE,
    boundary_smells,
    change_groups,
    compare,
    compare_vectors,
    continues_previous,
    is_label_like,
    is_lead_in,
    list_runs,
    main,
    measure,
    partition_from_rows,
)
from amsc.models import RawDocumentUnit, SemanticRole, UnitType

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()
CONFIG = QualityConfig(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)


def paragraph(unit_id, text, order=0, section=("S",)):
    return unit(unit_id, text, order=order, section=section)


def label_heading(unit_id, text, order, role=SemanticRole.ITEM):
    return RawDocumentUnit(
        document_id="doc",
        unit_id=unit_id,
        order=order,
        text=text,
        type=UnitType.HEADING,
        heading_level=3,
        semantic_role=role,
        opens_section=False,
        section_path=["S"],
    )


# --- shape predicates ---------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("**Kiralamalar (devamı)**", True),
        ("_**Finansal araçların sınıflandırılması ve ölçümü**_", True),
        ("**a) Pazarlama, satış ve dağıtım giderleri:**", True),
        ("**Bu bir cümledir.**", False),
        ("**30**", False),
        ("**==> picture [335 x 87] intentionally omitted <==**", False),
        ("**" + words(13, "w") + "**", False),
        ("**Bold start** and a plain tail", False),
        # Three shapes, not one. Emphasis was the original rule; capitals and
        # title case were added after blind labelling found chunks ending on
        # unemphasised printed titles -- "Kiralamalar (devamı)" among them,
        # which this table used to assert was *not* a label.
        ("Kiralamalar (devamı)", True),
        ("_Genel Müdür Yardımcısı_", True),
        ("ÜRÜN DİZAYN VE YÖNETİMİ BİRİMİ", True),
        ("Ar-Ge Merkezi Yazılım Geliştirme Birimi", True),
        # ... and the guards that keep those two rules narrow.
        ("5.880.692 FİNDEKS BİREYSEL ÜYE", False),  # digits: a statistic panel
        ("HİZMETİ", False),  # one word: a split heading fragment
        ("Bu cümle başlık değildir", False),  # not title-cased
        ("Şirket bu tutarı gider olarak muhasebeleştirmektedir.", False),
    ],
)
def test_a_paragraph_is_label_like_on_shape_alone(text, expected):
    assert is_label_like(paragraph("p-1", text)) is expected


def test_headings_are_labels_by_role_and_display_is_excluded():
    assert is_label_like(label_heading("h-1", "Stratejik Projeler", 1)) is True
    assert is_label_like(label_heading("h-2", "Bir slogan", 2, role=SemanticRole.DISPLAY)) is False
    assert is_label_like(heading("h-3", "BOLUM", 3)) is False  # opens a section


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Detayı aşağıdaki gibidir:", True),
        ("**Verilen teminat mektupları:**", True),
        ("Detayı aşağıdaki gibidir.", False),
    ],
)
def test_lead_in_is_a_trailing_colon(text, expected):
    assert is_lead_in(paragraph("p-1", text)) is expected
    assert is_lead_in(heading("h-1", text, 1)) is False


@pytest.mark.parametrize(
    "text, expected",
    [
        ("maliyet öngörüleri ve kaynakların eşleşmesi hedeflenmektedir.", True),
        ("ışık ve gölge", True),
        ("(*) Şirket'in vadesi geçmiş alacağı yoktur.", True),
        ("(1) Dipnot metni.", True),
        ("Bu değerlendirme kapsamında anapara tanımlanır.", False),
        ("ii. Şirket'in kullanım hakkı", False),
        ("a) Kredi riski", False),
        ("- düzeltme gerektirmeyen kur", False),
        ("“bir alıntı ile başlayan” cümle", True),
        ("2024 yılında", False),
    ],
)
def test_continuation_reads_footnotes_and_lower_case_starts_only(text, expected):
    assert continues_previous(paragraph("p-1", text)) is expected


def test_list_items_and_tables_never_read_as_continuations():
    assert continues_previous(unit("l-1", "düzeltme", order=1, type=UnitType.LIST)) is False
    assert continues_previous(unit("t-1", "|a|b|\n|---|---|\n|c|d|", order=1, type=UnitType.TABLE)) is False


# --- boundary smells ----------------------------------------------------------


def test_each_smell_fires_on_its_own_shape():
    label = paragraph("p-1", "**UFRS Yıllık İyileştirmeler (devamı)**")
    lead = paragraph("p-2", "Detayı aşağıdaki gibidir:")
    body = paragraph("p-3", "Bu bir gövde paragrafıdır.")
    cont = paragraph("p-4", "ve devam eden bir cümle.")
    assert boundary_smells(label, body, left_raw_id="p-1", right_raw_id="p-3") == ["orphan_label"]
    assert boundary_smells(lead, body, left_raw_id="p-2", right_raw_id="p-3") == ["lead_in_cut"]
    assert boundary_smells(body, cont, left_raw_id="p-3", right_raw_id="p-4") == ["continuation_cut"]
    assert boundary_smells(body, body, left_raw_id="p-3", right_raw_id="p-3b") == []


def test_a_fragmented_unit_is_one_smell_and_nothing_else():
    table = unit("t-1", "|a|\n|---|\n|b|", order=1, type=UnitType.TABLE)
    para = paragraph("p-1", "Uzun bir paragraf ve devamı.")
    assert boundary_smells(table, table, left_raw_id="t-1#f1", right_raw_id="t-1#f2") == ["table_split"]
    assert boundary_smells(para, para, left_raw_id="p-1#f1", right_raw_id="p-1#f2") == ["fragment_cut"]


def test_a_display_heading_at_a_tail_is_not_an_orphan():
    banner = label_heading("h-9", "Gururla dolu bir yolculuk", 9, role=SemanticRole.DISPLAY)
    body = paragraph("p-3", "Gövde.")
    assert boundary_smells(banner, body, left_raw_id="h-9", right_raw_id="p-3") == []


# --- list runs ---------------------------------------------------------------


def test_list_runs_follow_adjacency_and_section_path():
    units = [
        unit("l-1", "- a", order=1, type=UnitType.LIST, section=("S",)),
        unit("l-2", "- b", order=2, type=UnitType.LIST, section=("S",)),
        paragraph("p-1", "Ara.", order=3),
        unit("l-3", "- c", order=4, type=UnitType.LIST, section=("S",)),
        unit("l-4", "- d", order=5, type=UnitType.LIST, section=("T",)),
        unit("l-5", "- e", order=6, type=UnitType.LIST, section=("T",)),
    ]
    assert list_runs(units) == [("l-1", "l-2"), ("l-4", "l-5")]


# --- partitions and vectors --------------------------------------------------


def corpus():
    return [
        heading("h-1", "BOLUM", 1),
        paragraph("p-1", words(60, "A"), order=2, section=("BOLUM",)),
        paragraph("p-2", "Şunları içerebilir:", order=3, section=("BOLUM",)),
        unit("l-1", "- birinci madde", order=4, type=UnitType.LIST, section=("BOLUM",)),
        unit("l-2", "- ikinci madde", order=5, type=UnitType.LIST, section=("BOLUM",)),
        paragraph("p-3", words(60, "B"), order=6, section=("BOLUM",)),
        paragraph("p-4", words(60, "C"), order=7, section=("BOLUM",)),
    ]


def row(chunk_id, unit_ids, tokens, heading_text="BOLUM"):
    return {
        "chunk_id": chunk_id,
        "heading": heading_text,
        "section_paths": [[heading_text]],
        "unit_ids": list(unit_ids),
        "token_count": tokens,
        "text": "x",
    }


def test_measure_counts_smells_sizes_and_split_runs_per_section():
    rows = [
        row("c1", ["p-1", "p-2"], 70),  # lead-in tail
        row("c2", ["l-1"], 3),  # run split, below min
        row("c3", ["l-2", "p-3"], 70),
        row("c4", ["p-4"], 200),  # above soft max
    ]
    report = measure(corpus(), rows, counter=COUNTER, config=CONFIG)
    assert report["section_count"] == 1
    assert report["internal_boundary_count"] == 3
    assert report["totals"] == {
        "orphan_label": 0,
        "lead_in_cut": 1,
        "fragment_cut": 0,
        "table_split": 0,
        "run_split_when_fits": 1,
        "continuation_cut": 0,
        "below_min": 1,
        "above_soft_max": 1,
    }
    section = report["sections"][0]
    assert section["split_runs_when_fit"] == [["l-1", "l-2"]]
    assert section["boundaries"][0]["smells"] == ["lead_in_cut"]


def test_a_run_that_cannot_fit_one_block_is_not_a_smell():
    units = corpus()
    units[3] = unit("l-1", words(120, "l"), order=4, type=UnitType.LIST, section=("BOLUM",))
    units[4] = unit("l-2", words(120, "m"), order=5, type=UnitType.LIST, section=("BOLUM",))
    rows = [row("c1", ["p-1", "p-2", "l-1"], 130), row("c2", ["l-2", "p-3", "p-4"], 130)]
    report = measure(units, rows, counter=COUNTER, config=CONFIG)
    assert report["totals"]["run_split_when_fits"] == 0


def test_partition_groups_consecutive_rows_and_numbers_repeated_keys():
    rows = [row("a", ["p-1"], 10, "X"), row("b", ["p-2"], 10, "X"), row("c", ["p-3"], 10, "Y"), row("d", ["p-4"], 10, "X")]
    sections = partition_from_rows(rows)
    assert [(s.key[0], s.occurrence, len(s.blocks)) for s in sections] == [("X", 0, 2), ("Y", 0, 1), ("X", 1, 1)]
    assert sections[0].cuts == (1,)
    assert sections[0].unit_ids == ("p-1", "p-2")


def test_fragment_qualified_ids_are_preferred_when_present():
    rows = [{**row("a", ["t-1"], 10), "fragment_unit_ids": ["t-1#f1"]}, {**row("b", ["t-1"], 10), "fragment_unit_ids": ["t-1#f2"]}]
    sections = partition_from_rows(rows)
    assert sections[0].unit_ids == ("t-1#f1", "t-1#f2")


def test_a_row_without_token_count_is_counted_from_text_or_refused():
    rows = [{"chunk_id": "a", "heading": "X", "section_paths": [["X"]], "unit_ids": ["p-1"], "text": words(7)}]
    assert partition_from_rows(rows, COUNTER)[0].blocks[0].token_count == 7
    with pytest.raises(ValueError):
        partition_from_rows([{"chunk_id": "a", "unit_ids": ["p-1"]}])


# --- the comparison rule -----------------------------------------------------


def vector(**overrides):
    base = {key: 0 for key in VECTOR_KEYS}
    base.update(overrides)
    return base


def test_compare_vectors_is_a_per_type_subset_rule():
    standard = vector(orphan_label=1, lead_in_cut=1)
    assert compare_vectors(standard, vector(orphan_label=1, lead_in_cut=1)) == VERDICT_TIE
    assert compare_vectors(standard, vector(orphan_label=1)) == VERDICT_BETTER
    assert compare_vectors(standard, vector(orphan_label=0, continuation_cut=1)) == VERDICT_WORSE
    # fewer in total but one type grew: still worse
    assert compare_vectors(vector(orphan_label=3), vector(lead_in_cut=1)) == VERDICT_WORSE
    assert compare_vectors(vector(), vector(below_min=1)) == VERDICT_WORSE


# --- change groups -----------------------------------------------------------


def test_change_groups_are_spans_between_common_cuts():
    standard = partition_from_rows([row("s1", ["p-1", "p-2"], 10), row("s2", ["p-3", "p-4"], 10), row("s3", ["p-5", "p-6"], 10)])[0]
    deep = partition_from_rows([row("d1", ["p-1"], 10), row("d2", ["p-2", "p-3", "p-4"], 10), row("d3", ["p-5"], 10), row("d4", ["p-6"], 10)])[0]
    groups = change_groups(standard, deep)
    assert groups == [
        {
            "start_index": 0,
            "end_index": 4,
            "unit_ids": ["p-1", "p-2", "p-3", "p-4"],
            "standard_cuts_after": ["p-2"],
            "deep_cuts_after": ["p-1"],
        },
        {
            "start_index": 4,
            "end_index": 6,
            "unit_ids": ["p-5", "p-6"],
            "standard_cuts_after": [],
            "deep_cuts_after": ["p-5"],
        },
    ]


def test_identical_partitions_have_no_change_groups():
    section = partition_from_rows([row("a", ["p-1", "p-2"], 10), row("b", ["p-3"], 10)])[0]
    assert change_groups(section, section) == []


def test_change_groups_refuse_different_unit_sequences():
    a = partition_from_rows([row("a", ["p-1", "p-2"], 10)])[0]
    b = partition_from_rows([row("b", ["p-1", "p-9"], 10)])[0]
    with pytest.raises(ValueError):
        change_groups(a, b)


# --- compare -----------------------------------------------------------------


def test_compare_reports_verdicts_regressions_and_groups():
    units = corpus()
    standard = [row("s1", ["p-1", "p-2"], 70), row("s2", ["l-1", "l-2", "p-3"], 70), row("s3", ["p-4"], 60)]
    better = [row("d1", ["p-1"], 60), row("d2", ["p-2", "l-1", "l-2", "p-3"], 80), row("d3", ["p-4"], 60)]
    worse = [row("d1", ["p-1", "p-2"], 70), row("d2", ["l-1"], 3), row("d3", ["l-2", "p-3", "p-4"], 130)]

    report = compare(units, standard, better, counter=COUNTER, config=CONFIG)
    assert report["verdicts"] == {VERDICT_BETTER: 1, VERDICT_TIE: 0, VERDICT_WORSE: 0}
    assert report["structural_regression_count"] == 0
    assert report["change_group_count"] == 1
    assert report["totals"]["standard"]["lead_in_cut"] == 1
    assert report["totals"]["deep"]["lead_in_cut"] == 0

    report = compare(units, standard, worse, counter=COUNTER, config=CONFIG)
    assert report["verdicts"][VERDICT_WORSE] == 1
    assert report["regressions"][0]["deep"]["vector"]["run_split_when_fits"] == 1
    assert report["regressions"][0]["deep"]["vector"]["below_min"] == 1

    report = compare(units, standard, standard, counter=COUNTER, config=CONFIG)
    assert report["verdicts"] == {VERDICT_BETTER: 0, VERDICT_TIE: 1, VERDICT_WORSE: 0}
    assert report["sections_with_differences"] == []


def test_compare_refuses_partitions_of_different_section_sequences():
    units = corpus()
    standard = [row("s1", ["p-1", "p-2"], 70), row("s2", ["l-1", "l-2", "p-3", "p-4"], 70)]
    other = [row("o1", ["p-1", "p-2"], 70, "OTHER"), row("o2", ["l-1", "l-2", "p-3", "p-4"], 70, "OTHER")]
    with pytest.raises(ValueError):
        compare(units, standard, other, counter=COUNTER, config=CONFIG)


def test_measure_is_deterministic():
    rows = [row("c1", ["p-1", "p-2"], 70), row("c2", ["l-1"], 3), row("c3", ["l-2", "p-3", "p-4"], 70)]
    first = json.dumps(measure(corpus(), rows, counter=COUNTER, config=CONFIG), sort_keys=True)
    second = json.dumps(measure(corpus(), rows, counter=COUNTER, config=CONFIG), sort_keys=True)
    assert first == second


# --- CLI ---------------------------------------------------------------------


def test_cli_writes_a_report_and_refuses_evaluation(tmp_path, capsys):
    units_path = tmp_path / "doc.units.jsonl"
    with units_path.open("w", encoding="utf-8") as handle:
        for item in corpus():
            handle.write(item.model_dump_json(exclude_none=True) + "\n")
    chunks = tmp_path / "chunks.jsonl"
    standard = tmp_path / "standard.jsonl"
    chunks.write_text(
        "\n".join(json.dumps(r) for r in [row("d1", ["p-1"], 60), row("d2", ["p-2", "l-1", "l-2", "p-3"], 80), row("d3", ["p-4"], 60)]) + "\n",
        encoding="utf-8",
    )
    standard.write_text(
        "\n".join(json.dumps(r) for r in [row("s1", ["p-1", "p-2"], 70), row("s2", ["l-1", "l-2", "p-3"], 70), row("s3", ["p-4"], 60)]) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "out" / "report.json"
    main(
        [
            "--units", str(units_path), "--chunks", str(chunks), "--against", str(standard),
            "--output", str(output), "--min-tokens", "50", "--target-tokens", "150",
            "--soft-max-tokens", "160", "--hard-max-tokens", "1000",
        ]
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["compare"]["verdicts"][VERDICT_BETTER] == 1
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["change_group_count"] == 1

    with pytest.raises(ValueError):
        main(["--units", str(units_path), "--chunks", str(chunks), "--output", str(tmp_path / "evaluation" / "x.json")])
