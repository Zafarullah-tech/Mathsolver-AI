from flask import Flask, render_template, request, jsonify
import sympy as sp
from sympy import (symbols, diff, integrate, limit, series, solve,
                   simplify, factor, expand, sympify, Eq,
                   sin, cos, tan, exp, log, sqrt, pi, oo, E,
                   Add, Mul, Pow, latex)
from dotenv import load_dotenv
import os, re, logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Gemini (optional) ─────────────────────────────────────────
GEMINI_AVAILABLE = False
client = None
try:
    from google import genai
    KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBWJPF4XF-zAFZnalTBQ4QCsPmVXjlPC3c")
    if KEY:
        client = genai.Client(api_key=KEY)
        GEMINI_AVAILABLE = True
        print("✅ Gemini enabled")
except Exception as e:
    print(f"⚠️  Gemini unavailable: {e}")

# ── Symbols ───────────────────────────────────────────────────
x, y, z, t, a, b, n = symbols('x y z t a b n')
LOCALS = {
    'x':x,'y':y,'z':z,'t':t,'a':a,'b':b,'n':n,
    'e':E,'pi':pi,'oo':oo,'inf':oo,
    'sin':sin,'cos':cos,'tan':tan,'exp':exp,'log':log,'sqrt':sqrt
}

# ══════════════════════════════════════════════════════════════
# HTML BUILDING BLOCKS
# ══════════════════════════════════════════════════════════════
def step_row(label, content):
    return f'<div class="step-row"><div class="step-label">{label}</div><div class="step-content">{content}</div></div>'

def math_box(text):
    return f'<div class="math-expr">{text}</div>'

def rule_box(text):
    return f'<div class="rule-box">{text}</div>'

def note_box(text):
    return f'<div class="step-note">{text}</div>'

def divider():
    return '<div class="step-div"></div>'

def code_inline(t):
    return f'<code>{t}</code>'

def sym(e):
    return str(e)


# ══════════════════════════════════════════════════════════════
# EXPRESSION UTILITIES
# ══════════════════════════════════════════════════════════════
def clean(s):
    s = s.strip()
    s = s.replace('^','**')
    s = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', s)
    s = re.sub(r'([a-zA-Z\)])(\d)', r'\1*\2', s)
    s = re.sub(r'\)\s*\(', r')*(', s)
    s = re.sub(r'\bln\b', 'log', s)
    return s

def parse(s):
    return sympify(clean(s), locals=LOCALS)

def pull_expr(text, keywords):
    t = text.lower()
    for kw in sorted(keywords, key=len, reverse=True):
        t = re.sub(rf'\b{re.escape(kw)}\b', ' ', t)
    for w in ['the','find','calculate','compute','evaluate','please','me',
              'can','you','what','is','of','a','an','given','following']:
        t = re.sub(rf'\b{w}\b', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


# ══════════════════════════════════════════════════════════════
# RULE IDENTIFIER
# ══════════════════════════════════════════════════════════════
def get_derivative_rule(expr):
    """Returns (rule_name, rule_formula_html) for the expression."""
    if isinstance(expr, Add):
        return "Sum Rule", "d/dx [f(x) + g(x)] = f'(x) + g'(x)"
    if isinstance(expr, Mul):
        args = expr.args
        consts = [a for a in args if a.is_number]
        funcs  = [a for a in args if not a.is_number]
        if consts and len(funcs) == 1:
            return "Constant Multiple Rule", "d/dx [c·f(x)] = c · f'(x)"
        return "Product Rule", "d/dx [f(x)·g(x)] = f(x)·g'(x) + g(x)·f'(x)"
    if isinstance(expr, Pow):
        base, exp_e = expr.args
        if base == x and exp_e.is_number:
            return "Power Rule", "d/dx [x<sup>n</sup>] = n·x<sup>n−1</sup>"
        if exp_e.is_number:
            return "Chain Rule + Power Rule", "d/dx [g(x)<sup>n</sup>] = n·g(x)<sup>n−1</sup>·g'(x)"
        return "Exponential Rule", "d/dx [a<sup>f(x)</sup> ] = a<sup>f(x)</sup>·ln(a)·f'(x)"
    fn = type(expr).__name__.lower()
    if fn == 'log':
        inner = expr.args[0]
        if inner == x:
            return "Logarithm Rule", "d/dx [ln(x)] = 1/x"
        return "Chain Rule (Log)", "d/dx [ln(g(x))] = g'(x) / g(x)"
    if fn == 'sin':
        inner = expr.args[0]
        if inner == x: return "Sine Rule", "d/dx [sin(x)] = cos(x)"
        return "Chain Rule (Sine)", "d/dx [sin(g(x))] = cos(g(x)) · g'(x)"
    if fn == 'cos':
        inner = expr.args[0]
        if inner == x: return "Cosine Rule", "d/dx [cos(x)] = −sin(x)"
        return "Chain Rule (Cosine)", "d/dx [cos(g(x))] = −sin(g(x)) · g'(x)"
    if fn == 'tan':
        return "Tangent Rule", "d/dx [tan(x)] = sec²(x)"
    if fn == 'exp':
        inner = expr.args[0]
        if inner == x: return "Exponential Rule", "d/dx [e<sup>x</sup>] = e<sup>x</sup>"
        return "Chain Rule (Exp)", "d/dx [e<sup>g(x)</sup>] = e<sup>g(x)</sup> · g'(x)"
    return "Differentiation", "Apply standard differentiation rules"

def get_integral_rule(expr):
    fn = type(expr).__name__.lower()
    if isinstance(expr, Pow) and expr.args[0] == x:
        return "Power Rule", "∫ x<sup>n</sup> dx = x<sup>n+1</sup>/(n+1) + C  &nbsp;[n ≠ −1]"
    if fn == 'sin':
        return "Trigonometric Rule", "∫ sin(x) dx = −cos(x) + C"
    if fn == 'cos':
        return "Trigonometric Rule", "∫ cos(x) dx = sin(x) + C"
    if fn == 'exp':
        return "Exponential Rule", "∫ e<sup>x</sup> dx = e<sup>x</sup> + C"
    if fn == 'log':
        return "Logarithm Rule", "∫ (1/x) dx = ln|x| + C"
    if isinstance(expr, Add):
        return "Sum Rule", "∫ [f(x)+g(x)] dx = ∫f(x)dx + ∫g(x)dx"
    if isinstance(expr, Mul):
        return "Integration by Parts", "∫ u dv = uv − ∫ v du"
    return "Standard Integration", "Apply integration techniques"


# ══════════════════════════════════════════════════════════════
# STEP GENERATORS  (Rule → Here → Working → So)
# ══════════════════════════════════════════════════════════════

def make_derivative_steps(q, raw, expr, result):
    rule_name, rule_formula = get_derivative_rule(expr)
    simp = simplify(result)
    parts = []

    # ── Rule ──────────────────────────────────────────────────
    parts.append(step_row("Rule:", rule_box(f"<strong>{rule_name}</strong><br>{rule_formula}")))
    parts.append(divider())

    # ── Here ──────────────────────────────────────────────────
    parts.append(step_row("Here:", math_box(f"f(x) = {sym(expr)}")))
    parts.append(divider())

    # ── Show g(x) and g'(x) for chain/log rules ───────────────
    try:
        fn = type(expr).__name__.lower()
        if fn in ('log','sin','cos','tan','exp') and expr.args:
            inner = expr.args[0]
            d_inner = diff(inner, x)
            parts.append(step_row("g(x) =", math_box(sym(inner))))
            parts.append(step_row("g'(x) =", math_box(sym(d_inner))))
            parts.append(divider())
    except Exception:
        pass

    # ── Term-by-term for polynomials / sums ───────────────────
    try:
        terms = Add.make_args(expand(expr))
        if len(terms) > 1:
            rows = "".join(
                f'<div class="term-row"><span>d/dx [{sym(tm)}]</span>'
                f'<span class="eq">= {sym(diff(tm,x))}</span></div>'
                for tm in terms
            )
            parts.append(step_row("Term-by-term:", f'<div class="term-table">{rows}</div>'))
            parts.append(divider())
    except Exception:
        pass

    # ── Product Rule: show each part ──────────────────────────
    if isinstance(expr, Mul) and not any(a.is_number for a in expr.args):
        args = list(expr.args)
        if len(args) == 2:
            f1, g1 = args
            df1, dg1 = diff(f1, x), diff(g1, x)
            parts.append(step_row("Let:", math_box(
                f"f(x) = {sym(f1)}, &nbsp; g(x) = {sym(g1)}")))
            parts.append(step_row("Then:", math_box(
                f"f'(x) = {sym(df1)}, &nbsp; g'(x) = {sym(dg1)}")))
            parts.append(step_row("Apply:", math_box(
                f"f·g' + g·f' = {sym(f1)}·({sym(dg1)}) + {sym(g1)}·({sym(df1)})")))
            parts.append(divider())

    # ── So ────────────────────────────────────────────────────
    parts.append(step_row("So:", math_box(f"d/dx [{sym(expr)}] = {sym(result)}")))
    if sym(simp) != sym(result):
        parts.append(step_row("Simplified:", math_box(f"f'(x) = {sym(simp)}")))

    return "".join(parts)


def make_integral_steps(q, raw, expr, result, definite=False, lo=None, hi=None):
    rule_name, rule_formula = get_integral_rule(expr)
    parts = []

    parts.append(step_row("Rule:", rule_box(f"<strong>{rule_name}</strong><br>{rule_formula}")))
    parts.append(divider())

    label = f"∫ from {sym(lo)} to {sym(hi)} of {sym(expr)} dx" if definite else f"∫ {sym(expr)} dx"
    parts.append(step_row("Here:", math_box(label)))
    parts.append(divider())

    # Term-by-term
    try:
        terms = Add.make_args(expand(expr))
        if len(terms) > 1:
            rows = "".join(
                f'<div class="term-row"><span>∫ {sym(tm)} dx</span>'
                f'<span class="eq">= {sym(integrate(tm,x))}</span></div>'
                for tm in terms
            )
            parts.append(step_row("Term-by-term:", f'<div class="term-table">{rows}</div>'))
            parts.append(divider())
    except Exception:
        pass

    antideriv = integrate(expr, x)
    parts.append(step_row("Antiderivative:", math_box(f"F(x) = {sym(antideriv)}")))
    parts.append(divider())

    if definite:
        val_hi = antideriv.subs(x, hi)
        val_lo = antideriv.subs(x, lo)
        parts.append(step_row("Apply FTC:", math_box(
            f"F({sym(hi)}) − F({sym(lo)})"
        )))
        parts.append(step_row("Compute:", math_box(
            f"[{sym(antideriv)}] from {sym(lo)} to {sym(hi)}"
        )))
        parts.append(step_row("So:", math_box(f"= {sym(result)}")))
        try:
            num = float(result.evalf())
            parts.append(note_box(f"Numerical value ≈ {num:.6f}"))
        except Exception:
            pass
    else:
        parts.append(step_row("So:", math_box(f"∫ {sym(expr)} dx = {sym(result)} + C")))
        parts.append(note_box("C is the constant of integration"))

    return "".join(parts)


def make_limit_steps(q, raw, expr, point, result):
    parts = []
    parts.append(step_row("Goal:", rule_box(
        f"Find lim<sub>x→{sym(point)}</sub> [{sym(expr)}]")))
    parts.append(divider())
    parts.append(step_row("Here:", math_box(f"f(x) = {sym(expr)},  x → {sym(point)}")))
    parts.append(divider())
    parts.append(step_row("Step 1:", "<strong>Try direct substitution</strong>"))

    try:
        direct = expr.subs(x, point)
        if direct.is_finite and not direct.has(sp.zoo, sp.nan):
            parts.append(step_row("Substitute:", math_box(
                f"f({sym(point)}) = {sym(direct)}")))
            parts.append(step_row("So:", math_box(
                f"lim<sub>x→{sym(point)}</sub> [{sym(expr)}] = {sym(result)}")))
        else:
            parts.append(step_row("Result:", note_box("0/0 or ∞/∞ — indeterminate form")))
            parts.append(step_row("Step 2:", "<strong>Apply L'Hôpital's Rule or simplification</strong>"))
            parts.append(step_row("So:", math_box(
                f"lim<sub>x→{sym(point)}</sub> [{sym(expr)}] = {sym(result)}")))
    except Exception:
        parts.append(step_row("So:", math_box(
            f"lim<sub>x→{sym(point)}</sub> [{sym(expr)}] = {sym(result)}")))

    return "".join(parts)


def make_solve_steps(q, expr_str, result, lhs=None, rhs=None):
    parts = []

    if lhs is not None and rhs is not None:
        parts.append(step_row("Equation:", math_box(f"{sym(lhs)} = {sym(rhs)}")))
    else:
        parts.append(step_row("Expression:", math_box(f"{expr_str} = 0")))
    parts.append(divider())

    # Detect type
    try:
        combined = (lhs - rhs) if (lhs is not None and rhs is not None) else parse(expr_str)
        poly = sp.Poly(combined, x)
        deg = poly.degree()
        if deg == 1:
            parts.append(step_row("Type:", "<strong>Linear Equation  (ax + b = 0)</strong>"))
            a_c = poly.nth(1); b_c = poly.nth(0)
            parts.append(step_row("Coefficients:", math_box(f"a = {a_c},  b = {b_c}")))
            parts.append(step_row("Formula:", rule_box("x = −b / a")))
        elif deg == 2:
            coeffs = poly.all_coeffs()
            a_c, b_c, c_c = coeffs
            disc = b_c**2 - 4*a_c*c_c
            parts.append(step_row("Type:", "<strong>Quadratic Equation  (ax² + bx + c = 0)</strong>"))
            parts.append(step_row("Coefficients:", math_box(
                f"a = {sym(a_c)},  b = {sym(b_c)},  c = {sym(c_c)}")))
            parts.append(step_row("Discriminant:", math_box(
                f"Δ = b² − 4ac = ({sym(b_c)})² − 4({sym(a_c)})({sym(c_c)}) = {sym(disc)}")))
            parts.append(step_row("Formula:", rule_box(
                "x = (−b ± √Δ) / 2a")))
        elif deg == 3:
            parts.append(step_row("Type:", "<strong>Cubic Equation</strong>"))
        parts.append(divider())
    except Exception:
        pass

    parts.append(step_row("Working:", "<strong>Solve for x</strong>"))
    parts.append(divider())

    if isinstance(result, list):
        for i, sol in enumerate(result, 1):
            sol_html = f'<div class="solution-box">x<sub>{i}</sub> = {sym(sol)}'
            try:
                num = float(sol.evalf())
                sol_html += f'  &nbsp;≈ {num:.6f}'
            except Exception:
                pass
            sol_html += '</div>'
            parts.append(step_row(f"Solution {i}:", sol_html))
    else:
        parts.append(step_row("Solution:", f'<div class="solution-box">x = {sym(result)}</div>'))

    return "".join(parts)


def make_series_steps(q, raw, expr, point, n_terms, result):
    parts = []
    parts.append(step_row("Goal:", rule_box(
        f"Taylor/Maclaurin series of {sym(expr)} around x = {sym(point)}")))
    parts.append(divider())
    parts.append(step_row("Formula:", rule_box(
        "f(x) = f(a) + f'(a)(x−a) + f''(a)(x−a)²/2! + ···")))
    parts.append(divider())
    parts.append(step_row("Here:", math_box(f"f(x) = {sym(expr)},  a = {sym(point)}")))
    parts.append(divider())

    # Derivatives at point
    rows = ""
    for i in range(min(5, n_terms)):
        d = diff(expr, x, i)
        val = d.subs(x, sympify(point))
        prime = "'" * i
        rows += (f'<div class="term-row"><span>f{prime}({sym(point)})</span>'
                 f'<span class="eq">= {sym(val)}</span></div>')
    parts.append(step_row(f"Derivatives at x={point}:", f'<div class="term-table">{rows}</div>'))
    parts.append(divider())
    parts.append(step_row("Expansion:", math_box(str(result))))
    parts.append(note_box(f"Expanded to {n_terms} terms around x = {point}"))
    return "".join(parts)


def make_simplify_steps(q, raw, expr, result, operation='simplify'):
    parts = []
    parts.append(step_row("Expression:", math_box(sym(expr))))
    parts.append(divider())
    if operation == 'factor':
        parts.append(step_row("Method:", rule_box("Factor out common terms completely")))
        parts.append(step_row("Factored:", math_box(sym(result))))
    elif operation == 'expand':
        parts.append(step_row("Method:", rule_box("Distribute and expand all products")))
        parts.append(step_row("Expanded:", math_box(sym(result))))
    else:
        try:
            exp_form = expand(expr)
            parts.append(step_row("Expanded:", math_box(sym(exp_form))))
        except Exception:
            pass
        try:
            fac_form = factor(expr)
            if sym(fac_form) != sym(expr):
                parts.append(step_row("Factored:", math_box(sym(fac_form))))
        except Exception:
            pass
        parts.append(step_row("Simplified:", math_box(sym(result))))
    return "".join(parts)


def make_error_steps(question, error_msg):
    parts = []
    parts.append(step_row("⚠️ Error:", f'<div class="error-note">{error_msg}</div>'))
    parts.append(divider())
    parts.append(step_row("Correct format:", f"""<ul class="tips-list">
        <li>Use {code_inline('^')} for powers: {code_inline('x^2')}</li>
        <li>Use {code_inline('*')} for multiply: {code_inline('2*x')}</li>
        <li>Natural log: {code_inline('log(x)')} or {code_inline('ln(x)')}</li>
        <li>Trig: {code_inline('sin(x)')}, {code_inline('cos(x)')}, {code_inline('tan(x)')}</li>
        <li>Constant e: {code_inline('E')} or {code_inline('exp(x)')}</li>
    </ul>"""))
    parts.append(step_row("Examples:", f"""<ul class="tips-list">
        <li>{code_inline('derivative of x^3 + 2*x - 5')}</li>
        <li>{code_inline('integrate sin(x) * exp(x)')}</li>
        <li>{code_inline('solve 2*x^2 - 4*x - 6 = 0')}</li>
        <li>{code_inline('limit of sin(x)/x as x approaches 0')}</li>
        <li>{code_inline('taylor series of exp(x) 5 terms')}</li>
        <li>{code_inline('factor x^2 - 5*x + 6')}</li>
    </ul>"""))
    return "".join(parts)


# ══════════════════════════════════════════════════════════════
# CONVERSATIONAL HANDLER
# ══════════════════════════════════════════════════════════════
MATH_KEYWORDS = [
    'derivative','differentiate','diff','d/dx','integral','integrate','antiderivative',
    'limit','lim','approaches','series','taylor','maclaurin','solve','equation',
    'factor','expand','simplify','evaluate','compute','calculate','find x','root',
    'zero','polynomial','quadratic','linear','cubic','sin','cos','tan','log','sqrt',
    'exponential','expression','function','algebra','calculus'
]

DEFINITIONS = {
    'derivative': (
        "A derivative measures the instantaneous rate of change of a function.",
        [step_row("Definition:", rule_box("f'(x) = lim<sub>h→0</sub> [f(x+h) − f(x)] / h")),
         step_row("Example:", math_box("d/dx [x²] = 2x")),
         note_box("The derivative gives the slope of the tangent line at any point.")]
    ),
    'integral': (
        "An integral computes the area under a curve — the reverse of differentiation.",
        [step_row("Definition:", rule_box("∫ f(x) dx = F(x) + C  where F'(x) = f(x)")),
         step_row("Example:", math_box("∫ 2x dx = x² + C")),
         note_box("Connected to derivatives by the Fundamental Theorem of Calculus.")]
    ),
    'limit': (
        "A limit describes the value a function approaches as x gets arbitrarily close to a point.",
        [step_row("Definition:", rule_box("lim<sub>x→a</sub> f(x) = L")),
         step_row("Example:", math_box("lim<sub>x→0</sub> sin(x)/x = 1")),
         note_box("Limits are the foundation of calculus.")]
    ),
    'calculus': (
        "Calculus is the branch of mathematics that studies continuous change.",
        [step_row("Two branches:", f"""<ul class="tips-list">
            <li><strong>Differential Calculus</strong> — rates of change (derivatives)</li>
            <li><strong>Integral Calculus</strong> — accumulation of quantities (integrals)</li>
         </ul>"""),
         note_box("Both are unified by the Fundamental Theorem of Calculus.")]
    ),
    'product rule': (
        "The product rule is used to differentiate the product of two functions.",
        [step_row("Rule:", rule_box("d/dx [f(x)·g(x)] = f(x)·g'(x) + g(x)·f'(x)")),
         step_row("Example:", math_box("d/dx [x²·sin(x)] = x²·cos(x) + sin(x)·2x")),
         note_box("Remember: 'first times derivative of second + second times derivative of first'")]
    ),
    'chain rule': (
        "The chain rule differentiates composite functions.",
        [step_row("Rule:", rule_box("d/dx [f(g(x))] = f'(g(x)) · g'(x)")),
         step_row("Example:", math_box("d/dx [sin(x²)] = cos(x²) · 2x")),
         note_box("Identify the outer function f and inner function g.")]
    ),
    'quotient rule': (
        "The quotient rule differentiates the ratio of two functions.",
        [step_row("Rule:", rule_box("d/dx [f/g] = [g·f' − f·g'] / g²")),
         step_row("Example:", math_box("d/dx [sin(x)/x] = [x·cos(x) − sin(x)] / x²")),
         note_box("Remember: 'lo d-hi minus hi d-lo, over lo-squared'")]
    ),
    'power rule': (
        "The power rule is the most basic differentiation rule.",
        [step_row("Rule:", rule_box("d/dx [x<sup>n</sup>] = n·x<sup>n−1</sup>")),
         step_row("Examples:", f"""<ul class="tips-list">
             <li>d/dx [x³] = 3x²</li>
             <li>d/dx [x⁵] = 5x⁴</li>
             <li>d/dx [√x] = d/dx [x<sup>½</sup>] = ½x<sup>−½</sup></li>
         </ul>""")]
    ),
}

CHAT_RESPONSES = [
    (r'\b(hi|hello|hey|howdy|hiya)\b',
     "Hello! 👋 I'm your Math AI tutor. Ask me about derivatives, integrals, limits, series, or any algebra!",
     [step_row("I can solve:", f"""<ul class="tips-list">
        <li>Derivatives (chain/product/quotient rules shown)</li>
        <li>Integrals (indefinite &amp; definite)</li>
        <li>Limits (including L'Hôpital)</li>
        <li>Taylor / Maclaurin Series</li>
        <li>Equations (linear, quadratic, polynomial)</li>
        <li>Simplify / Factor / Expand</li>
     </ul>""")]),
    (r'\b(how are you|how do you do|how r u)\b',
     "I'm ready to crunch math! 🧮 What problem can I help you with?", []),
    (r'\b(thank|thanks|thank you|thx|ty)\b',
     "You're welcome! 😊 Ask me another math problem anytime.", []),
    (r'\b(bye|goodbye|see you|cya)\b',
     "Goodbye! Come back whenever you have a math problem. 👋", []),
    (r'\b(who are you|what are you|your name)\b',
     "I'm MathSolver AI — a symbolic math assistant. I provide step-by-step solutions with proper rules shown (Rule → Here → Working → So).", []),
    (r'\b(what can you (do|solve)|help|capabilities)\b',
     "I'm a symbolic math solver powered by SymPy.",
     [step_row("Try:", f"""<ul class="tips-list">
        <li>{code_inline('derivative of ln(1 + x^2)')}</li>
        <li>{code_inline('integrate x^2 * sin(x)')}</li>
        <li>{code_inline('solve x^2 - 5x + 6 = 0')}</li>
        <li>{code_inline('limit of (1+1/n)^n as n approaches oo')}</li>
        <li>{code_inline('taylor series of sin(x) 6 terms')}</li>
     </ul>""")]),
]


def handle_conversational(question):
    q = question.lower().strip()

    # Check definitions
    for keyword, (answer, step_list) in DEFINITIONS.items():
        if keyword in q and any(w in q for w in ['what is','define','explain','tell me about','what\'s']):
            return {
                'answer': answer,
                'steps': "".join(step_list),
                'conversational': True, 'success': True
            }

    # Check chat patterns
    for pattern, answer, step_list in CHAT_RESPONSES:
        if re.search(pattern, q):
            return {
                'answer': answer,
                'steps': "".join(step_list),
                'conversational': True, 'success': True
            }
    return None


def is_math(question):
    q = question.lower()
    return (any(kw in q for kw in MATH_KEYWORDS) or
            bool(re.search(r'[\d\+\-\*\/\^\=\(\)\\]', q)))


# ══════════════════════════════════════════════════════════════
# MAIN SOLVER
# ══════════════════════════════════════════════════════════════
def solve_math(question):
    q = question.strip()
    ql = q.lower()

    try:
        # ── DERIVATIVE ─────────────────────────────────────────
        if any(w in ql for w in ['derivative','differentiate','d/dx','d/dy']):
            raw = pull_expr(q, ['derivative','differentiate','d/dx','d/dy','of','wrt','with respect to x'])
            try:
                expr = parse(raw)
                res = diff(expr, x)
                return {'success': True, 'answer': sym(simplify(res)),
                        'steps': make_derivative_steps(q, raw, expr, res),
                        'operation': 'Derivative'}
            except Exception as e:
                return {'success': False, 'answer': None,
                        'steps': make_error_steps(q, f"Could not parse '{raw}': {e}"), 'operation': ''}

        # ── INTEGRAL ───────────────────────────────────────────
        elif any(w in ql for w in ['integral','integrate','antiderivative']):
            def_m = re.search(
                r'from\s+([-\d.pio]+|inf|infinity|-inf|-infinity)\s+to\s+([-\d.pio]+|inf|infinity|-inf|-infinity)',
                ql)
            raw = pull_expr(q, ['integral','integrate','antiderivative','definite','indefinite','of','dx'])
            if def_m:
                raw = re.sub(r'from\s+[\w.\-]+\s+to\s+[\w.\-]+', '', raw).strip()
            try:
                expr = parse(raw)
                if def_m:
                    def pb(s):
                        s = s.replace('infinity','oo').replace('inf','oo')
                        return sympify(s, locals=LOCALS)
                    lo, hi = pb(def_m.group(1)), pb(def_m.group(2))
                    res = integrate(expr, (x, lo, hi))
                    html = make_integral_steps(q, raw, expr, res, True, lo, hi)
                    return {'success': True, 'answer': sym(res), 'steps': html, 'operation': 'Definite Integral'}
                else:
                    res = integrate(expr, x)
                    html = make_integral_steps(q, raw, expr, res)
                    return {'success': True, 'answer': f"{sym(res)} + C", 'steps': html, 'operation': 'Integral'}
            except Exception as e:
                return {'success': False, 'answer': None,
                        'steps': make_error_steps(q, f"Could not parse '{raw}': {e}"), 'operation': ''}

        # ── LIMIT ──────────────────────────────────────────────
        elif any(w in ql for w in ['limit','lim','approaches','tends to']):
            pt_m = re.search(
                r'(?:x\s*(?:→|->|approaches?|tends?\s+to))\s*([-\d.]+|oo|inf|-inf|infinity|-infinity|pi|0)',
                ql)
            point = sympify('0')
            if pt_m:
                raw_pt = pt_m.group(1).replace('infinity','oo').replace('inf','oo')
                try: point = sympify(raw_pt, locals=LOCALS)
                except Exception: point = sympify('0')
            raw = pull_expr(q, ['limit','lim','of','as','x','approaches','tends','to'])
            raw = re.sub(r'x\s*(?:→|->|approaches?|tends?\s*to)\s*[\w.\-]+', '', raw)
            raw = re.sub(r'\s+', ' ', raw).strip()
            try:
                expr = parse(raw)
                res = limit(expr, x, point)
                return {'success': True, 'answer': sym(res),
                        'steps': make_limit_steps(q, raw, expr, point, res),
                        'operation': 'Limit'}
            except Exception as e:
                return {'success': False, 'answer': None,
                        'steps': make_error_steps(q, str(e)), 'operation': ''}

        # ── SERIES ─────────────────────────────────────────────
        elif any(w in ql for w in ['series','taylor','maclaurin']):
            n_m = re.search(r'(\d+)\s*terms?', ql)
            a_m = re.search(r'around\s+([\d.\-]+)', ql)
            n_terms = int(n_m.group(1)) if n_m else 6
            pt = float(a_m.group(1)) if a_m else 0
            raw = pull_expr(q, ['series','taylor','maclaurin','of','expand'])
            raw = re.sub(r'\d+\s*terms?', '', raw)
            raw = re.sub(r'around\s+[\d.]+', '', raw).strip()
            try:
                expr = parse(raw)
                res = series(expr, x, pt, n_terms)
                return {'success': True, 'answer': sym(res),
                        'steps': make_series_steps(q, raw, expr, pt, n_terms, res),
                        'operation': 'Series'}
            except Exception as e:
                return {'success': False, 'answer': None,
                        'steps': make_error_steps(q, str(e)), 'operation': ''}

        # ── SOLVE ──────────────────────────────────────────────
        elif any(w in ql for w in ['solve','equation','root','zero','find x']) or '=' in q:
            lhs_e = rhs_e = None
            if '=' in q:
                eq_part = re.sub(r'^(solve|equation|find|:)\s*', '', q, flags=re.IGNORECASE).strip()
                parts = eq_part.split('=', 1)
                try:
                    lhs_e = parse(parts[0])
                    rhs_e = parse(parts[1])
                    res = solve(Eq(lhs_e, rhs_e), x)
                    return {'success': True, 'answer': str(res),
                            'steps': make_solve_steps(q, f"{sym(lhs_e)} = {sym(rhs_e)}", res, lhs_e, rhs_e),
                            'operation': 'Equation'}
                except Exception as e:
                    return {'success': False, 'answer': None,
                            'steps': make_error_steps(q, str(e)), 'operation': ''}
            else:
                raw = pull_expr(q, ['solve','equation','find','root','zero','for','x'])
                try:
                    expr = parse(raw)
                    res = solve(expr, x)
                    return {'success': True, 'answer': str(res),
                            'steps': make_solve_steps(q, raw, res),
                            'operation': 'Solve'}
                except Exception as e:
                    return {'success': False, 'answer': None,
                            'steps': make_error_steps(q, str(e)), 'operation': ''}

        # ── FACTOR / EXPAND / SIMPLIFY ─────────────────────────
        elif any(w in ql for w in ['factor','expand','simplify']):
            op = 'factor' if 'factor' in ql else ('expand' if 'expand' in ql else 'simplify')
            raw = pull_expr(q, ['factor','expand','simplify','the','expression'])
            try:
                expr = parse(raw)
                res = factor(expr) if op=='factor' else (expand(expr) if op=='expand' else simplify(expr))
                return {'success': True, 'answer': sym(res),
                        'steps': make_simplify_steps(q, raw, expr, res, op),
                        'operation': op.title()}
            except Exception as e:
                return {'success': False, 'answer': None,
                        'steps': make_error_steps(q, str(e)), 'operation': ''}

        # ── GENERAL ────────────────────────────────────────────
        else:
            raw = clean(q)
            try:
                expr = parse(raw)
                res = simplify(expr)
                return {'success': True, 'answer': sym(res),
                        'steps': make_simplify_steps(q, raw, expr, res),
                        'operation': 'Simplify'}
            except Exception as e:
                return {'success': False, 'answer': None,
                        'steps': make_error_steps(q, str(e)), 'operation': ''}

    except Exception as e:
        logger.error(f"Solver error: {e}")
        return {'success': False, 'answer': None, 'steps': make_error_steps(q, str(e)), 'operation': ''}


# ══════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_msg = request.json.get('message', '').strip()
        logger.info(f"MSG: {user_msg}")
        if not user_msg:
            return jsonify({'answer': 'Please type a question.', 'steps': '', 'success': False})

        # 1. Conversational check
        conv = handle_conversational(user_msg)
        if conv:
            return jsonify(conv)

        # 2. Math solver
        if is_math(user_msg):
            result = solve_math(user_msg)
            result['conversational'] = False
            return jsonify(result)

        # 3. Gemini fallback for unknown inputs
        if GEMINI_AVAILABLE and client:
            try:
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=f"You are a math tutor. Answer helpfully and concisely: {user_msg}")
                return jsonify({'answer': resp.text, 'steps': '', 'conversational': True, 'success': True})
            except Exception:
                pass

        # 4. Generic fallback
        return jsonify({
            'answer': "I'm a math solver! Try a math question like:",
            'steps': make_error_steps(user_msg, "Input not recognized as a math problem."),
            'success': False, 'conversational': True
        })

    except Exception as e:
        logger.error(f"Route error: {e}")
        return jsonify({'answer': 'Server error.', 'steps': str(e), 'success': False})


if __name__ == '__main__':
    print("\n" + "═"*55)
    print("🚀  MathSolver AI  —  Ready")
    print("═"*55)
    print(f"🤖  Gemini : {'✅ On' if GEMINI_AVAILABLE else '⚠️  Off (built-in steps)'}")
    print("📚  Ops    : Derivative | Integral | Limit | Series")
    print("             Solve | Factor | Expand | Simplify")
    print("💬  Chat   : Greetings, definitions, math rules")
    print("═"*55 + "\n")
    app.run(debug=True, port=5000)