from amsc.pairwise_chunker import partition_pairwise

from _chunk_fixtures import heading, unit, words


BUDGET = {
    "min_tokens": 50,
    "target_tokens": 150,
    "soft_max_tokens": 160,
    "hard_max_tokens": 1000,
}


class Counter:
    counter_id = "test:whitespace@1"

    def count(self, text: str) -> int:
        return len(text.split())


COUNTER = Counter()


def test_pairwise_groups_consecutive_units_in_twos():
    units = [
        heading("h-1", "A", 1),
        unit("p-1", words(10, "a1"), order=2, section=("A",)),
        unit("p-2", words(10, "a2"), order=3, section=("A",)),
        unit("p-3", words(10, "a3"), order=4, section=("A",)),
        unit("p-4", words(10, "a4"), order=5, section=("A",)),
        unit("p-5", words(10, "a5"), order=6, section=("A",)),
    ]

    result = partition_pairwise(
        units,
        counter=COUNTER,
        budget=BUDGET,
    )

    assert [row["unit_ids"] for row in result.rows] == [
        ["p-1", "p-2"],
        ["p-3", "p-4"],
        ["p-5"],
    ]

    assert result.rows[0]["chunk_id"] == "doc:pairwise-0001"
    assert result.rows[0]["token_count"] == 20
    assert result.rows[0]["section_paths"] == [["A"]]
    assert result.diagnostics == {"pair_size": 2}


def test_pairwise_never_crosses_a_heading():
    units = [
        heading("h-1", "A", 1),
        unit("p-1", words(10, "a1"), order=2, section=("A",)),
        heading("h-2", "B", 3),
        unit("p-2", words(10, "b1"), order=4, section=("B",)),
        unit("p-3", words(10, "b2"), order=5, section=("B",)),
    ]

    result = partition_pairwise(
        units,
        counter=COUNTER,
        budget=BUDGET,
    )

    assert [row["unit_ids"] for row in result.rows] == [
        ["p-1"],
        ["p-2", "p-3"],
    ]