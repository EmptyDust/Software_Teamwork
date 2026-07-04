from rag.app.standard.clauses import detect_heading, flatten_clauses, parse_clauses


def test_full_width_chinese_heading_is_detected_as_clause():
    heading = detect_heading("１．１ 术语和定义")

    assert heading is not None
    assert heading.kind == "clause"
    assert heading.number == "1.1"
    assert heading.title == "术语和定义"
    assert heading.level == 2


def test_annex_note_and_table_caption_detection():
    assert detect_heading("Annex A Precision").kind == "annex"
    assert detect_heading("附录Ａ 资料性附录").kind == "annex"
    assert detect_heading("NOTE 1 This is explanatory.").kind == "note"
    assert detect_heading("表 1 技术参数").kind == "table_caption"


def test_parse_clauses_builds_section_paths_and_keeps_body_on_deep_clause():
    nodes = parse_clauses(
        [
            "1 Scope\n"
            "1.1 This test method specifies a procedure.\n"
            "The procedure measures kinematic viscosity.\n"
            "1.2 Referenced documents are listed below.",
        ]
    )

    flattened = flatten_clauses(nodes)
    paths = [" > ".join(heading.number for heading in path) for _node, path in flattened]

    assert paths == ["1", "1 > 1.1", "1 > 1.2"]
    assert "measures kinematic viscosity" in flattened[1][0].text
