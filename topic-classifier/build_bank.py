
import sys
from api import build_bank
print(build_bank(*(sys.argv[1:3] or ["raw_questions.json", "question_bank.json"])))
