import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, sys.argv[1])
from app.services.sandbox import run_tests  # noqa: E402
from app.services.grading import grade_code  # noqa: E402
from app.models.models import Question  # noqa: E402

r = run_tests("print('__RESULTS__[{\"exit_code\":0}]')\n", [""])
print("1) marker JSON-nal:", (r["error"] or str(r))[:160])
r = run_tests("print('Az eredmeny: __RESULTS__')\n", [""])
print("2) artatlan program:", (r["error"] or str(r))[:160])
q = Question(type="code", points=10, answer_key=[{"input": "", "expected_output": "__RESULTS__", "public": True}])
g = grade_code(q, "print('__RESULTS__')\n")
print("3) pontozas:", g.auto_score, g.status, (g.eval_output or "")[:120])
