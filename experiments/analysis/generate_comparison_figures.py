import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

WIDTH = 1040
HEIGHT = 620
COLORS = {
    "baseline": "#4B5563",
    "m0": "#D97706",
    "m1": "#2563EB",
    "m2": "#059669",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Stage 05 paper figures from a comparison JSON file")
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _element(parent: ET.Element, tag: str, **attributes: object) -> ET.Element:
    return ET.SubElement(parent, tag, {key.replace("_", "-"): str(value) for key, value in attributes.items()})


def _text(
    parent: ET.Element,
    x: float,
    y: float,
    value: str,
    *,
    size: int = 14,
    weight: int = 400,
    anchor: str = "middle",
    fill: str = "#111827",
) -> ET.Element:
    node = _element(
        parent,
        "text",
        x=round(x, 1),
        y=round(y, 1),
        font_size=size,
        font_weight=weight,
        text_anchor=anchor,
        fill=fill,
    )
    node.text = value
    return node


def _root(title: str, description: str) -> ET.Element:
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(WIDTH),
            "height": str(HEIGHT),
            "viewBox": f"0 0 {WIDTH} {HEIGHT}",
            "role": "img",
            "aria-labelledby": "title description",
        },
    )
    title_node = _element(root, "title", id="title")
    title_node.text = title
    description_node = _element(root, "desc", id="description")
    description_node.text = description
    _element(root, "rect", x=0, y=0, width=WIDTH, height=HEIGHT, fill="#FFFFFF")
    _text(root, 64, 48, title, size=22, weight=700, anchor="start")
    return root


def _write(root: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _add_legend(root: ET.Element, variants: list[str], y: int = 74) -> None:
    start_x = WIDTH - 84 - len(variants) * 112
    for index, variant in enumerate(variants):
        x = start_x + index * 112
        _element(root, "rect", x=x, y=y - 13, width=18, height=18, rx=2, fill=COLORS[variant])
        _text(root, x + 26, y + 1, variant.upper(), anchor="start", size=13, weight=600)


def _add_rate_axis(root: ET.Element, left: int, top: int, bottom: int, right: int) -> None:
    for step in range(5):
        rate = step / 4
        y = bottom - rate * (bottom - top)
        _element(root, "line", x1=left, y1=y, x2=right, y2=y, stroke="#D1D5DB", stroke_width=1)
        _text(root, left - 14, y + 5, f"{rate:.0%}", anchor="end", size=12, fill="#4B5563")
    _text(root, 26, (top + bottom) / 2, "Rate", size=13, weight=600, fill="#374151")


def build_effectiveness_figure(data: dict[str, Any]) -> ET.Element:
    rows = data["variants"]
    variants = [row["variant"] for row in rows]
    metrics = [
        ("attack_block_rate", ("Attack", "block")),
        ("attack_full_completion_rate", ("Full task", "completion")),
        ("useful_result_retention_rate", ("Useful result", "retention")),
        ("false_value_rate", ("False value", "(lower is better)")),
        ("invariant_pass_rate", ("Invariant", "preservation")),
    ]
    root = _root(
        "Security and utility across execution variants",
        "Grouped bars compare aggregate attack-case rates for Baseline, M0, M1, and M2.",
    )
    _add_legend(root, variants)
    left, right, top, bottom = 82, 1004, 106, 500
    _add_rate_axis(root, left, top, bottom, right)

    group_width = (right - left) / len(metrics)
    bar_width = 30
    bar_gap = 7
    bars_width = len(variants) * bar_width + (len(variants) - 1) * bar_gap
    for metric_index, (metric, labels) in enumerate(metrics):
        center = left + group_width * (metric_index + 0.5)
        start = center - bars_width / 2
        for variant_index, row in enumerate(rows):
            value = row[metric]
            if value is None:
                continue
            height = value * (bottom - top)
            x = start + variant_index * (bar_width + bar_gap)
            y = bottom - height
            _element(root, "rect", x=x, y=y, width=bar_width, height=max(height, 1), rx=2, fill=COLORS[row["variant"]])
            _text(root, x + bar_width / 2, max(top - 6, y - 7), f"{value:.0%}", size=11, weight=600)
        _text(root, center, 530, labels[0], size=13, weight=600)
        _text(root, center, 548, labels[1], size=12, fill="#4B5563")

    _text(
        root,
        82,
        594,
        f"Case 2 + Case 3; n={data['attack_trials_per_variant']} attack trials per variant",
        anchor="start",
        size=12,
        fill="#4B5563",
    )
    return root


def build_latency_figure(data: dict[str, Any]) -> ET.Element:
    rows = data["variants"]
    variants = [row["variant"] for row in rows]
    values = [row["attack_mean_latency_ms"] for row in rows]
    axis_max = max(1000, math.ceil(max(values) * 1.2 / 500) * 500)
    root = _root(
        "Mean attack-case execution latency",
        "Bars compare aggregate mean execution latency for the four variants on Case 2 and Case 3.",
    )
    _add_legend(root, variants)
    left, right, top, bottom = 90, 1004, 106, 500
    tick_step = 1000 if axis_max >= 4000 else 500
    for value in range(0, axis_max + 1, tick_step):
        y = bottom - value / axis_max * (bottom - top)
        _element(root, "line", x1=left, y1=y, x2=right, y2=y, stroke="#D1D5DB", stroke_width=1)
        _text(root, left - 14, y + 5, str(value), anchor="end", size=12, fill="#4B5563")
    _text(root, 28, (top + bottom) / 2, "Milliseconds", size=13, weight=600, fill="#374151")

    slot = (right - left) / len(rows)
    bar_width = 96
    for index, row in enumerate(rows):
        value = row["attack_mean_latency_ms"]
        center = left + slot * (index + 0.5)
        height = value / axis_max * (bottom - top)
        y = bottom - height
        _element(
            root,
            "rect",
            x=center - bar_width / 2,
            y=y,
            width=bar_width,
            height=height,
            rx=3,
            fill=COLORS[row["variant"]],
        )
        _text(root, center, y - 10, f"{value:.1f}", size=12, weight=600)
        _text(root, center, 528, row["variant"].upper(), size=14, weight=700)

    _text(
        root,
        90,
        576,
        "Baseline aborts after the rejected output; its latency is not an equivalent end-to-end comparison.",
        anchor="start",
        size=12,
        fill="#4B5563",
    )
    return root


def generate_figures(data: dict[str, Any], output_dir: Path) -> list[Path]:
    variants = {row["variant"] for row in data.get("variants", [])}
    if variants != set(COLORS):
        raise ValueError(f"Expected four variants, found {sorted(variants)}")
    outputs = [
        output_dir / "effectiveness.svg",
        output_dir / "attack_latency.svg",
    ]
    _write(build_effectiveness_figure(data), outputs[0])
    _write(build_latency_figure(data), outputs[1])
    return outputs


def main() -> None:
    args = parse_args()
    data = json.loads(args.comparison.read_text(encoding="utf-8"))
    outputs = generate_figures(data, args.output_dir)
    print(json.dumps([str(path) for path in outputs]))


if __name__ == "__main__":
    main()
