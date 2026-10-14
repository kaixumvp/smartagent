from smartagent.db.models import VectorMemory


def test_vector_memory_session_id_fits_scoped_chat_key():
    max_chat_key_length = len("chat:") + (64 * 3) + 3 + 128

    assert VectorMemory.__table__.c.session_id.type.length >= max_chat_key_length
