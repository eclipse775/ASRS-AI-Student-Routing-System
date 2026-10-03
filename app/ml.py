"""Supervised multinomial Naive Bayes text classifier with safe abstention."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

STOPWORDS = set("a an the i my me we our you your it is are was were be been to of in on at for with and or but this that have has had can could would should please help need want how what when where why do does did not no get am about from as will out so some any just into cannot after before student request issue problem support university school today yesterday tomorrow".split())


def tokenize(text):
    normalized = text.lower().replace("wi-fi", "wifi").replace("wi fi", "wifi")
    words = re.findall(r"[a-z]+", normalized)
    words = [w for w in words if w not in STOPWORDS and len(w) > 1]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


class Classifier:
    """Learn token likelihoods from labels; never fit on evaluation examples."""
    provider = "local"

    def __init__(self, training_path):
        raw = Path(training_path).read_bytes()
        rows = json.loads(raw)
        self.version = "nb-" + hashlib.sha256(raw).hexdigest()[:12]
        self.counts = defaultdict(Counter)
        self.documents = Counter()
        self.vocabulary = set()
        for row in rows:
            features = tokenize(row["text"])
            self.counts[row["label"]].update(features)
            self.documents[row["label"]] += 1
            self.vocabulary.update(features)
        self.labels = sorted(self.documents)
        self.totals = {k: sum(v.values()) for k, v in self.counts.items()}
        # Features occurring across every department carry little routing evidence.
        self.informative = {w for w in self.vocabulary
                            if sum(w in self.counts[k] for k in self.labels) < len(self.labels)}
        self.training_size = len(rows)

    def status(self):
        return {"provider": "local", "model": self.version, "configured": True,
                "connection_verified": False, "last_error": None,
                "training_examples": self.training_size}

    def classify(self, text):
        features = Counter(w for w in tokenize(text) if w in self.vocabulary)
        scores = {}
        size = len(self.vocabulary)
        for label in self.labels:
            score = math.log(self.documents[label] / self.training_size)
            for word, frequency in features.items():
                score += frequency * math.log((self.counts[label][word] + 1) /
                                               (self.totals[label] + size))
            scores[label] = score
        # Temperature reduces excessive certainty from repeated correlated words.
        maximum = max(scores.values())
        exp_scores = {k: math.exp((v - maximum) / 1.5) for k, v in scores.items()}
        denominator = sum(exp_scores.values())
        probabilities = {k: v / denominator for k, v in exp_scores.items()}
        label = max(probabilities, key=probabilities.get)
        matched = sorted(w for w in features if w in self.informative and "_" not in w)
        confidence = probabilities[label]
        reason = "Classification based on labeled support examples."
        if len(matched) < 2:
            confidence = min(confidence, 0.49)
            reason = "Too little known topic evidence. A staff member should review this request."
        if re.search(r"[\u0400-\u04ff]", text):
            confidence = min(confidence, 0.49)
            reason = "Russian and Kazakh classification is planned for a later sprint. Staff review is required."
        return {"suggested_code": label, "confidence": round(confidence, 6),
                "probabilities": {k: round(v, 6) for k, v in probabilities.items()},
                "matched_terms": matched[:12], "reason": reason,
                "model_version": self.version, "provider": "local", "provider_result": "local"}
