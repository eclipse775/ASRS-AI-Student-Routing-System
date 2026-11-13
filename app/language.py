"""Lightweight language detection and offline vocabulary for English/Russian/Kazakh intake."""
import re

KAZAKH_MARKS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
RUSSIAN_WORDS = {"и", "в", "не", "на", "мне", "мой", "моя", "это", "для", "что", "как", "необходимо", "помогите"}

LEXICON = {
    # Russian
    "вайфай":"wifi", "wi-fi":"wifi", "интернет":"internet", "сеть":"network", "пароль":"password",
    "логин":"login", "войти":"login", "аккаунт":"account", "учетная":"account", "компьютер":"computer",
    "ноутбук":"laptop", "принтер":"printer", "почта":"email", "почту":"email", "портал":"portal",
    "доступ":"access", "сбросить":"reset", "оплата":"payment", "оплатить":"payment", "плата":"tuition",
    "стипендия":"scholarship", "стипендию":"scholarship", "грант":"scholarship", "возврат":"refund",
    "экзамен":"exam", "экзамена":"exam", "расписание":"schedule", "оценка":"grade", "оценки":"grade",
    "предмет":"course", "курс":"course", "регистрация":"registration", "запись":"registration",
    "врач":"doctor", "больница":"hospital", "клиника":"clinic", "здоровье":"health", "боль":"pain",
    "заболел":"sick", "медицинский":"medical", "психолог":"counseling", "тревога":"anxiety",
    "пожар":"fire", "угроза":"threat", "нападение":"assault", "оружие":"weapon", "преследует":"stalking",
    # Kazakh
    "сымсыз":"wireless", "желі":"network", "құпиясөз":"password", "құпия":"password", "кіру":"login",
    "тіркелгі":"account", "компьютерім":"computer", "ноутбук":"laptop", "принтер":"printer",
    "пошта":"email", "порталға":"portal", "қолжетімділік":"access", "төлем":"payment", "төлемі":"payment",
    "оқуақысы":"tuition", "стипендия":"scholarship", "грант":"scholarship", "қайтарым":"refund",
    "емтихан":"exam", "сабақ":"course", "кесте":"schedule", "баға":"grade", "тіркелу":"registration",
    "дәрігер":"doctor", "аурухана":"hospital", "денсаулық":"health", "ауырып":"sick", "ауырсыну":"pain",
    "психолог":"counseling", "мазасыздық":"anxiety", "өрт":"fire", "қауіп":"threat", "шабуыл":"assault",
    "қару":"weapon", "қорқыту":"threat", "аңду":"stalking",
}


def detect_language(text):
    text = text or ""
    if any(ch in KAZAKH_MARKS for ch in text):
        return "kk"
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cyrillic and cyrillic >= latin:
        words = set(re.findall(r"[а-яё]+", text.lower()))
        return "ru" if words & RUSSIAN_WORDS or cyrillic > 0 else "kk"
    return "en" if latin or not cyrillic else "other"


def english_features(text):
    words = re.findall(r"[^\W\d_]+", (text or "").lower(), flags=re.UNICODE)
    return [LEXICON[w] for w in words if w in LEXICON]
