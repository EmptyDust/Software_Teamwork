from rag.app.standard import tables as standard_tables


def _simple_tokenize(chunk, text, _eng):
    chunk["content_with_weight"] = text
    chunk["content_ltks"] = text
    chunk["content_sm_ltks"] = text


def _simple_positions(chunk, positions):
    chunk["page_num_int"] = [int(pos[0]) + 1 for pos in positions]
    chunk["position_int"] = [
        (int(pos[0]) + 1, int(pos[1]), int(pos[2]), int(pos[3]), int(pos[4]))
        for pos in positions
    ]
    chunk["top_int"] = [int(pos[3]) for pos in positions]


def _build(sections, parser_tables):
    return standard_tables.build_standard_table_chunks(
        sections,
        parser_tables,
        {"docnm_kwd": "ASTM D445-2015.pdf"},
        "ASTM D445-2015.pdf",
        eng=True,
        tokenize_fn=_simple_tokenize,
        positions_fn=_simple_positions,
    )


def test_deepdoc_like_table_gets_caption_metadata_and_row_chunks():
    sections = [
        (
            "Designation: D445 - 2015\n"
            "5 Apparatus\n"
            "Table 1 - Viscometer tolerances@@1\t10.0\t80.0\t20.0\t40.0##",
            "",
        )
    ]
    parser_tables = [((None, [["Item", "Limit"], ["A", "1"], ["B", "2"]]), [[0, 10, 80, 45, 90]])]

    chunks = _build(sections, parser_tables)

    table_chunk = chunks[0]
    row_chunks = chunks[1:]
    assert table_chunk["doc_type_kwd"] == "table"
    assert table_chunk["table_no_kwd"] == "Table 1"
    assert table_chunk["table_title_tks"] == "Viscometer tolerances"
    assert table_chunk["clause_no_kwd"] == "5"
    assert table_chunk["section_path_kwd"] == "ASTM D445-2015 > 5 Apparatus"
    assert "| Item | Limit |" in table_chunk["content_with_weight"]
    assert table_chunk["page_num_int"] == [1]
    assert [chunk["doc_type_kwd"] for chunk in row_chunks] == ["table_row", "table_row"]
    assert row_chunks[0]["row_index_int"] == 1
    assert row_chunks[0]["columns_obj"] == {"Item": "A", "Limit": "1"}


def test_markdown_table_section_gets_chinese_caption_metadata():
    sections = [
        (
            "1 范围\n"
            "表 1 试验条件\n"
            "| 项目 | 限值 |\n"
            "| --- | --- |\n"
            "| 温度 | 20 |\n"
            "| 时间 | 30 |",
            "",
        )
    ]

    chunks = _build(sections, [])

    assert chunks[0]["doc_type_kwd"] == "table"
    assert chunks[0]["table_no_kwd"] == "表 1"
    assert chunks[0]["table_title_tks"] == "试验条件"
    assert chunks[0]["clause_no_kwd"] == "1"
    assert "| 项目 | 限值 |" in chunks[0]["content_with_weight"]
    assert any(chunk["doc_type_kwd"] == "table_row" for chunk in chunks)


def test_html_table_section_gets_table_chunk():
    sections = [
        (
            "2 Requirements\n"
            "Table A.1 Precision values\n"
            "<table><tr><th>Property</th><th>Value</th></tr>"
            "<tr><td>Density</td><td>0.1</td></tr></table>",
            "",
        )
    ]

    chunks = _build(sections, [])

    assert chunks[0]["table_no_kwd"] == "Table A.1"
    assert chunks[0]["table_title_tks"] == "Precision values"
    assert "| Property | Value |" in chunks[0]["content_with_weight"]
    assert chunks[1]["columns_obj"] == {"Property": "Density", "Value": "0.1"}


def test_ambiguous_table_suppresses_row_chunks_but_keeps_table_level():
    sections = ["Table 2 - Merged cells"]
    parser_tables = [((None, "<table><tr><th colspan='2'>Header</th></tr><tr><td>A</td><td>1</td></tr></table>"), "")]

    chunks = _build(sections, parser_tables)

    assert len(chunks) == 1
    assert chunks[0]["doc_type_kwd"] == "table"
    assert chunks[0]["table_no_kwd"] == "Table 2"


def test_unreliable_rows_without_header_do_not_emit_row_chunks():
    sections = ["Table 3 - Plain values"]
    parser_tables = [((None, [["", "Limit"], ["A", "1"]]), "")]

    chunks = _build(sections, parser_tables)

    assert [chunk["doc_type_kwd"] for chunk in chunks] == ["table"]


def test_captionless_table_keeps_standard_section_context_fallback():
    sections = ["Designation: D445 - 2015\n7 Procedure"]
    parser_tables = [((None, [["Item", "Limit"], ["A", "1"]]), "")]

    chunks = _build(sections, parser_tables)

    assert chunks[0]["doc_type_kwd"] == "table"
    assert chunks[0]["section_path_kwd"] == "ASTM D445-2015"
    assert "table_no_kwd" not in chunks[0]
