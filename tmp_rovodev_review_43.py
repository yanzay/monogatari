"""Engagement review for story 43."""
import json

with open('pipeline/engagement_baseline.json') as f: b = json.load(f)
b['reviews'] = [r for r in b['reviews'] if r.get('story_id') != 43]

review = {
    "story_id": 43,
    "title_jp": "鍵がありません",
    "title_en": "There Is No Key",
    "reviewer": "rovo-dev",
    "scores": {
        "hook": 4,
        "voice": 4,
        "originality": 4,
        "coherence": 4,
        "closure": 4
    },
    "average": 4.0,
    "approved": True,
    "highlights": [
        "First story in the library to express NEGATION — a structural milestone (50/100 of the cozy spectrum was previously inaccessible)",
        "ありません appears 3 times (title, s3, s5) so the introduction lands by repetition without parallel-construction worksheet feel",
        "The mystery shape is genre-perfect: search → frustration → quiet → realisation → relief → image",
        "Closer 静かな夜、小さい鍵です abandons subject-predicate altogether — pure appositive image"
    ],
    "weaknesses": [
        "s8-9 (静か → 思います) is a familiar 'narrator-thinks' beat that the library has used many times",
        "Frustration register stays gentle — 困ります is the strongest negative emotion, which fits the cozy voice but limits the negation's expressive range"
    ]
}

b['reviews'].append(review)
b['reviews'].sort(key=lambda r: r['story_id'])

with open('pipeline/engagement_baseline.json', 'w') as f:
    json.dump(b, f, ensure_ascii=False, indent=2)
print(f"Review written. Average: {review['average']} Approved: {review['approved']}")
