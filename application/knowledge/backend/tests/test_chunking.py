from app.chunking import chunk_markdown


def test_no_headings_single_chunk():
    md = "hello world"
    drafts = chunk_markdown(md, max_chars=800, overlap=120)
    assert len(drafts) == 1
    assert drafts[0].text == "hello world"
    assert drafts[0].heading_path == ""
    assert drafts[0].start_offset == 0
    assert drafts[0].end_offset == len("hello world")


def test_headings_build_path():
    md = "# A\n\nintro\n\n## B\n\nbody\n\n# C\n\nend"
    drafts = chunk_markdown(md, max_chars=800, overlap=120)
    paths = {d.heading_path for d in drafts}
    assert "A" in paths
    assert "A / B" in paths
    assert "C" in paths


def test_long_text_splits_with_monotonic_offsets():
    md = ("word " * 500).strip()
    drafts = chunk_markdown(md, max_chars=800, overlap=120)
    assert len(drafts) > 1
    starts = [d.start_offset for d in drafts]
    assert starts == sorted(starts)


def test_empty_markdown():
    assert chunk_markdown("", max_chars=800, overlap=120) == []
