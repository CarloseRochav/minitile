from pathlib import Path

import pytest

from minitile.parser import DesignError, load_design, parse_design

TESTCASES = Path(__file__).parent.parent / "testcases"

SPEC_EXAMPLE = """
die:
  width: 40
  height: 40
  halo: 1
reach_per_cycle: 12
modules:
  - { name: cpu,   w: 8,  h: 8, fixed: [2, 2] }
  - { name: gpu,   w: 10, h: 8 }
  - { name: dsp,   w: 6,  h: 6 }
  - { name: modem, w: 8,  h: 6 }
  - { name: noc,   w: 4,  h: 4 }
nets:
  - { from: cpu, to: noc,   width: 128 }
  - { from: gpu, to: noc,   width: 256 }
  - { from: dsp, to: modem, width: 64 }
  - { from: noc, to: modem, width: 64 }
"""


def make(modules: str, nets: str = "[]", die: str = "{ width: 20, height: 20 }") -> str:
    return f"die: {die}\nreach_per_cycle: 12\nmodules: {modules}\nnets: {nets}\n"


def errors_of(text: str) -> list[str]:
    with pytest.raises(DesignError) as info:
        parse_design(text)
    return info.value.errors


def test_spec_example_parses() -> None:
    d = parse_design(SPEC_EXAMPLE)
    assert len(d.modules) == 5
    assert d.die.halo == 1
    assert d.module("cpu").fixed == (2, 2)
    assert d.nets[1].src == "gpu" and d.nets[1].width == 256


def test_halo_default() -> None:
    d = parse_design(make("[{ name: a, w: 1, h: 1 }]"))
    assert d.die.halo == 1


@pytest.mark.parametrize(
    "text, needle",
    [
        (make("[{ name: a, h: 1 }]"), "w"),  # missing field
        (make("[{ name: a, w: 2.5, h: 1 }]"), "integer"),  # non-int
        (make('[{ name: a, w: "3", h: 1 }]'), "integer"),  # string
        (make("[{ name: a, w: 0, h: 1 }]"), "greater than 0"),
        (make("[]", die="{ width: -1, height: 5 }"), "greater than 0"),
        (make("[]", die="{ width: 5, height: 5, halo: -1 }"), "greater than or equal to 0"),
        (make("[{ name: a, w: 1, h: 1 }, { name: b, w: 1, h: 1 }]", "[{from: a, to: b}]"), "width"),
        (
            make(
                "[{ name: a, w: 1, h: 1 }, { name: b, w: 1, h: 1 }]",
                "[{from: a, to: b, width: 0}]",
            ),
            "greater than 0",
        ),
        ("die: { width: 5, height: 5 }\nreach_per_cycle: 0\nmodules: []\nnets: []\n", "reach"),
    ],
)
def test_rule1_schema(text: str, needle: str) -> None:
    errs = errors_of(text)
    assert any(needle in e for e in errs), errs


def test_rule2_duplicate_names() -> None:
    errs = errors_of(make("[{ name: a, w: 1, h: 1 }, { name: a, w: 2, h: 2 }]"))
    assert errs == ["module 'a': duplicate module name"]


def test_rule3_module_larger_than_die() -> None:
    errs = errors_of(make("[{ name: big, w: 21, h: 1 }]"))
    assert len(errs) == 1 and "big" in errs[0] and "larger than die" in errs[0]


def test_rule4_fixed_outside_die() -> None:
    errs = errors_of(make("[{ name: a, w: 4, h: 4, fixed: [18, 0] }]"))
    assert len(errs) == 1 and "'a'" in errs[0] and "outside die" in errs[0]
    errs = errors_of(make("[{ name: a, w: 4, h: 4, fixed: [-1, 0] }]"))
    assert "outside die" in errs[0]


def test_rule5_fixed_overlap_and_halo() -> None:
    errs = errors_of(
        make("[{ name: a, w: 4, h: 4, fixed: [0, 0] }, { name: b, w: 4, h: 4, fixed: [2, 2] }]")
    )
    assert errs == ["fixed modules 'a' and 'b' overlap"]
    errs = errors_of(
        make("[{ name: a, w: 4, h: 4, fixed: [0, 0] }, { name: b, w: 4, h: 4, fixed: [4, 0] }]")
    )
    assert errs == ["fixed modules 'a' and 'b' violate halo 1"]
    # gap of 1 with halo 1 is fine; touching with halo 0 is fine
    parse_design(
        make("[{ name: a, w: 4, h: 4, fixed: [0, 0] }, { name: b, w: 4, h: 4, fixed: [5, 0] }]")
    )
    parse_design(
        make(
            "[{ name: a, w: 4, h: 4, fixed: [0, 0] }, { name: b, w: 4, h: 4, fixed: [4, 0] }]",
            die="{ width: 20, height: 20, halo: 0 }",
        )
    )


def test_rule6_unknown_module() -> None:
    errs = errors_of(make("[{ name: a, w: 1, h: 1 }]", "[{from: a, to: zz, width: 8}]"))
    assert len(errs) == 1 and "unknown module 'zz'" in errs[0]


def test_rule7_self_loop() -> None:
    errs = errors_of(make("[{ name: a, w: 1, h: 1 }]", "[{from: a, to: a, width: 8}]"))
    assert len(errs) == 1 and "self-loop" in errs[0]


def test_rule8_rotatable() -> None:
    errs = errors_of(make("[{ name: a, w: 1, h: 1, rotatable: true }]"))
    assert errs == ["module 'a': rotation not supported in Phase 1"]
    parse_design(make("[{ name: a, w: 1, h: 1, rotatable: false }]"))


def test_rule9_cannot_fit() -> None:
    errs = errors_of(
        make(
            "[{ name: a, w: 5, h: 5 }, { name: b, w: 5, h: 5 }]",
            die="{ width: 7, height: 7 }",
        )
    )
    assert len(errs) == 1 and "design cannot fit" in errs[0]


def test_rule10_duplicate_nets_allowed() -> None:
    d = parse_design(
        make(
            "[{ name: a, w: 1, h: 1 }, { name: b, w: 1, h: 1 }]",
            "[{from: a, to: b, width: 8}, {from: b, to: a, width: 16}]",
        )
    )
    assert len(d.nets) == 2


def test_three_errors_reported_together() -> None:
    errs = errors_of(
        make(
            "[{ name: a, w: 1, h: 1 }, { name: a, w: 1, h: 1 }, { name: r, w: 1, h: 1, "
            "rotatable: true }]",
            "[{from: a, to: a, width: 8}]",
        )
    )
    assert len(errs) == 3
    assert any("duplicate" in e for e in errs)
    assert any("rotation" in e for e in errs)
    assert any("self-loop" in e for e in errs)


def test_not_a_mapping() -> None:
    assert errors_of("- 1\n- 2\n")


def test_load_design_uses_file_stem(tmp_path: Path) -> None:
    p = tmp_path / "my_chip.yaml"
    p.write_text(SPEC_EXAMPLE)
    assert load_design(p).name == "my_chip"
