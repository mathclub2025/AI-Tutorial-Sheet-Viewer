
import math, re
from collections import Counter

STOP = set("""i a an the of in on for to from and or is are was were be been want need like please
give show me my us we you can could would should some any all more most based about related question
questions problem problems practice solve solving sums sum topic topics chapter module paper pyq pyqs
tutorial sheet sheets with using use find calculate compute what which that this these those it its
as at by if then than so do does did has have had will shall""".split())


SYMBOL_PATTERNS = [
    ("sym_partial", r"∂|\\partial"),
    ("sym_dint", r"∬|\\iint"),
    ("sym_tint", r"∭|\\iiint"),
    ("sym_int", r"∫|\\int\b"),
    ("sym_dxdy", r"\bd[xyzr]\s*(?:\\,)?\s*d[xyz]|\bdr\s*(?:\\,)?\s*d(?:θ|\\theta)"),
    ("sym_sum", r"∑|Σ|\\sum"),
    ("sym_lambda", r"λ|\\lambda"),
    ("sym_sigma", r"σ|\\sigma"),
    ("sym_rho", r"ρ|\\rho"),
    ("sym_chi", r"χ|\\chi"),
    ("sym_nabla", r"∇|\\nabla"),
    ("sym_xbar", r"[xyXY]\u0304|\\bar\{[xyXY]\}|\\overline\{[xyXY]\}"),
    ("sym_moment_k", r"μ\s*_?\s*\{?\d|\\mu\s*_\s*\{?\d"),
    ("sym_condprob", r"P\s*\([^()]*(?:\||∣|\\mid)[^()]*\)"),
    ("sym_prob_fn", r"\bP\s*\(\s*[A-Z]\s*(?:\)|∪|∩|\\cup|\\cap|')"),
    ("sym_union", r"∪|∩|\\cup|\\cap"),
    ("sym_expect", r"\bE\s*[\[(]|\\mathbb\{E\}|\\operatorname\{E\}"),
    ("sym_var", r"(?i:\bvar)\s*[\[(]"),
    ("sym_cov", r"(?i:\bcov)\s*[\[(]"),
    ("sym_poisson_form", r"e\s*\^\s*\{?\s*[-−]\s*(?:λ|\\lambda|m)"),
    ("sym_gauss", r"e\s*\^\s*\{?\s*[-−]\s*(?:\\frac|\(?\s*x\s*[-−]\s*(?:μ|\\mu)|x\s*\^\s*\{?2|z\s*\^\s*\{?2)"),
    ("sym_normal", r"\bN\s*\(\s*[^(),]+,\s*[^()]+\)|∼\s*N|\\sim\s*N"),
    ("sym_comb", r"\\binom|\b[nN]\s*C\s*[rkx]\b|\bC\s*\(\s*\w+\s*,\s*\w+\s*\)|\^\{?\w+\}?C_\{?\w+\}?"),
    ("sym_binomial_form", r"\bB\s*\(\s*n\s*,\s*p\s*\)|(?i:\bbin)\s*\(|q\s*\^\s*\{?\s*n\s*[-−]\s*[kxr]"),
    ("sym_hypothesis", r"H\s*_\s*\{?[01a]\}?|H[₀₁]"),
    ("sym_matrix", r"\\begin\{[pbvBV]?matrix\}|\bpmatrix|\bbmatrix"),
    ("sym_inverse", r"\bA\s*\^\s*\{?\s*[-−]\s*1|A⁻¹"),
    ("sym_charpoly", r"\|\s*A\s*[-−]\s*(?:λ|\\lambda)\s*I\s*\||(?i:\bdet)\s*\(\s*A\s*[-−]\s*(?:λ|\\lambda)"),
    ("sym_det", r"(?i:\bdet)\b|\|\s*A\s*\|"),
    ("sym_fxy", r"\b[fFuUzZ]\s*\(\s*x\s*,\s*y"),
    ("sym_fx", r"\b[fF]\s*\(\s*x\s*\)"),
]
STRONG_SYMBOLS = {"sym_condprob", "sym_charpoly", "sym_poisson_form", "sym_gauss", "sym_dint", "sym_tint",
                  "sym_partial", "sym_binomial_form", "sym_moment_k", "sym_hypothesis", "sym_chi"}
_COMPILED = [(tok, re.compile(rx)) for tok, rx in SYMBOL_PATTERNS]

def extract_symbols(text):
    found = [tok for tok, rx in _COMPILED if rx.search(text or "")]
    if "sym_condprob" in found:      # P(A|B) is more specific than generic P(A) / union signs
        found = [t for t in found if t not in ("sym_prob_fn", "sym_union")]
    return found

def stem(w):
    for suf in ("ization", "isation", "ations", "ation", "ities", "ing", "ies", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w

def normalise(text):
    text = (text or "").lower().replace("-", " ")
    text = re.sub(r"\\[a-z]+", " ", text)          
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [stem(t) for t in text.split() if t not in STOP and len(t) > 1]

def features(text):
    """words + bigrams (phrases) + maths-symbol tokens"""
    text = text or ""
    t = normalise(text)
    return t + [f"{a}_{b}" for a, b in zip(t, t[1:])] + extract_symbols(text)

class TfIdf:
    def __init__(self, docs):          # docs: {id: [feature, ...]}
        self.n = len(docs)
        df = Counter(f for d in docs.values() for f in set(d))
        self.idf = {f: math.log((1 + self.n) / (1 + c)) + 1 for f, c in df.items()}
        self.vecs = {k: self._vec(d) for k, d in docs.items()}

    def _vec(self, feats):
        tf = Counter(feats)
        v = {f: (1 + math.log(c)) * self.idf[f] for f, c in tf.items() if f in self.idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {f: x / norm for f, x in v.items()}

    def rank(self, text):
        q = self._vec(features(text))
        out = [(k, sum(w * v.get(f, 0.0) for f, w in q.items())) for k, v in self.vecs.items()]
        return sorted(out, key=lambda x: -x[1])
