
import json, os, tempfile
from classifier import TopicClassifier

REVIEW_BELOW = 0.20         
_clf = None

def _classifier():
    global _clf
    if _clf is None:
        _clf = TopicClassifier()
    return _clf

def tag_question(record, rel=0.75):
    """record needs 'id'; uses 'text' (OCR/Gemini). Optional 'admin_topics': ['subject/module/topic'] overrides the model.
    All other fields in the record are passed through untouched."""
    clf = _classifier()
    out = dict(record)
    if record.get("admin_topics"):
        tags = [dict(clf.topic_meta[k], score=1.0) for k in record["admin_topics"]]
    else:
        tags = clf.classify(record.get("text") or "", rel=rel)   
    out["subject"] = tags[0]["subject"] if tags else None
    out["module"] = tags[0]["module"] if tags else None
    out["topics"] = [t["topic"] for t in tags]
    out["topic_keys"] = [f'{t["subject"]}/{t["module"]}/{t["topic"]}' for t in tags]
    out["confidence"] = tags[0]["score"] if tags else 0.0
    out["needs_review"] = (not tags) or out["confidence"] < REVIEW_BELOW
    return out

def _assemble(questions):
    by_topic = {}
    for q in questions:
        for k in q.get("topic_keys", []):
            by_topic.setdefault(k, []).append(q["id"])
    return {"questions": questions, "by_topic": by_topic,
            "needs_review": [q["id"] for q in questions if q.get("needs_review")]}

def _write_atomic(path, data):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)             

def _load(path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))["questions"]
    return []

def add_to_bank(record, bank_path="question_bank.json"):
    """Admin uploads one question: tag it and store it. Same id again = update. Returns the tagged record."""
    tagged = tag_question(record)
    questions = [q for q in _load(bank_path) if q["id"] != tagged["id"]] + [tagged]
    _write_atomic(bank_path, _assemble(questions))
    return tagged

def build_bank(raw_path="raw_questions.json", bank_path="question_bank.json"):
    raw = json.load(open(raw_path, encoding="utf-8"))
    bank = _assemble([tag_question(r) for r in raw])
    _write_atomic(bank_path, bank)
    return {"questions": len(bank["questions"]), "topics": len(bank["by_topic"]),
            "needs_review": len(bank["needs_review"])}

def search(query, bank_path="question_bank.json", limit=20):
    bank = _assemble(_load(bank_path))
    qs = {q["id"]: q for q in bank["questions"]}
    topics = _classifier().classify(query, max_topics=3, min_score=0.10)
    seen, results = set(), []
    for t in topics:
        for qid in bank["by_topic"].get(f'{t["subject"]}/{t["module"]}/{t["topic"]}', []):
            if qid not in seen:
                seen.add(qid)
                results.append(dict(qs[qid], matched_topic=t["topic_name"], match_score=t["score"]))
    return {"query": query, "matched_topics": topics, "questions": results[:limit]}
