from rag.app.standard.cleanup import clean_sections, extract_position_tags, repair_dehyphenation, section_text


def test_dehyphenation_repairs_line_end_words_without_touching_urls_or_prefix_terms():
    text = (
        "The appro-\n"
        "priate de-\n"
        "termination method is listed at https://example.com/a-b\n"
        "for non-\n"
        "Newtonian materials and D445-15a. API-\n"
        "gravity and mg-\n"
        "kg ranges stay hyphenated."
    )

    repaired = repair_dehyphenation(text)

    assert "appropriate" in repaired
    assert "determination" in repaired
    assert "https://example.com/a-b" in repaired
    assert "non-Newtonian" in repaired
    assert "D445-15a" in repaired
    assert "API-gravity" in repaired
    assert "mg-kg" in repaired


def test_clean_sections_removes_repeated_noise_and_preserves_clause_text():
    sections = [
        ("ASTM D445 Licensed to Example\n1 Scope\nThis standard covers liquid viscosity.\n- 1 -", ""),
        ("ASTM D445 Licensed to Example\n1.1 This test method specifies a procedure.\n- 2 -", ""),
        ("ASTM D445 Licensed to Example\n1.2 Values stated in SI units are standard.\n- 3 -", ""),
    ]

    cleaned = "\n".join(clean_sections(sections))

    assert "Licensed to Example" not in cleaned
    assert "- 1 -" not in cleaned
    assert "1 Scope" in cleaned
    assert "1.1 This test method specifies a procedure." in cleaned


def test_position_tags_are_extractable_and_removed_from_public_clean_text():
    tag = "@@2\t10.0\t50.0\t12.0\t30.0##"
    sections = [(f"1 Scope{tag}\nThis text is public.", "")]

    assert extract_position_tags(sections[0][0]) == [[1, 10.0, 50.0, 12.0, 30.0]]
    assert "@@" not in clean_sections(sections)[0]


def test_section_text_appends_position_tags_but_not_layout_labels():
    assert section_text(("1 Scope", "@@1\t0.0\t1.0\t2.0\t3.0##")).endswith("##")
    assert section_text(("1 Scope", "title")) == "1 Scope"
