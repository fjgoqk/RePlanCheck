import xml.etree.ElementTree as ET

import pytest

from experiments.analysis.generate_comparison_figures import generate_figures


def _comparison() -> dict:
    rows = []
    for variant, full_completion, useful, false_value, invariants, latency in [
        ("baseline", 0.0, 0.0, 0.0, None, 2000.0),
        ("m0", 0.0, 1.0, 1.0, 1.0, 3000.0),
        ("m1", 0.0, 1.0, 0.0, 1.0, 3100.0),
        ("m2", 1.0, 1.0, 0.0, 1.0, 3400.0),
    ]:
        rows.append(
            {
                "variant": variant,
                "attack_block_rate": 1.0,
                "attack_full_completion_rate": full_completion,
                "useful_result_retention_rate": useful,
                "false_value_rate": false_value,
                "invariant_pass_rate": invariants,
                "attack_mean_latency_ms": latency,
            }
        )
    return {"attack_trials_per_variant": 60, "variants": rows}


def test_generate_stage05_svg_figures(tmp_path):
    outputs = generate_figures(_comparison(), tmp_path)

    assert [path.name for path in outputs] == ["effectiveness.svg", "attack_latency.svg"]
    for path in outputs:
        root = ET.parse(path).getroot()
        assert root.tag.endswith("svg")
        assert root.attrib["viewBox"] == "0 0 1040 620"
        assert path.stat().st_size > 1000


def test_generate_figures_requires_all_variants(tmp_path):
    data = _comparison()
    data["variants"].pop()

    with pytest.raises(ValueError, match="Expected four variants"):
        generate_figures(data, tmp_path)
