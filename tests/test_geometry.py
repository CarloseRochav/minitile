from minitile.geometry import (
    Rect,
    adjacent,
    cells,
    distance_to_rect,
    halo_violation,
    halo_violation_pair,
    inside_die,
    manhattan,
    neighbors_of_rect,
    overlap_area,
    violates_halo,
)


def test_cells_3x2() -> None:
    assert cells(Rect(1, 1, 3, 2)) == {(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2)}


def test_manhattan_horizontal() -> None:
    assert manhattan(Rect(1, 1, 3, 3), Rect(10, 1, 3, 3)) == 7
    assert manhattan(Rect(10, 1, 3, 3), Rect(1, 1, 3, 3)) == 7


def test_manhattan_diagonal() -> None:
    assert manhattan(Rect(0, 0, 2, 2), Rect(5, 5, 2, 2)) == 8


def test_manhattan_overlap() -> None:
    assert manhattan(Rect(0, 0, 4, 4), Rect(2, 2, 4, 4)) == 0


def test_overlap_area() -> None:
    assert overlap_area(Rect(3, 4, 5, 6), Rect(3, 4, 5, 6)) == 30
    assert overlap_area(Rect(0, 0, 2, 2), Rect(2, 0, 2, 2)) == 0
    assert overlap_area(Rect(0, 0, 4, 4), Rect(2, 2, 4, 4)) == 4


def test_halo() -> None:
    a = Rect(0, 0, 2, 2)
    touching = Rect(2, 0, 2, 2)  # gap 0
    gap1 = Rect(3, 0, 2, 2)  # gap 1
    assert violates_halo(a, touching, 1)
    assert halo_violation(a, touching, 1) == 2
    assert not violates_halo(a, gap1, 1)
    assert halo_violation(a, gap1, 1) == 0
    assert not violates_halo(a, touching, 0)


def test_halo_pair_symmetric() -> None:
    a = Rect(0, 0, 1, 1)
    b = Rect(1, 0, 10, 10)
    assert halo_violation(a, b, 1) != halo_violation(b, a, 1)
    assert halo_violation_pair(a, b, 1) == halo_violation_pair(b, a, 1)


def test_adjacent_and_inside() -> None:
    assert adjacent(Rect(0, 0, 2, 2), Rect(2, 1, 2, 2))
    assert not adjacent(Rect(0, 0, 2, 2), Rect(2, 2, 2, 2))  # diagonal corner
    assert inside_die(Rect(0, 0, 5, 5), 5, 5)
    assert not inside_die(Rect(1, 0, 5, 5), 5, 5)


def test_distance_and_neighbors() -> None:
    r = Rect(1, 1, 2, 2)
    assert distance_to_rect((0, 0), r) == 2
    assert distance_to_rect((1, 1), r) == 0
    assert len(neighbors_of_rect(r, 10, 10)) == 8
    assert len(neighbors_of_rect(Rect(0, 0, 2, 2), 10, 10)) == 4
