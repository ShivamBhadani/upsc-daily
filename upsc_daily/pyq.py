"""UPSC Previous Year Question (PYQ) style model.

Everything the generator knows about *how* UPSC frames a question lives here:
the recurring Prelims formats and their share of a modern paper, the subject
weightage seen in recent years, the trend notes that separate a 2013-style
factual question from a 2023-style elimination-proof one, and the option
templates the Commission actually uses.

The same tables drive both the LLM prompt and the offline template generator,
so the two backends produce papers that look alike.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Format:
    """One recurring Prelims question shape."""

    key: str
    name: str
    share: int              # rough % of a modern Prelims paper
    options: list[str]      # canonical option set, or [] when contextual
    blueprint: str
    exemplar: str


FORMATS: list[Format] = [
    Format(
        key="how_many_statements",
        name="Statement counting",
        share=22,
        options=["Only one", "Only two", "Only three", "All four"],
        blueprint=(
            "Give 3-4 short factual statements about the topic, then ask "
            "'How many of the above statements are correct?'. Counting kills "
            "the partial-knowledge shortcut, which is exactly why UPSC leans on it."
        ),
        exemplar=(
            "UPSC 2023: 'Consider the following statements regarding the Digital India "
            "Land Records Modernization Programme... How many of the statements given "
            "above are correct?' — Only one / Only two / All three / None"
        ),
    ),
    Format(
        key="statements_which_correct",
        name="Which statement(s) is/are correct",
        share=20,
        options=["1 only", "2 only", "Both 1 and 2", "Neither 1 nor 2"],
        blueprint=(
            "Two statements, ask which is/are correct. The classic workhorse. "
            "Statements must be independently verifiable, not opinions."
        ),
        exemplar=(
            "UPSC 2022: 'With reference to the Indian economy, consider the following "
            "statements... Which of the statements given above is/are correct?'"
        ),
    ),
    Format(
        key="statements_three",
        name="Three-statement combination",
        share=12,
        options=["1 and 2 only", "2 and 3 only", "1 and 3 only", "1, 2 and 3"],
        blueprint=(
            "Three statements with combination options. Never let one obviously "
            "false statement eliminate three options — vary which statement is wrong."
        ),
        exemplar=(
            "UPSC 2021: 'Consider the following statements about the Cabinet Secretariat... "
            "Which of the statements given above is/are correct?'"
        ),
    ),
    Format(
        key="pairs_matched",
        name="Correctly matched pairs",
        share=12,
        options=["Only one pair", "Only two pairs", "Only three pairs", "All four pairs"],
        blueprint=(
            "Present 3-4 pairs (term : description, species : habitat, scheme : ministry, "
            "report : publishing body) and ask how many are correctly matched. "
            "Descriptions must be substantive, never one-word."
        ),
        exemplar=(
            "UPSC 2023: 'Consider the following pairs — Regions sometimes mentioned in "
            "news : Country. How many of the above pairs are correctly matched?'"
        ),
    ),
    Format(
        key="best_describes",
        name="Best describes the term",
        share=12,
        options=[],
        blueprint=(
            "'With reference to X, which one of the following best describes / "
            "what is the most likely implication?' Four full-sentence options, all "
            "plausible, only one precisely right. This is the flagship conceptual format: "
            "the news supplies the trigger word, the syllabus supplies the answer."
        ),
        exemplar=(
            "UPSC 2020: 'With reference to the current trends in the cure of tuberculosis, "
            "consider the following statements' / UPSC 2019: 'Which one of the following "
            "best describes the term Merchant Discount Rate?'"
        ),
    ),
    Format(
        key="statement_i_ii",
        name="Statement-I / Statement-II",
        share=8,
        options=[
            "Both Statement-I and Statement-II are correct and Statement-II is the correct explanation for Statement-I",
            "Both Statement-I and Statement-II are correct but Statement-II is not the correct explanation for Statement-I",
            "Statement-I is correct but Statement-II is incorrect",
            "Statement-I is incorrect but Statement-II is correct",
        ],
        blueprint=(
            "A claim plus a candidate reason. Test both truth values *and* whether "
            "the second really explains the first. Introduced in force from 2022."
        ),
        exemplar=(
            "UPSC 2023: 'Statement-I: India accounts for 3.2% of global export of goods. "
            "Statement-II: Many countries have imposed customs duties...'"
        ),
    ),
    Format(
        key="context_application",
        name="Implication / application",
        share=8,
        options=[],
        blueprint=(
            "Give a policy change or event, then ask for its most likely consequence, "
            "or list 3-4 candidate outcomes and ask which would follow. Rewards "
            "cause-effect reasoning over recall."
        ),
        exemplar=(
            "UPSC 2021: 'If the RBI decides to adopt an expansionist monetary policy, "
            "which of the following would it not do?'"
        ),
    ),
    Format(
        key="sequence_odd",
        name="Sequence / odd-one-out",
        share=6,
        options=[],
        blueprint=(
            "Chronological ordering, north-to-south geographic ordering, or 'which one "
            "of the following is not...'. Use sparingly — roughly one or two per paper."
        ),
        exemplar=(
            "UPSC 2018: 'Consider the following events... arrange in chronological order.'"
        ),
    ),
]

FORMAT_BY_KEY = {f.key: f for f in FORMATS}

# Approximate Prelims GS-I weightage of the last several papers.
SUBJECT_WEIGHTS: dict[str, int] = {
    "Polity & Governance": 15,
    "Economy": 16,
    "Environment & Ecology": 15,
    "Science & Technology": 12,
    "History, Art & Culture": 13,
    "Geography": 11,
    "International Relations": 8,
    "Social Issues & Schemes": 10,
}

TRENDS: list[str] = [
    "News is the trigger, the syllabus is the answer. Never ask 'what happened on "
    "which date' — ask about the institution, law, ecology, economics or geography "
    "the news exposes.",
    "Counting formats ('How many of the above are correct?', 'How many pairs are "
    "correctly matched?') have grown sharply since 2023 because they defeat "
    "partial-elimination. Make them a fifth of the paper.",
    "Statements are short, factual and independently checkable — no 'may', 'often', "
    "'is considered important'. Ambiguity is a flaw, not a difficulty setting.",
    "Distractors must be near-misses: the wrong ministry, the neighbouring year of "
    "enactment, the sister scheme, a species from an adjacent habitat, a similar "
    "sounding index by a different publisher.",
    "Static-current fusion. A news item on a Ramsar site becomes a question on the "
    "Ramsar Convention criteria; an RBI announcement becomes a question on monetary "
    "transmission. Anchor at least half the paper to static syllabus concepts.",
    "Institutional detail is prized: who publishes a report, which ministry runs a "
    "scheme, which article/section applies, statutory vs constitutional vs executive body.",
    "Environment and Economy together carry roughly a third of the paper; keep them "
    "the two largest blocks.",
    "Difficulty comes from precision, not obscurity. A question nobody can attempt "
    "is a bad question; the correct answer must be derivable by a well-prepared "
    "candidate who reasons carefully.",
    "Negative marking is one-third, so options should reward informed elimination "
    "rather than punish it randomly.",
    "Avoid 'None of the above' and avoid making the longest option the answer — both "
    "are tells the Commission does not leave.",
]

# The line UPSC prints after the statements/pairs block. Used when a generated
# stem stops at the colon, so the question always closes with its interrogative.
CLOSING_LINE: dict[str, str] = {
    "how_many_statements": "How many of the above statements are correct?",
    "statements_which_correct": "Which of the statements given above is/are correct?",
    "statements_three": "Which of the statements given above is/are correct?",
    "pairs_matched": "How many of the pairs given above are correctly matched?",
    "sequence_odd": "Select the correct answer using the code given below.",
    "context_application": "Select the correct answer using the code given below.",
}


def closing_line(qtype: str, stem: str) -> str:
    """The interrogative to print after the statements, if the stem lacks one."""
    if stem.rstrip().endswith("?"):
        return ""
    return CLOSING_LINE.get(qtype, "")


MAINS_DIRECTIVES: list[str] = [
    "Discuss", "Examine", "Critically examine", "Analyse", "Critically analyse",
    "Evaluate", "Elucidate", "Comment", "Substantiate", "To what extent",
]

MAINS_PAPERS: dict[str, str] = {
    "GS-I": "Society, geography, history, art and culture",
    "GS-II": "Polity, constitution, governance, social justice, international relations",
    "GS-III": "Economy, agriculture, environment, science and technology, security, disaster management",
    "GS-IV": "Ethics, integrity and aptitude — case-study or applied-ethics framing",
}


def style_guide() -> str:
    """Render the PYQ model as prompt text for the LLM backends."""
    lines: list[str] = []
    lines.append("UPSC CIVIL SERVICES PRELIMS — QUESTION STYLE MODEL (derived from PYQ patterns)")
    lines.append("")
    lines.append("FORMAT MIX (target share of the set):")
    for f in FORMATS:
        lines.append(f"  [{f.key}] {f.name} — about {f.share}%")
        lines.append(f"      How: {f.blueprint}")
        lines.append(f"      PYQ reference: {f.exemplar}")
        if f.options:
            lines.append(f"      Canonical options: {f.options}")
        lines.append("")
    lines.append("SUBJECT WEIGHTAGE (target share of the set):")
    for s, w in SUBJECT_WEIGHTS.items():
        lines.append(f"  {s}: {w}%")
    lines.append("")
    lines.append("TRENDS AND RULES THE COMMISSION FOLLOWS:")
    for i, t in enumerate(TRENDS, 1):
        lines.append(f"  {i}. {t}")
    lines.append("")
    lines.append("MAINS DIRECTIVE WORDS: " + ", ".join(MAINS_DIRECTIVES))
    lines.append("MAINS PAPERS: " + "; ".join(f"{k} = {v}" for k, v in MAINS_PAPERS.items()))
    return "\n".join(lines)


def target_format_plan(count: int) -> list[str]:
    """Spread `count` questions across formats in PYQ-like proportion."""
    plan: list[str] = []
    for f in FORMATS:
        n = round(count * f.share / 100)
        plan.extend([f.key] * n)
    while len(plan) < count:
        plan.append("statements_which_correct")
    return plan[:count]


def target_subject_plan(count: int) -> list[str]:
    """Spread `count` questions across subjects in PYQ-like proportion."""
    plan: list[str] = []
    for s, w in SUBJECT_WEIGHTS.items():
        plan.extend([s] * round(count * w / 100))
    while len(plan) < count:
        plan.append("Economy")
    return plan[:count]
