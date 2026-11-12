import sys

from app.topic_classifier.api import build_bank

print(build_bank(*sys.argv[1:3]))
