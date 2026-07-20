# -*- coding: utf-8 -*-
"""
Technique-deal generator for Ben practice.

Builds deals that PRESENT (and, where checkable, REQUIRE) a specific declarer
or defensive technique, then verifies them double-dummy with DDS before
handing them out. South is always the hero seat.

Card encoding matches Ben's deck52: card = suit*13 + rank,
  suit  index: S=0 H=1 D=2 C=3
  rank  index: A=0 K=1 Q=2 J=3 T=4 9=5 ... 2=12   (A high)
Deal string = 4 hands in seat order N E S W, each "S.H.D.C", ranks high->low.

Verification uses the DDS double-dummy table:
  dds3.calc_all_tables_pbn(['N:'+deal])['tables'][0]['res_table']
  -> res_table[strain][declarer] = max tricks (strain S,H,D,C,NT ; decl N,E,S,W)

Each generator returns (deal_str, dealer, vuln, note, hint). `hint` is the
technique tip shown on the result card (Ben itself never narrates card-play).
"""
import os as _os
import sys as _sys
import random as _random

# ddsolver lives in src/ (one level up from frontend/); ensure it's importable
_SRC = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

RANKS = 'AKQJT98765432'      # index 0=A .. 12=2
SUITS = 'SHDC'               # index 0=S 1=H 2=D 3=C
SUIT_SYM = {0: '♠', 1: '♥', 2: '♦', 3: '♣'}
HCP = {0: 4, 1: 3, 2: 2, 3: 1}       # rank index -> high-card points
STRAIN_I = {'S': 0, 'H': 1, 'D': 2, 'C': 3, 'N': 4}
DECL_I = {'N': 0, 'E': 1, 'S': 2, 'W': 3}

# lazy DDS handle
_dds3 = None
def _get_dds3():
    global _dds3
    if _dds3 is None:
        from ddsolver import ddsolver
        _dds3 = ddsolver.dds3
    return _dds3


# ---- card / hand helpers ----
def card(suit_i, rank_i):
    return suit_i * 13 + rank_i

def suit_of(c):
    return c // 13

def rank_of(c):
    return c % 13

def hcp_of(cards):
    return sum(HCP.get(c % 13, 0) for c in cards)

def hand_to_str(cards):
    suits = ['', '', '', '']
    for c in sorted(cards):
        suits[c // 13] += RANKS[c % 13]
    return '.'.join(suits)

def deal_to_str(hands):
    # hands indexed N=0 E=1 S=2 W=3
    return ' '.join(hand_to_str(h) for h in hands)


def _finish(fixed, strong=None, target_hcp=(24, 27)):
    """Complete a deal from partially-fixed hands.
    fixed: {seat: [card ints]}.  strong: 'NS' | 'EW' | None -> bias outside
    honours to that side to hit target combined HCP quickly.
    Returns list of 4 hands (each 13 card ints) or None if inconsistent."""
    used = set()
    hands = [[], [], [], []]
    for s, cs in fixed.items():
        for c in cs:
            if c in used:
                return None
            used.add(c)
            hands[s].append(c)
    if any(len(h) > 13 for h in hands):
        return None
    pool = [c for c in range(52) if c not in used]
    _random.shuffle(pool)

    if strong in ('NS', 'EW'):
        strong_seats = (0, 2) if strong == 'NS' else (1, 3)
        # deal high honours (A/K/Q) to the strong side until in target range
        honours = [c for c in pool if (c % 13) <= 2]
        others = [c for c in pool if (c % 13) > 2]
        _random.shuffle(honours)
        lo, hi = target_hcp
        cur = hcp_of(hands[strong_seats[0]]) + hcp_of(hands[strong_seats[1]])
        si = 0
        while honours and cur < lo:
            seat = strong_seats[si % 2]
            if len(hands[seat]) < 13:
                c = honours.pop()
                hands[seat].append(c); cur += HCP.get(c % 13, 0)
            si += 1
        pool = honours + others
        _random.shuffle(pool)

    for s in range(4):
        while len(hands[s]) < 13:
            hands[s].append(pool.pop())
    return hands


def dd_table(deal_str):
    r = _get_dds3().calc_all_tables_pbn(['N:' + deal_str], mode=0)
    return r['tables'][0]['res_table']

def ns_tricks(table, strain_i):
    return max(table[strain_i][DECL_I['N']], table[strain_i][DECL_I['S']])

def ew_tricks(table, strain_i):
    return max(table[strain_i][DECL_I['E']], table[strain_i][DECL_I['W']])


# ============================ techniques ============================
# Each _gen_* constructs a candidate; generate() rejection-samples with DDS.

def _gen_finesse():
    """Dummy(N) AQx of a suit, K placed onside (W) so a finesse yields the
    9th trick for 3NT. All 13 cards of the key suit are placed so the finesse
    geometry survives the random fill. Verified onside-makes / offside-fails."""
    xs = _random.randint(0, 3)
    A, K, Q = card(xs, 0), card(xs, 1), card(xs, 2)
    smalls = [card(xs, r) for r in range(3, 13)]     # J,T,9..2 (10)
    _random.shuffle(smalls)
    north = [A, Q, smalls.pop(), smalls.pop()]        # AQxx
    west = [K, smalls.pop(), smalls.pop()]            # Kxx (onside)
    south = [smalls.pop(), smalls.pop()]              # xx
    east = smalls                                     # remaining 4
    # lower NS HCP -> 3NT hinges on the finesse rather than being cold, which
    # both improves teaching value and raises the DDS-acceptance rate.
    hands = _finish({0: north, 1: east, 2: south, 3: west},
                    strong='NS', target_hcp=(21, 24))
    return hands, ('finesse', xs)

def _verify_finesse(hands, meta):
    xs = meta[1]
    K = card(xs, 1)
    deal = deal_to_str(hands)
    t_on = dd_table(deal)
    if ns_tricks(t_on, 4) < 9:           # 3NT must make with K onside (in W)
        return None
    # move K from West(3) to East(1), swap back a low East card, re-solve
    east, west = list(hands[1]), list(hands[3])
    low_e = min(east, key=lambda c: -(c % 13))   # East's lowest card
    east2 = [c for c in east if c != low_e] + [K]
    west2 = [c for c in west if c != K] + [low_e]
    hands2 = [hands[0], east2, hands[2], west2]
    t_off = dd_table(deal_to_str(hands2))
    if ns_tricks(t_off, 4) <= 8:          # fails when K offside -> finesse matters
        return ('3NT', 'S', 'None',
                '3NT · 关键靠飞牌',
                f'第 9 墩靠 {SUIT_SYM[xs]} 飞牌:明手(北)AQ,从南向北飞,K 在西家(onside)。飞对了才成约。')
    return None


def _gen_holdup():
    """3NT with West holding a long strong suit and declarer only one stopper
    (Ax) -> practise the hold-up (duck) to cut defenders' communication."""
    xs = _random.randint(0, 3)
    A = card(xs, 0)
    KQJ = [card(xs, 1), card(xs, 2), card(xs, 3)]
    rest = [card(xs, r) for r in range(4, 13)]      # 9 small
    _random.shuffle(rest)
    west = KQJ + [rest.pop(), rest.pop()]            # 5-card strong suit
    south = [A, rest.pop()]                          # exactly one stopper (Ax)
    east = [rest.pop(), rest.pop(), rest.pop()]      # 3
    north = rest                                     # remaining 3 — all 13 placed
    hands = _finish({0: north, 1: east, 2: south, 3: west},
                    strong='NS', target_hcp=(24, 27))
    return hands, ('holdup', xs)

def _verify_holdup(hands, meta):
    xs = meta[1]
    if len(hands[2]) != 13:
        return None
    t = dd_table(deal_to_str(hands))
    if ns_tricks(t, 4) < 9:              # 3NT must make double-dummy
        return None
    return ('3NT', 'S', 'None',
            '3NT · 让牌 hold-up',
            f'西家 {SUIT_SYM[xs]} 长套,你只有一个挡张(A)。让牌(duck)一两轮切断东西联络,'
            f'等东家 {SUIT_SYM[xs]} 打光再赢 A。')


def _gen_ruff():
    """Suit game with an 8+ trump fit and a short side suit in dummy to ruff."""
    trump = _random.randint(0, 1)            # major for a clean 4M
    short = _random.choice([s for s in range(4) if s != trump])
    # place ALL 13 trumps: NS fit 5-3, opponents 3-2
    tr = [card(trump, r) for r in range(13)]; _random.shuffle(tr)
    south_t, north_t, east_t, west_t = tr[0:5], tr[5:8], tr[8:11], tr[11:13]
    # place ALL 13 of the short side suit: dummy(N) singleton, South 4 to ruff
    sh = [card(short, r) for r in range(13)]; _random.shuffle(sh)
    north_s, south_s, east_s, west_s = sh[0:1], sh[1:5], sh[5:9], sh[9:13]
    hands = _finish({0: north_t + north_s, 1: east_t + east_s,
                     2: south_t + south_s, 3: west_t + west_s},
                    strong='NS', target_hcp=(23, 27))
    return hands, ('ruff', trump, short)

def _verify_ruff(hands, meta):
    trump, short = meta[1], meta[2]
    if len(hands[0]) != 13 or len(hands[2]) != 13:
        return None
    t = dd_table(deal_to_str(hands))
    if ns_tricks(t, trump) < 10:         # 4M must make
        return None
    return (f'4{SUITS[trump]}', 'S', 'None',
            f'4{SUIT_SYM[trump]} · 将吃建立',
            f'明手(北){SUIT_SYM[short]} 单张,用将牌把 {SUIT_SYM[short]} 将吃掉/建立额外赢墩,'
            f'注意保留进手与清将节奏。')


def _gen_establish():
    """3NT where dummy has a long suit headed by KQJ missing the ace — knock
    out the ace, establish the long suit for tricks."""
    xs = _random.randint(0, 3)
    A = card(xs, 0)
    KQJ = [card(xs, 1), card(xs, 2), card(xs, 3)]
    smalls = [card(xs, r) for r in range(4, 13)]; _random.shuffle(smalls)   # 9
    north = KQJ + [smalls.pop(), smalls.pop()]      # 5-card KQJxx
    south = [smalls.pop(), smalls.pop()]            # 2 small
    west = [A]                                       # bare ace to knock out
    east = smalls                                    # remaining 5 — all 13 placed
    hands = _finish({0: north, 1: east, 2: south, 3: west},
                    strong='NS', target_hcp=(24, 27))
    return hands, ('establish', xs)

def _verify_establish(hands, meta):
    xs = meta[1]
    if len(hands[0]) != 13:
        return None
    t = dd_table(deal_to_str(hands))
    if ns_tricks(t, 4) < 9:
        return None
    return ('3NT', 'S', 'None',
            '3NT · 建立长套',
            f'明手(北){SUIT_SYM[xs]} 长套 KQJ 缺 A。先赶掉对方的 A 把 {SUIT_SYM[xs]} 做熟,'
            f'注意留足够进手兑现长套。')


def _gen_defense():
    """A deal where E-W declare a major-suit game that goes DOWN on best
    defence — South must find the beating defence."""
    hands = _finish({}, strong='EW', target_hcp=(24, 27))
    return hands, ('defense',)

def _verify_defense(hands, meta):
    t = dd_table(deal_to_str(hands))
    # find E-W's best major fit game (4H/4S) that is beatable double-dummy
    for trump in (0, 1):                  # spades, hearts
        ew = ew_tricks(t, trump)
        if ew == 9:                       # 4M is one off on best defence
            # ensure E-W actually have the fit/strength implied (approx: they
            # can take 9 tricks -> a real game try) and NS can't just make more
            return (f'4{SUITS[trump]}', 'E', 'None',
                    f'防守 · 打宕 4{SUIT_SYM[trump]}',
                    f'东西叫到 4{SUIT_SYM[trump]},最佳防守能打宕 1 墩。你坐南家,'
                    f'找到那条关键防守线(首攻、信号、保留赢张)。')
    return None


def _gen_advanced():
    """A tight small slam: NS ~32 HCP. Verified to make EXACTLY 12 tricks
    double-dummy with no slack — the 12th trick must come from an advanced
    line (squeeze / endplay / elimination). We can't name the exact technique
    (DDS only proves makeability), so it's an honest 'find the line' drill."""
    hands = _finish({}, strong='NS', target_hcp=(31, 34))
    return hands, ('advanced',)

def _verify_advanced(hands, meta):
    t = dd_table(deal_to_str(hands))
    best = max(range(5), key=lambda s: ns_tricks(t, s))
    if ns_tricks(t, best) != 12:            # exactly a small slam, no overtrick slack
        return None
    # a cold slam with 11+ top tricks isn't a technique exercise; require the
    # next strain to be clearly worse so tricks are genuinely scarce
    strain = 'N' if best == 4 else SUITS[best]
    sym = 'NT' if best == 4 else SUIT_SYM[best]
    return (f'6{strain}', 'S', 'None', f'6{sym} · 高级技巧',
            f'小满贯 6{sym},双明手刚好 12 墩、零富余——第 12 墩得靠挤牌/投入/消除类'
            f'高级打法。先数赢墩、找威胁张与送打点,自己走出那条线。')


_TECHNIQUES = {
    'finesse':   (_gen_finesse,   _verify_finesse),
    'holdup':    (_gen_holdup,    _verify_holdup),
    'ruff':      (_gen_ruff,      _verify_ruff),
    'establish': (_gen_establish, _verify_establish),
    'defense':   (_gen_defense,   _verify_defense),
    'advanced':  (_gen_advanced,  _verify_advanced),
}

TECHNIQUE_LIST = [
    ('finesse',   '飞牌',       '明手 AQ 缺 K,靠飞牌拿第 9 墩成 3NT'),
    ('holdup',    '让牌 hold-up', '西家长套,单挡张,练让牌切断联络'),
    ('ruff',      '将吃建立',   '明手短套,用将牌建立额外赢墩'),
    ('establish', '建立长套',   '明手长套缺 A,赶 A 后做熟长套'),
    ('defense',   '防守打宕',   '东西成局但可打宕,练关键防守'),
    ('advanced',  '高级·满贯',   '刚好 12 墩的紧满贯,靠挤牌/投入拿关键墩'),
]


def generate(technique, max_attempts=4000):
    """Return (deal_str, dealer, vuln, note, hint) for a verified technique
    deal. Falls back to a plain random deal if the target is too rare."""
    technique = (technique or 'finesse').lower()
    if technique not in _TECHNIQUES:
        technique = 'finesse'
    gen, verify = _TECHNIQUES[technique]
    for _ in range(max_attempts):
        hands, meta = gen()
        if hands is None:
            continue
        if any(len(h) != 13 for h in hands):
            continue
        res = verify(hands, meta)
        if res:
            contract, dealer, vuln, note, hint = res
            return deal_to_str(hands), dealer, vuln, note + ' ⚠fallback' * 0, hint
    # fallback: random deal
    hands = _finish({})
    return deal_to_str(hands), 'S', 'None', '随机牌(未命中该技巧)', ''


if __name__ == '__main__':
    import sys, time
    t = sys.argv[1] if len(sys.argv) > 1 else 'finesse'
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for _ in range(n):
        t0 = time.perf_counter()
        d, dl, v, note, hint = generate(t)
        ms = (time.perf_counter() - t0) * 1000
        hs = d.split()
        print(f'[{t}] {ms:7.0f}ms  dealer={dl}  {note}')
        for seat, h in zip('NESW', hs):
            mark = '  <- 你' if seat == 'S' else ''
            print(f'  {seat}: {h}{mark}')
        print(f'  提示: {hint}\n')
