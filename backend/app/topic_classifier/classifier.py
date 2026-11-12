
import json
import os

from .nlp_local import STRONG_SYMBOLS, TfIdf, features

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")


class TopicClassifier:
    def __init__(self, taxonomy_path=os.path.join(DATA_DIR, "taxonomy.json")):
        self.tax = json.load(open(taxonomy_path, encoding="utf-8"))["subjects"]
        self.topic_meta, topic_docs, subj_docs = {}, {}, {}
        for sid, s in self.tax.items():
            sdoc, ssyms = [s["name"]] + s.get("aliases", []), []
            for mid, m in s["modules"].items():
                for tid, t in m["topics"].items():
                    key = f"{sid}/{mid}/{tid}"
                    self.topic_meta[key] = dict(subject=sid, subject_name=s["name"], module=mid,
                                                module_name=m["name"], topic=tid, topic_name=t["name"])
                    syms = t.get("symbols", [])
                    text = " ".join([t["name"]] * 3 + t["keywords"] * 2)
                    # symbols weigh like the topic name; very specific notation (e.g. P(A|B), ∂, |A-λI|) weighs 3x more
                    topic_docs[key] = features(text) + [x for x in syms for _ in range(4 if x in STRONG_SYMBOLS else 2)]
                    sdoc += [t["name"]] + t["keywords"]
                    ssyms += syms
            subj_docs[sid] = features(" ".join(sdoc)) + ssyms
        self.topics = TfIdf(topic_docs)
        self.subjects = TfIdf(subj_docs)

    def classify(self, text, max_topics=3, min_score=0.12, rel=0.55, subject=None):
        """returns list of topic dicts with 'score'; optionally restricted to a subject"""
        text = text or ""
        subj_rank = self.subjects.rank(text)
        best_subj = subj_rank[0][0] if subj_rank and subj_rank[0][1] > 0.05 else None
        subject = subject or best_subj
        ranked = [(k, sc) for k, sc in self.topics.rank(text) if sc >= min_score]
        if subject:
            ranked = [(k, sc) for k, sc in ranked if self.topic_meta[k]["subject"] == subject]
        if not ranked:
            return []
        top = ranked[0][1]
        picked = [(k, sc) for k, sc in ranked if sc >= rel * top][:max_topics]
        return [dict(self.topic_meta[k], score=round(sc, 3)) for k, sc in picked]
