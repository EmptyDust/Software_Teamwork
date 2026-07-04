from rag.app.standard import chunks as standard_chunks


def _simple_tokenize(chunk, text, _eng):
    chunk["content_with_weight"] = text
    chunk["content_ltks"] = text.lower()
    chunk["content_sm_ltks"] = text.lower()


def _simple_positions(chunk, positions):
    chunk["page_num_int"] = [int(pos[0]) + 1 for pos in positions]
    chunk["position_int"] = [
        (int(pos[0]) + 1, int(pos[1]), int(pos[2]), int(pos[3]), int(pos[4]))
        for pos in positions
    ]
    chunk["top_int"] = [int(pos[3]) for pos in positions]


def test_build_standard_clause_chunks_uses_clean_text_and_clause_metadata(monkeypatch):
    monkeypatch.setattr(standard_chunks, "tokenize_chunk", _simple_tokenize)
    monkeypatch.setattr(standard_chunks, "add_chunk_positions", _simple_positions)

    sections = [
        (
            "ASTM D445 Licensed to Example\n"
            "Designation: D445 - 15a\n"
            "1 Scope@@1\t10.0\t50.0\t10.0\t30.0##\n"
            "This test method specifies the appro-\n"
            "priate procedure.\n"
            "- 1 -",
            "",
        ),
        (
            "ASTM D445 Licensed to Example\n"
            "1.1 The values stated in SI units are standard.@@2\t11.0\t55.0\t20.0\t40.0##\n"
            "- 2 -",
            "",
        ),
        (
            "ASTM D445 Licensed to Example\n"
            "1.2 The result depends upon sample behavior.@@3\t12.0\t56.0\t25.0\t45.0##\n"
            "- 3 -",
            "",
        ),
    ]

    chunks = standard_chunks.build_standard_clause_chunks(sections, {"docnm_kwd": "ASTM D445-2015.pdf"}, "ASTM D445-2015.pdf", eng=True)

    assert [chunk["clause_no_kwd"] for chunk in chunks] == ["1", "1.1", "1.2"]
    assert all(chunk["doc_type_kwd"] == "clause" for chunk in chunks)
    assert chunks[0]["standard_no_kwd"] == "ASTM D445-2015"
    assert chunks[0]["standard_year_int"] == 2015
    assert chunks[1]["section_path_kwd"] == "ASTM D445-2015 > 1 Scope > 1.1 The values stated in SI units are standard."
    assert "appropriate procedure" in chunks[0]["content_with_weight"]
    assert "@@" not in chunks[0]["content_with_weight"]
    assert "Licensed to Example" not in chunks[0]["content_with_weight"]
    assert chunks[1]["page_num_int"] == [2]


def test_long_clause_is_split_without_losing_metadata(monkeypatch):
    monkeypatch.setattr(standard_chunks, "tokenize_chunk", _simple_tokenize)
    monkeypatch.setattr(standard_chunks, "add_chunk_positions", _simple_positions)

    long_body = "\n".join(f"Paragraph {idx} " + ("x" * 1200) for idx in range(5))
    sections = [("1 Scope\n" + long_body, "")]

    chunks = standard_chunks.build_standard_clause_chunks(sections, {"docnm_kwd": "GB 123.pdf"}, "GB 123.pdf", eng=True)

    assert len(chunks) > 1
    assert {chunk["clause_no_kwd"] for chunk in chunks} == {"1"}
    assert [chunk["chunk_part_int"] for chunk in chunks] == list(range(1, len(chunks) + 1))
