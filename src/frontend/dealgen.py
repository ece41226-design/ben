# -*- coding: utf-8 -*-
"""
Themed deal generator for Ben practice.

Rejection-sampling a random 52-card deal until it matches a target THEME,
then emitting it in Ben's deal-string format (seats N E S W, suits S.H.D.C,
ranks AKQJT98765432). South is always the hero/human seat.

This shapes the HANDS that make a given contract likely (HCP + shape + fit
heuristics) — it does NOT run the auction, so the exact final contract is
still up to Ben's bidding. That's the standard practice-generator approach:
fast, deterministic categories, no external AI.

Usage (module):
    from dealgen import generate
    deal_str, dealer, vuln, note = generate('3nt')
"""
import random as _random

SUITS = 'SHDC'                       # index 0..3
RANKS = 'AKQJT98765432'              # index 0..12  (A high)
HCP_VALUE = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}


def _fresh_deck():
    # card int = suit*13 + rank_index ; matches deck52.encode_card
    return list(range(52))


def _split(deck):
    """Return 4 hands (lists of card ints) in order N E S W."""
    _random.shuffle(deck)
    return [deck[0:13], deck[13:26], deck[26:39], deck[39:52]]


def _hand_to_str(hand):
    """13 card ints -> 'S.H.D.C' string (ranks high->low)."""
    suits = ['', '', '', '']
    for c in sorted(hand):
        suits[c // 13] += RANKS[c % 13]
    return '.'.join(suits)


def _hcp(hand):
    total = 0
    for c in hand:
        total += HCP_VALUE.get(RANKS[c % 13], 0)
    return total


def _suit_lengths(hand):
    """[spades, hearts, diamonds, clubs] lengths."""
    lengths = [0, 0, 0, 0]
    for c in hand:
        lengths[c // 13] += 1
    return lengths


def _is_balanced(lengths):
    """Balanced = no void/singleton, at most one doubleton (4333/4432/5332)."""
    doubletons = sum(1 for L in lengths if L == 2)
    if min(lengths) < 2:
        return False
    if doubletons > 1:
        return False
    if max(lengths) > 5:
        return False
    return True


def _major_fit(len_a, len_b):
    """Best combined major fit length between two hands (spades/hearts)."""
    return max(len_a[0] + len_b[0], len_a[1] + len_b[1])


def _best_fit(len_a, len_b):
    """Best combined fit across all four suits."""
    return max(len_a[i] + len_b[i] for i in range(4))


# --- theme predicates -------------------------------------------------------
# hands indexed N=0 E=1 S=2 W=3 ; South is the hero.

def _match(theme, hands):
    N, E, S, W = hands
    hcp = [_hcp(h) for h in hands]
    ln = [_suit_lengths(h) for h in hands]
    ns = hcp[0] + hcp[2]
    ew = hcp[1] + hcp[3]

    if theme == '1nt':
        # South opens a strong notrump: balanced 15-17.
        return _is_balanced(ln[2]) and 15 <= hcp[2] <= 17

    if theme == '3nt':
        # N-S balanced game values, no 8-card major fit -> notrump game.
        return (25 <= ns <= 28
                and _is_balanced(ln[2]) and _is_balanced(ln[0])
                and _major_fit(ln[2], ln[0]) <= 7
                and hcp[2] >= 10 and hcp[0] >= 10)

    if theme == 'game':
        # N-S game values WITH an 8+ major fit -> 4H/4S practice.
        return 25 <= ns <= 29 and _major_fit(ln[2], ln[0]) >= 8

    if theme == 'slam':
        # N-S small-slam values, with a decent fit or big balanced.
        return ns >= 33 and (_best_fit(ln[2], ln[0]) >= 8 or (_is_balanced(ln[2]) and _is_balanced(ln[0])))

    if theme == 'defense':
        # E-W hold game values -> they declare, South defends.
        return ew >= 25 and (_major_fit(ln[1], ln[3]) >= 8 or ew >= 27)

    if theme == 'partscore':
        # Competitive part-score zone: neither side has game values.
        return ns <= 24 and ew <= 24 and abs(ns - ew) <= 6

    if theme == 'preempt':
        # South holds a weak two / preempt: 5-10 HCP, a 6+ suit.
        return 5 <= hcp[2] <= 10 and max(ln[2]) >= 6

    # 'random' or unknown -> accept anything
    return True


# dealer/vuln chosen so the hero side is the one that opens where sensible.
_THEME_META = {
    '1nt':       ('S', 'None', '南家 15-17 均型开叫 1NT — 练开叫与应叫'),
    '3nt':       ('S', 'None', 'N-S 25-28 点均型无大牌配合 — 目标 3NT'),
    'game':      ('S', 'None', 'N-S 有 8+ 高花配合的成局牌 — 练 4H/4S'),
    'slam':      ('S', 'None', 'N-S 33+ 点 — 小满贯区间,练满贯叫'),
    'defense':   ('E', 'None', 'E-W 有成局实力做庄 — 你(南)练防守'),
    'partscore': ('N', 'None', '双方都无成局实力 — 争叫/部分定约区'),
    'preempt':   ('S', 'None', '南家弱牌带 6+ 长套 — 练阻击开叫'),
    'random':    ('N', 'None', '随机一副牌'),
}


def generate(theme, max_attempts=200000):
    """Return (deal_str, dealer, vuln, note). Falls back to random if the
    target is too rare to hit within max_attempts."""
    theme = (theme or 'random').lower()
    dealer, vuln, note = _THEME_META.get(theme, _THEME_META['random'])
    for _ in range(max_attempts):
        hands = _split(_fresh_deck())
        if _match(theme, hands):
            deal_str = ' '.join(_hand_to_str(h) for h in hands)
            return deal_str, dealer, vuln, note
    # fallback: give a random deal but flag it
    hands = _split(_fresh_deck())
    deal_str = ' '.join(_hand_to_str(h) for h in hands)
    return deal_str, dealer, vuln, note + '(未命中,已给随机牌)'


if __name__ == '__main__':
    import sys, time
    t = sys.argv[1] if len(sys.argv) > 1 else 'random'
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for _ in range(n):
        start = time.perf_counter()
        d, dl, v, note = generate(t)
        ms = (time.perf_counter() - start) * 1000
        print(f'[{t}] {ms:6.1f}ms  dealer={dl} vuln={v}')
        print(f'  N: {d.split()[0]}')
        print(f'  E: {d.split()[1]}')
        print(f'  S: {d.split()[2]}   <- 你')
        print(f'  W: {d.split()[3]}')
        print(f'  {note}')
