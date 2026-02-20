"""
Mode Detector for MyNextory Companion
Classifies user intent into 7 modes using keyword matching (no LLM call).

Modes:
- TEACH: learner wants to learn something new
- QUIZ: learner wants to test their knowledge
- REFLECT: learner is reflecting or expressing emotions
- PREPARE: learner wants to preview upcoming content
- CELEBRATE: learner completed something, wants acknowledgment
- CONNECT: learner wants to link concepts across lessons
- ESCALATE: distress language detected, route to human
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class Mode(str, Enum):
    TEACH = "teach"
    QUIZ = "quiz"
    REFLECT = "reflect"
    PREPARE = "prepare"
    CELEBRATE = "celebrate"
    CONNECT = "connect"
    ESCALATE = "escalate"


@dataclass
class ModeResult:
    mode: Mode
    confidence: float  # 0.0 - 1.0
    matched_keywords: List[str]
    fallback: bool = False  # True if no strong match, defaulted to TEACH


# Keyword patterns per mode, ordered by priority (ESCALATE first)
_MODE_PATTERNS = {
    Mode.ESCALATE: {
        'keywords': [
            "harm", "hopeless", "give up", "suicide", "self-harm",
            "kill myself", "end it all", "worthless", "no point",
            "can't go on", "want to die", "hurting myself",
        ],
        'weight': 1.0,  # Always high confidence when matched
    },
    Mode.QUIZ: {
        'keywords': [
            "quiz me", "test me", "check my knowledge", "ask me questions",
            "practice questions", "assessment", "how well do i know",
            "test my understanding", "quiz", "flashcard",
        ],
        'weight': 0.85,
    },
    Mode.REFLECT: {
        'keywords': [
            "i feel", "i'm feeling", "struggling with", "confused about",
            "frustrated", "overwhelmed", "anxious about", "worried",
            "i think i", "makes me think", "reminds me of",
            "in my experience", "personally", "i've noticed",
            "i realized", "it occurred to me",
        ],
        'weight': 0.8,
    },
    Mode.CELEBRATE: {
        'keywords': [
            "i finished", "i completed", "done with", "passed",
            "got it right", "nailed it", "finally understand",
            "made progress", "achievement", "milestone",
            "i did it", "accomplished",
        ],
        'weight': 0.85,
    },
    Mode.PREPARE: {
        'keywords': [
            "what's next", "upcoming", "preview", "prepare for",
            "what should i expect", "next lesson", "coming up",
            "get ready for", "before i start", "what will i learn",
        ],
        'weight': 0.8,
    },
    Mode.CONNECT: {
        'keywords': [
            "how does", "relate to", "connection between",
            "similar to", "different from", "compared to",
            "in common with", "link between", "ties into",
            "builds on", "related to",
        ],
        'weight': 0.8,
    },
    Mode.TEACH: {
        'keywords': [
            "tell me about", "explain", "what is", "what are",
            "how do", "how does", "can you teach", "help me understand",
            "describe", "define", "meaning of", "walk me through",
            "show me", "elaborate", "clarify",
        ],
        'weight': 0.7,
    },
}


class ModeDetector:
    """
    Classify user intent into one of 7 modes for the Companion.
    Uses keyword matching only (no LLM call needed).
    """

    def detect(self, query: str, context: Optional[dict] = None) -> ModeResult:
        """
        Classify a user query into a mode.

        Args:
            query: The user's message
            context: Optional context dict with keys like
                     'just_completed_lesson' (bool) for event-triggered modes

        Returns:
            ModeResult with mode, confidence, and matched keywords
        """
        query_lower = query.lower().strip()

        # Check for event-triggered modes first
        if context and context.get('just_completed_lesson'):
            return ModeResult(
                mode=Mode.CELEBRATE,
                confidence=0.9,
                matched_keywords=['completion_event'],
            )

        # Score each mode by keyword matches
        scores: List[Tuple[Mode, float, List[str]]] = []

        for mode, config in _MODE_PATTERNS.items():
            matched = []
            for keyword in config['keywords']:
                if keyword in query_lower:
                    matched.append(keyword)

            if matched:
                # More keyword matches = higher confidence, capped at weight
                match_ratio = min(len(matched) / 2.0, 1.0)
                confidence = config['weight'] * match_ratio
                scores.append((mode, confidence, matched))

        if not scores:
            # Default to TEACH with low confidence
            return ModeResult(
                mode=Mode.TEACH,
                confidence=0.3,
                matched_keywords=[],
                fallback=True,
            )

        # Sort by confidence descending
        scores.sort(key=lambda x: x[1], reverse=True)
        best_mode, best_confidence, best_keywords = scores[0]

        # ESCALATE always wins if detected, regardless of score
        for mode, conf, kws in scores:
            if mode == Mode.ESCALATE:
                return ModeResult(
                    mode=Mode.ESCALATE,
                    confidence=1.0,
                    matched_keywords=kws,
                )

        return ModeResult(
            mode=best_mode,
            confidence=round(best_confidence, 2),
            matched_keywords=best_keywords,
        )

    def detect_multi(
        self, query: str, context: Optional[dict] = None, threshold: float = 0.5
    ) -> List[ModeResult]:
        """
        Return all modes above threshold, sorted by confidence.
        Useful for blended responses (e.g., TEACH + CONNECT).
        """
        query_lower = query.lower().strip()
        results = []

        for mode, config in _MODE_PATTERNS.items():
            matched = [kw for kw in config['keywords'] if kw in query_lower]
            if matched:
                match_ratio = min(len(matched) / 2.0, 1.0)
                confidence = config['weight'] * match_ratio
                if confidence >= threshold:
                    results.append(ModeResult(
                        mode=mode,
                        confidence=round(confidence, 2),
                        matched_keywords=matched,
                    ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results if results else [
            ModeResult(mode=Mode.TEACH, confidence=0.3, matched_keywords=[], fallback=True)
        ]
