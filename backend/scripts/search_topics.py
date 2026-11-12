import sys

from app.topic_classifier.api import search

r = search(" ".join(sys.argv[1:]) or "mean median mode from probability and statistics")
print("topics:", [(t["topic_name"], t["score"]) for t in r["matched_topics"]])
for q in r["questions"]:
    print(" -", q["id"], "|", q["matched_topic"], "|", (q.get("text") or "")[:70])
