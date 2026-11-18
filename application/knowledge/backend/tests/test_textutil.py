from app.textutil import hashed_embedding, l2_normalize, term_overlap, tokenize


def test_tokenize_mixed_latin_and_cjk():
    assert tokenize("Q3 revenue 营收") == ["q3", "revenue", "营", "收"]


def test_tokenize_lowercases():
    assert tokenize("Hello WORLD") == ["hello", "world"]


def test_l2_normalize():
    v = l2_normalize([3.0, 4.0])
    assert abs(v[0] - 0.6) < 1e-9
    assert abs(v[1] - 0.8) < 1e-9


def test_l2_normalize_zero_vector():
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]


def test_hashed_embedding_dim_and_norm():
    vec = hashed_embedding("hello world", 128)
    assert len(vec) == 128
    norm = sum(v * v for v in vec)
    assert abs(norm - 1.0) < 1e-9


def test_term_overlap():
    assert term_overlap(["revenue", "growth"], "revenue grew a lot") == 0.5
    assert term_overlap(["zzz"], "nothing here") == 0.0
    assert term_overlap([], "anything") == 0.0
