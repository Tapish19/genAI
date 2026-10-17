from collections import Counter
import math
import re
import statistics

def normalize(text):
    text = re.sub(r'\[\d+\]', '', text.lower())
    return ' '.join(re.findall(r'\b\w+\b', text))

def answer_metrics(prediction, expected):
    a, b = normalize(prediction).split(), normalize(expected).split()
    common = sum((Counter(a) & Counter(b)).values())
    f1 = 2 * common / (len(a) + len(b)) if a or b else 1.0
    return {'em': float(a == b), 'f1': f1}

def retrieval_metrics(ids, relevant, k):
    relevant = set(relevant)
    if not relevant:
        raise ValueError('Exclude unanswerable queries from positive retrieval metrics')
    flags = [float(x in relevant) for x in ids[:k]]
    dcg = sum(v / math.log2(i + 2) for i, v in enumerate(flags))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return {'recall_at_k': sum(flags) / len(relevant), 'hit_rate': float(any(flags)),
            'mrr': next((1 / (i + 1) for i, v in enumerate(flags) if v), 0),
            'ndcg_at_k': dcg / ideal, 'context_precision': sum(flags) / len(ids[:k]) if ids[:k] else 0}

def percentile(values, percent):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * percent / 100
    low = math.floor(index)
    high = math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)

def kappa(predicted, gold):
    if not gold:
        return None
    agreement = sum(a == b for a, b in zip(predicted, gold)) / len(gold)
    p, g = Counter(predicted), Counter(gold)
    chance = sum(p[x] * g[x] for x in set(p) | set(g)) / len(gold) ** 2
    return (agreement - chance) / (1 - chance) if chance < 1 else None

def mean(values):
    return statistics.mean(values) if values else None

def binary_validation(verdicts, gold):
    if not gold or len(verdicts) != len(gold):
        raise ValueError('Validation needs equal, nonempty verdict and gold lists')
    predictions = [v.get('passed', False) if v.get('status') == 'ok' else 'error' for v in verdicts]
    return {'agreement': sum(a == b for a,b in zip(predictions,gold)) / len(gold),
            'cohens_kappa': kappa(predictions,gold),
            'errors': sum(v.get('status') != 'ok' for v in verdicts)}

