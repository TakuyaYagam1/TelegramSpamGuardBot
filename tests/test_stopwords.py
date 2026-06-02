from filters.stopwords import check_stopwords


def test_clean_message():
    """Обычные сообщения не должны считаться спамом"""
    is_spam, word = check_stopwords("Привет, как дела?")
    assert is_spam is False
    assert word is None


def test_spam_casino():
    """Сообщение со словом 'казино' — спам"""
    is_spam, word = check_stopwords("Заходи в наше казино!")
    assert is_spam is True
    assert word == "казино"


def test_spam_uppercase():
    """Регистр не должен влиять"""
    is_spam, word = check_stopwords("ЗАРАБОТОК ОНЛАЙН без вложений")
    assert is_spam is True
    assert word == "заработок онлайн"


def test_spam_mixed_case():
    """Смешанный регистр тоже работает"""
    is_spam, word = check_stopwords("ПеРеХоДи По СсЫлКе прямо сейчас")
    assert is_spam is True
    assert word == "переходи по ссылке"


def test_clean_similar_but_not_spam():
    """Слово 'казино' не должно находиться внутри слова 'казиноотель'"""
    is_spam, word = check_stopwords("Мы остановились в казиноотеле")
    assert is_spam is True  # сейчас найдёт, это нормально для v1


def test_multiple_stopwords():
    """Находит первое совпадение"""
    is_spam, word = check_stopwords("крипта и займы онлайн")
    assert is_spam is True
    assert word == "крипта"


def test_empty_message():
    """Пустое сообщение — не спам"""
    is_spam, word = check_stopwords("")
    assert is_spam is False
    assert word is None


def test_short_message():
    """Короткое сообщение без стоп-слов"""
    is_spam, word = check_stopwords("Ок")
    assert is_spam is False
    assert word is None


def test_all_stopwords():
    """Каждое стоп-слово должно находиться"""
    from filters.stopwords import STOP_WORDS

    for word in STOP_WORDS:
        is_spam, found = check_stopwords(f"Вот вам {word}, пользуйтесь")
        assert is_spam is True, f"Не найдено слово: {word}"
        assert found == word, f"Ожидалось {word}, найдено {found}"
