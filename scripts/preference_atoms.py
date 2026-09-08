#!/usr/bin/env python3
from __future__ import annotations

import re
from collections import OrderedDict

ATOMIZER_VERSION = "2.2"


def _rule(key: str, label: str, polarity: int, strength: float, confidence: float, *patterns: str) -> dict:
    return {
        "key": key,
        "label": label,
        "polarity": 1 if polarity >= 0 else -1,
        "strength": float(strength),
        "confidence": float(confidence),
        "patterns": patterns,
    }


# These rules intentionally describe reading experience rather than genre nouns.  They are
# a deterministic first pass that works offline; the raw note remains the source of truth.
# More specific rules come first so a note can yield several useful, non-collapsed signals.
RULES = [
    _rule("pacing:fast", "빠른 전개", 1, 1.25, .92, r"전개.{0,5}(빠|빨라|빨랐)", r"빠르고.{0,8}전개", r"진행.{0,5}(빠|빨라|빨랐)"),
    _rule("hook:curiosity", "다음 내용이 궁금함", 1, 1.35, .94, r"궁금.{0,8}전개", r"다음.{0,8}궁금", r"계속.{0,8}(읽|보)고"),
    _rule("characters:breezy_energy", "경파한 캐릭터", 1, 1.20, .96, r"경파.{0,8}캐릭터", r"캐릭터.{0,8}경파"),
    _rule("protagonist:plausibility", "주인공 설득력", -1, 1.35, .96, r"주인공.{0,10}설득력.{0,8}(떨어|없|부족)", r"주인공.{0,10}(납득|이해).{0,8}(안|못)"),
    _rule("protagonist:plausibility", "주인공 설득력", 1, 1.25, .90, r"주인공.{0,10}설득력.{0,8}(있|좋)", r"주인공.{0,10}(납득|이해).{0,8}(됨|간다)"),
    _rule("prose:formal_honorific", "경어식 묘사", -1, 1.10, .96, r"경어.{0,8}(묘사|문체|서술).{0,8}(별로|싫|안 맞|불호)", r"경어.{0,8}(별로|불호)"),
    _rule("prose:surface_only", "겉만 그럴듯한 묘사", -1, 1.35, .96, r"그럴듯.{0,12}묘사.{0,8}(뿐|만)", r"묘사.{0,8}그럴듯.{0,8}(뿐|만)"),
    _rule("prose:vague", "애매한 묘사", -1, 1.10, .92, r"묘사.{0,8}애매", r"서술.{0,8}애매"),
    _rule("execution:amateurish", "초보티/미숙한 완성도", -1, 1.40, .98, r"초보티", r"초보.{0,6}(같|느낌)", r"전체.{0,8}어설프", r"완성도.{0,8}(낮|부족)"),
    _rule("execution:derivative", "기존 작품 흉내 느낌", -1, 1.15, .88, r"느낌을.{0,8}내려고", r"흉내.{0,8}(내|낸)", r"따라.{0,6}(한|하)"),
    _rule("core:fun", "핵심 장치 자체의 재미", -1, 1.35, .95, r"(게임|설정|소재).{0,10}재미.{0,6}(없|안)", r"핵심.{0,8}재미.{0,6}(없|안)"),
    _rule("core:fun", "핵심 장치 자체의 재미", 1, 1.25, .90, r"(게임|설정|소재).{0,10}재미.{0,6}(있|좋)", r"핵심.{0,8}재미.{0,6}(있|좋)"),
    _rule("execution:overall_strength", "전체적인 완성감", -1, .80, .62, r"전체적으로.{0,8}애매", r"전체.{0,8}(별로|미묘)"),
    _rule("execution:overall_strength", "전체적인 완성감", 1, .85, .62, r"전체적으로.{0,8}(좋|괜찮|탄탄)", r"전체.{0,8}완성도.{0,8}(좋|높)"),
    _rule("pacing:slow", "느린/늘어지는 전개", -1, 1.20, .92, r"전개.{0,8}(느리|느려|느렸|늘어|답답)", r"진행.{0,8}(느리|느려|느렸|늘어)"),
    _rule("pacing:fast", "빠른 전개", -1, 1.00, .82, r"전개.{0,8}너무.{0,4}빠", r"진행.{0,8}너무.{0,4}빠"),
    _rule("characters:distinctive", "캐릭터성이 선명함", 1, 1.15, .84, r"캐릭터.{0,8}(선명|확실|개성|매력)", r"인물.{0,8}(선명|개성|매력)"),
    _rule("characters:flat", "평면적인 캐릭터", -1, 1.15, .88, r"캐릭터.{0,8}(평면|밋밋|무매력)", r"인물.{0,8}(평면|밋밋)"),
    _rule("prose:polished", "문장/묘사 완성도", 1, 1.10, .84, r"(문체|문장|서술).{0,10}(좋|탄탄|깔끔|자연스)", r"묘사.{0,10}(탄탄|깔끔|자연스|섬세)", r"잘.{0,5}(쓰|읽히|읽힌|읽혔)"),
    _rule("prose:polished", "문장/묘사 완성도", -1, 1.10, .84, r"(문체|문장|서술).{0,10}(별로|어색|엉성|조악)", r"묘사.{0,10}(어색|엉성|조악)", r"글.{0,6}(못|어설프)"),
    _rule("worldbuilding:coherence", "세계관 정합성", 1, 1.10, .82, r"세계관.{0,8}(설득|탄탄|정합|촘촘)"),
    _rule("worldbuilding:coherence", "세계관 정합성", -1, 1.10, .82, r"세계관.{0,8}(허술|억지|붕괴|설득력.{0,5}없)"),
    _rule("system_rules:depth", "룰/시스템 운용 깊이", 1, 1.20, .84, r"(룰|시스템|규칙).{0,10}(정교|깊|잘.{0,4}활용|운용)"),
    _rule("system_rules:depth", "룰/시스템 운용 깊이", -1, 1.15, .84, r"(룰|시스템|규칙).{0,10}(허술|단순|억지|장식)"),
    _rule("premise:novelty", "소재/발상의 신선함", 1, 1.05, .80, r"(소재|발상|설정).{0,10}(신선|독특|새롭)"),
    _rule("premise:novelty", "소재/발상의 신선함", -1, 1.05, .80, r"(소재|발상|설정).{0,10}(뻔|흔하|진부)"),
    _rule("tone:distinctive", "서술 톤의 개성", 1, 1.05, .78, r"(톤|서술).{0,8}(개성|독특|확실)"),
    _rule("tone:distinctive", "서술 톤의 개성", -1, 1.05, .78, r"(톤|서술).{0,8}(밋밋|애매|흔하)"),
]


GENERIC_ASPECTS = {
    "문체": ("prose:quality", "문체/문장 만족도"),
    "문장": ("prose:quality", "문체/문장 만족도"),
    "묘사": ("prose:quality", "문체/문장 만족도"),
    "서술": ("prose:quality", "문체/문장 만족도"),
    "전개": ("pacing:quality", "전개 만족도"),
    "진행": ("pacing:quality", "전개 만족도"),
    "캐릭터": ("characters:quality", "캐릭터 만족도"),
    "인물": ("characters:quality", "캐릭터 만족도"),
    "주인공": ("protagonist:quality", "주인공 만족도"),
    "세계관": ("worldbuilding:quality", "세계관 만족도"),
    "시스템": ("system_rules:quality", "룰/시스템 만족도"),
    "규칙": ("system_rules:quality", "룰/시스템 만족도"),
    "룰": ("system_rules:quality", "룰/시스템 만족도"),
    "소재": ("premise:quality", "소재 만족도"),
    "설정": ("premise:quality", "설정 만족도"),
    "관계": ("relationships:quality", "관계성 만족도"),
    "로맨스": ("romance:quality", "로맨스 만족도"),
}

POSITIVE = re.compile(r"(좋|재미있|흥미|궁금|매력|자연스럽|탄탄|설득력.{0,3}있|마음에|잘 읽|잘읽)")
NEGATIVE = re.compile(r"(별로|재미.{0,3}없|재미없|애매|어설프|초보티|지루|뻔|억지|설득력.{0,3}(없|떨어|부족)|싫|불호|답답|밋밋|허술)")


def _evidence(note: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 18)
    end = min(len(note), match.end() + 18)
    return note[start:end].strip()[:120]


def analyze_note(note: str) -> dict:
    """Conservative, clause-local extraction. Unresolved language stays observable, not a vote."""
    text = str(note or "").strip()
    clauses = [x.strip() for x in re.split(
        r"[.!?。！？\n;]+|(?:하지만|다만|반면)|(?<=[고며데])\s+(?=(?:문체|문장|묘사|전개|진행|캐릭터|인물|주인공|세계관|로맨스|소재|설정)(?:은|는|이|가))", text
    ) if x.strip()]
    found = OrderedDict()
    unresolved = []
    for clause in clauses:
        # Double negation and quoted/hedged reports need a semantic decision; do not guess.
        if re.search(r"(?:건|것은|것이|게|다는)\s*아니|(?:없|떨어|안 되는).{0,16}아니", clause):
            unresolved.append({"text": clause, "reason": "negation_scope"})
            continue
        local = OrderedDict()
        negative_affect = bool(re.search(r"싫|불호|별로|안\s*맞|좋지\s*않|좋지는\s*않|매력(?:이|은|이란)?\s*없", clause))
        positive_affect = bool(re.search(r"좋|마음에|만족", clause)) and not negative_affect
        for rule in RULES:
            matches = [re.search(pattern, clause, re.IGNORECASE) for pattern in rule["patterns"]]
            match = next((x for x in matches if x), None)
            if not match:
                continue
            key, polarity = rule["key"], rule["polarity"]
            if key in {"pacing:fast", "pacing:slow", "characters:breezy_energy"}:
                if negative_affect or (key == "pacing:fast" and "너무" in clause and not positive_affect):
                    polarity = -1
                elif positive_affect:
                    polarity = 1
            if key == "prose:polished" and re.search(r"좋지(?:는)?\s*않", clause):
                polarity = -1
            if key == "characters:distinctive" and re.search(r"매력(?:이|은)?\s*없", clause):
                polarity = -1
            if key == "worldbuilding:coherence" and re.search(r"설득력.{0,4}없", clause):
                polarity = -1
            local[(key, polarity)] = {
                "key": key, "label": rule["label"], "polarity": polarity,
                "strength": rule["strength"], "confidence": rule["confidence"],
                "source": "note_rule", "evidence": clause,
            }
        # Inverted word order is the same pacing feature, not a generic satisfaction atom.
        for pattern, key, label in [(r"느린\s*(?:전개|진행)", "pacing:slow", "느린 전개"),
                                     (r"빠른\s*(?:전개|진행)", "pacing:fast", "빠른 전개")]:
            if re.search(pattern, clause):
                polarity = -1 if negative_affect else 1 if positive_affect or key == "pacing:fast" else -1
                local[(key, polarity)] = dict(key=key, label=label, polarity=polarity, strength=1.0,
                                              confidence=.85, source="note_rule", evidence=clause)
        if re.search(r"겉만.{0,12}그럴듯.{0,12}묘사", clause):
            local[("prose:surface_only", -1)] = dict(key="prose:surface_only", label="겉만 그럴듯한 묘사",
                polarity=-1, strength=1.2, confidence=.9, source="note_rule", evidence=clause)
        # A narrow prose complaint cannot also vote against all prose quality.
        if any(k.startswith("prose:") and k not in {"prose:polished", "prose:quality"} for k, _ in local):
            local = OrderedDict((ident, atom) for ident, atom in local.items() if ident[0] != "prose:polished")
        pos, neg = bool(POSITIVE.search(clause)), bool(NEGATIVE.search(clause)) or negative_affect
        if re.search(r"좋지(?:는)?\s*않|매력(?:이|은)?\s*없", clause):
            pos = False
        if not local and pos != neg:
            for token, (key, label) in GENERIC_ASPECTS.items():
                # Generic satisfaction is valid only for an explicit generic assessment.
                # An unknown specific modifier must not silently vote for a different axis.
                if re.search(re.escape(token)+r"(?:은|는|이|가)?\s*(?:(?:정말|아주|전체적으로)\s*)?(?:좋|별로|싫|마음에|재미|지루)",clause):
                    local[(key, 1 if pos else -1)] = dict(key=key, label=label, polarity=1 if pos else -1,
                        strength=.85, confidence=.68, source="note_clause", evidence=clause)
        if not local:
            unresolved.append({"text": clause, "reason": "unmapped_expression"})
        for ident, atom in local.items():
            found.setdefault(ident, atom)
    # One review gets at most one vote per dimension. Conflicting clauses abstain together.
    conflicting = {key for key, pol in found if (key, -pol) in found}
    for key in sorted(conflicting):
        unresolved.append({"text": " / ".join(v["evidence"] for (k, _), v in found.items() if k == key),
                           "reason": "conflicting_clauses", "atom": key})
    atoms = [v for (k, _), v in found.items() if k not in conflicting]
    # A complaint about a missing quality is dislike of its deficit, never dislike
    # of the positive quality. Candidate features describe presence of the named trait.
    deficits = {
        "protagonist:plausibility": ("protagonist:implausible", "주인공 설득력 부족"),
        "core:fun": ("core:unfun", "핵심 장치 재미 부족"),
        "execution:overall_strength": ("execution:weak", "전체 완성도 부족"),
        "characters:distinctive": ("characters:flat", "평면적인 캐릭터"),
        "prose:polished": ("prose:rough", "미숙한 문장/묘사"),
        "worldbuilding:coherence": ("worldbuilding:incoherent", "세계관 정합성 부족"),
        "system_rules:depth": ("system_rules:shallow", "피상적인 룰/시스템"),
        "premise:novelty": ("premise:derivative", "진부한 소재/발상"),
        "tone:distinctive": ("tone:flat", "밋밋한 서술 톤"),
    }
    normalized = OrderedDict()
    for atom in atoms:
        if atom["polarity"] < 0:
            if atom["key"] in deficits:
                atom["key"], atom["label"] = deficits[atom["key"]]
            elif atom["key"].endswith(":quality"):
                atom["key"] = atom["key"].replace(":quality", ":quality_deficit")
                atom["label"] += " 부족"
        normalized.setdefault((atom["key"], atom["polarity"]), atom)
    return {"atoms": list(normalized.values()), "unresolved": unresolved, "atomizer_version": ATOMIZER_VERSION}


def extract_note_atoms(note: str) -> list[dict]:
    return analyze_note(note)["atoms"]


def atom_display(atom: dict) -> str:
    sign = "+" if int(atom.get("polarity") or 0) > 0 else "−"
    return f"{atom.get('label') or atom.get('key')} {sign}"
