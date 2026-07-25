# -*- coding: utf-8 -*-
"""
Bidding-sequence practice-deal generator for Ben.

Constructs deals (by fast rejection sampling on HCP + shape — no DDS needed,
these are auction-driven) so a specific bidding sequence is the natural one.
South is the hero. `dealer` is set so the intended opener speaks first.

Two families:
  1NT follow-ups   — partner (North) opens a 15-17 1NT; you (South) respond
                     (Stayman / Jacoby transfer / invite / game / slam try).
  common sequences — strong 2C, weak two, 2/1 GF, Jacoby 2NT, takeout double,
                     simple overcall.

Card encoding matches deck52: card = suit*13 + rank ; suit S0 H1 D2 C3 ;
rank A0 K1 Q2 J3 T4 9..2 = 5..12. Deal string = N E S W, each "S.H.D.C".
Each generator returns (deal_str, dealer, vuln, note, hint).
"""
import random as _random

RANKS = 'AKQJT98765432'
SUITS = 'SHDC'
SUIT_SYM = {0: '♠', 1: '♥', 2: '♦', 3: '♣'}
HCP = {0: 4, 1: 3, 2: 2, 3: 1}


def _split():
    deck = list(range(52))
    _random.shuffle(deck)
    return [deck[0:13], deck[13:26], deck[26:39], deck[39:52]]   # N E S W

def hand_to_str(cards):
    suits = ['', '', '', '']
    for c in sorted(cards):
        suits[c // 13] += RANKS[c % 13]
    return '.'.join(suits)

def deal_to_str(hands):
    return ' '.join(hand_to_str(h) for h in hands)

def hcp(cards):
    return sum(HCP.get(c % 13, 0) for c in cards)

def lengths(cards):
    L = [0, 0, 0, 0]
    for c in cards:
        L[c // 13] += 1
    return L

def is_balanced(L):
    return min(L) >= 2 and sum(1 for x in L if x == 2) <= 1 and max(L) <= 5

def longest(L):
    return L.index(max(L))

def is_opener(cards, L):
    # ~12+ HCP, or 11 with a 6-card suit; a rough natural opening
    h = hcp(cards)
    return h >= 12 or (h >= 11 and max(L) >= 6)


# ============= 1NT follow-ups (North opens 1NT, South responds) =============
def _nt_opener(cards):
    return is_balanced(lengths(cards)) and 15 <= hcp(cards) <= 17

def _check_stayman(H):
    N, E, S, W = H
    if not _nt_opener(N):
        return None
    Ls = lengths(S)
    if (Ls[0] == 4 or Ls[1] == 4) and Ls[0] < 5 and Ls[1] < 5 and 8 <= hcp(S) <= 15:
        return ('N', '1NT–Stayman', '搭档(北)开 1NT。你有 4 张高花 + 邀请以上牌力,'
                '用 Stayman(叫 2♣)问搭档有没有 4 张高花。')
    return None

def _check_transfer(H, suit_i, other_i, name):
    N, E, S, W = H
    if not _nt_opener(N):
        return None
    Ls = lengths(S)
    if Ls[suit_i] >= 5 and Ls[suit_i] >= Ls[other_i]:
        low = '2♦' if suit_i == 1 else '2♥'
        return ('N', f'1NT–转移({name})', f'搭档(北)开 1NT。你有 5+ 张{SUIT_SYM[suit_i]},'
                f'用 Jacoby 转移(叫 {low})让搭档做庄{SUIT_SYM[suit_i]}。')
    return None

def _check_nt_invite(H):
    N, E, S, W = H
    if not _nt_opener(N):
        return None
    Ls = lengths(S)
    if is_balanced(Ls) and Ls[0] < 4 and Ls[1] < 4 and 8 <= hcp(S) <= 9:
        return ('N', '1NT–2NT 邀请', '搭档(北)开 1NT。你均型 8-9 点、无 4 张高花,'
                '叫 2NT 邀请成局,让搭档按最大/最小决定。')
    return None

def _check_nt_game(H):
    N, E, S, W = H
    if not _nt_opener(N):
        return None
    Ls = lengths(S)
    if is_balanced(Ls) and Ls[0] < 4 and Ls[1] < 4 and 10 <= hcp(S) <= 14:
        return ('N', '1NT–3NT', '搭档(北)开 1NT。你均型 10-14 点、无 4 张高花,'
                '直接叫 3NT 成局。')
    return None

def _check_nt_slam(H):
    N, E, S, W = H
    if not _nt_opener(N):
        return None
    Ls = lengths(S)
    if is_balanced(Ls) and 16 <= hcp(S) <= 17:
        return ('N', '1NT–满贯邀请', '搭档(北)开 1NT。你均型 16-17 点,合计约 32-34,'
                '用定量 4NT 邀请小满贯(搭档最大就上 6NT)。')
    return None

def _check_twoway_stayman(H):
    # Two-way Stayman: 2C = invitational Stayman, 2D = game-forcing Stayman.
    # Drill the 2D (forcing) branch: GF hand with a 4-card major.
    N, E, S, W = H
    if not _nt_opener(N):
        return None
    Ls = lengths(S)
    if (Ls[0] == 4 or Ls[1] == 4) and Ls[0] < 5 and Ls[1] < 5 and 11 <= hcp(S) <= 15:
        return ('N', '双路斯台曼(2♦逼局)', '搭档(北)开 1NT。你成局逼叫值 + 4 张高花,'
                '用双路斯台曼的 2♦(逼局版,区别于邀请性 2♣)问高花。'
                '注:Ben 按自有体系应,练你自己叫出这口。')
    return None

def _check_puppet_stayman(H):
    # Puppet Stayman over a 2NT opening: 3C asks opener for a 5-card major
    # first, then 4-card majors. Drill: partner opens 2NT, you hold a major.
    N, E, S, W = H
    if not (is_balanced(lengths(N)) and 20 <= hcp(N) <= 21):
        return None
    Ls = lengths(S)
    if (Ls[0] >= 4 or Ls[1] >= 4) and hcp(S) >= 4:
        return ('N', '傀儡斯台曼(2NT–3♣)', '搭档(北)开 2NT(20-21 均型)。你有 4+ 张高花、'
                '想找 5-3 或 4-4 高花配合,用傀儡(Puppet)斯台曼 3♣ 让搭档先报 5 张、再报 4 张高花。'
                '注:Ben 按自有体系应,练你自己叫出这口。')
    return None


# ===================== common sequences =====================
def _check_strong_2c(H):
    N, E, S, W = H
    if hcp(S) >= 22:
        return ('S', '强 2♣ 开叫', '你 22+ 点(或接近成局的强牌),开叫人工逼叫 2♣,'
                '之后按牌力/牌型继续描述。')
    return None

def _has_two_top3(cards, suit_i):
    # True if the hand holds >=2 of the top-3 honors (A/K/Q) in that suit.
    return sum(1 for c in cards if c // 13 == suit_i and (c % 13) in (0, 1, 2)) >= 2

# Cheapest natural positive-response call to a strong 2C, by suit.
_POS_2C_CALL = {0: '2♠', 1: '2♥', 2: '3♦', 3: '3♣'}

def _check_respond_2c(H):
    # Partner (North) opens a strong, game-forcing 2C; you (South) make the
    # standard 2D waiting/negative response (limited values, no clear positive).
    N, E, S, W = H
    if hcp(N) < 22:
        return None
    if hcp(S) <= 7:
        return ('N', '强 2♣ 应叫 · 2♦ 等叫',
                '搭档(北)开人工逼叫强 2♣(22+)。你牌力有限(≤7 点)、暂无正响应,'
                '按体系叫 2♦ 等叫(waiting/否定),把空间留给搭档继续描述,再随其定叫。')
    return None

def _check_respond_2c_pos(H):
    # Partner (North) opens strong 2C; you (South) hold a positive response:
    # 8+ HCP with a good 5+ suit (2 of the top-3 honors) -> show it directly.
    N, E, S, W = H
    if hcp(N) < 22 or hcp(S) < 8:
        return None
    Ls = lengths(S)
    for s in range(4):
        if Ls[s] >= 5 and _has_two_top3(S, s):
            return ('N', '强 2♣ 应叫 · 正响应',
                    f'搭档(北)开强 2♣(22+)。你 8+ 点、{SUIT_SYM[s]}好套(5+ 张带两张大牌),'
                    f'做正响应直接叫出该花色({_POS_2C_CALL[s]}),提前示实力与落点,而非 2♦ 等叫。')
    return None

def _check_weak_two(H):
    N, E, S, W = H
    Ls = lengths(S)
    for m in (0, 1):
        if Ls[m] == 6 and 5 <= hcp(S) <= 10 and max(Ls) == 6:
            return ('S', f'弱二开叫 2{SUIT_SYM[m]}', f'你 6 张{SUIT_SYM[m]}好套、5-10 点,'
                    f'开叫弱二 2{SUIT_SYM[m]}抢占空间。')
    return None

def _check_respond_preempt(H):
    # Partner (North) opens a weak two in a major; you (South) hold a fit and
    # game-going values -> raise to game (or 2NT Ogust to invite / ask).
    N, E, S, W = H
    Ln, Ls = lengths(N), lengths(S)
    for m in (0, 1):
        if Ln[m] == 6 and 5 <= hcp(N) <= 10 and max(Ln) == 6:
            if Ls[m] >= 3 and hcp(S) >= 15:
                return ('N', f'阻击应叫 · 抬到成局 (2{SUIT_SYM[m]}–4{SUIT_SYM[m]})',
                        f'搭档(北)开弱二 2{SUIT_SYM[m]}(6 张、5-10 点)。你有 {SUIT_SYM[m]}配合(3+)'
                        f'+ 成局力(15+),直接抬到 4{SUIT_SYM[m]}成局;'
                        f'若只想邀请或问搭档牌质,可用 2NT(Ogust)问明。')
    return None

def _check_defend_preempt(H):
    # RHO (East) opens a weak two; you (South) make a takeout double: opening+
    # values, short in their suit, support for the unbid suits.
    N, E, S, W = H
    Le, Ls = lengths(E), lengths(S)
    for m in (0, 1, 2):                    # weak two in D/H/S (2C not a weak two)
        if Le[m] == 6 and 5 <= hcp(E) <= 10 and max(Le) == 6:
            others = [s for s in range(4) if s != m]
            if hcp(S) >= 13 and Ls[m] <= 2 and sum(1 for s in others if Ls[s] >= 3) >= 2:
                return ('E', f'阻击防守 · 技术性加倍 (东开 2{SUIT_SYM[m]})',
                        f'东家开弱二 2{SUIT_SYM[m]}(6 张、5-10 点)阻击。你 13+ 点、在{SUIT_SYM[m]}短(≤2)、'
                        f'其余各门有支持,用技术性加倍(takeout)让搭档在高一级挑花色;'
                        f'若只是自己一门好长套,则改用夺叫。')
    return None

def _check_twoover1(H):
    N, E, S, W = H
    Ls, Ln = lengths(S), lengths(N)
    for m in (0, 1):                      # South opens 1 of a major
        if Ls[m] >= 5 and 12 <= hcp(S) <= 20:
            # North: game-forcing 2/1 — 13+, a 4+ lower suit, weak support
            if hcp(N) >= 13 and Ln[m] <= 2:
                low = [s for s in range(4) if s != m and Ln[s] >= 4 and s > m]
                if low:
                    return ('S', f'2/1 逼局 (1{SUIT_SYM[m]}–2♣/♦)',
                            f'你开 1{SUIT_SYM[m]}(5+ 张),搭档 13+ 点用低花做 2/1 成局逼叫。'
                            f'一路叫到成局,从容找配合/探满贯。')
    return None

def _check_jacoby2nt(H):
    N, E, S, W = H
    Ln, Ls = lengths(N), lengths(S)
    for m in (0, 1):                      # North opens 1 major, South raises via 2NT
        if Ln[m] >= 5 and 12 <= hcp(N) <= 20:
            if Ls[m] >= 4 and hcp(S) >= 13 and min(Ls) >= 2:
                return ('N', f'Jacoby 2NT (1{SUIT_SYM[m]}–2NT)',
                        f'搭档开 1{SUIT_SYM[m]},你有 4+ 张将牌支持 + 成局力、均型,'
                        f'叫 Jacoby 2NT 示将牌配合并问搭档短套,探满贯。')
    return None

def _check_takeout(H):
    N, E, S, W = H
    Le, Ls = lengths(E), lengths(S)
    if not is_opener(E, Le):
        return None
    esuit = longest(Le)                   # East's (likely) opening suit
    if Le[esuit] < 4:
        return None
    others = [s for s in range(4) if s != esuit]
    if hcp(S) >= 12 and Ls[esuit] <= 2 and sum(1 for s in others if Ls[s] >= 3) >= 2:
        return ('E', f'技术性加倍 (东开 1{SUIT_SYM[esuit]})',
                f'东家开 1{SUIT_SYM[esuit]}。你 12+ 点、在{SUIT_SYM[esuit]}短,其余三门有支持,'
                f'用技术性加倍(takeout)让搭档挑一门花色。')
    return None

def _check_overcall(H):
    N, E, S, W = H
    Le, Ls = lengths(E), lengths(S)
    if not is_opener(E, Le):
        return None
    esuit = longest(Le)
    if Le[esuit] < 4:
        return None
    for s in range(4):
        if s != esuit and Ls[s] >= 5 and 8 <= hcp(S) <= 16:
            # suit rank S>H>D>C (index 0 highest); a higher-ranking suit
            # (lower index) can be overcalled at the 1-level.
            lvl = '1' if s < esuit else '2'
            return ('E', f'夺叫 ({lvl}{SUIT_SYM[s]})',
                    f'东家开 1{SUIT_SYM[esuit]}。你有 5+ 张{SUIT_SYM[s]}好套、8-16 点,'
                    f'夺叫 {lvl}{SUIT_SYM[s]}争夺定约/指示首攻。')
    return None


# ============= opening 1NT (South opens 1NT, handles partner) =============
def _opponents_quiet(E, W):
    # Keep an "open 1NT and declare it" drill on-topic: the opponents must not
    # have the ammunition to overcall and steal the auction, otherwise South
    # ends up *defending* (e.g. a Cappelletti 2D both-majors overcall pushing
    # the deal to 3H by E/W) instead of declaring the NT contract the drill is
    # about. Filter out any E/W hand that would naturally compete.
    for hand in (E, W):
        L = lengths(hand)
        h = hcp(hand)
        if h >= 12:                                   # opening strength
            return False
        if max(L) >= 6:                               # long suit -> jump/overcall
            return False
        if L[0] >= 4 and L[1] >= 4 and h >= 9:        # both majors -> Cappelletti
            return False
    if hcp(E) + hcp(W) >= 20:                         # combined balance-of-power
        return False
    return True


def _check_open_1nt(H):
    N, E, S, W = H
    if _nt_opener(S) and _opponents_quiet(E, W):
        return ('S', '开叫 1NT', '你 15-17 均型,开叫 1NT。之后按搭档的应叫'
                '(Stayman / 转移 / 邀请)逐步应对,并打好这个无将定约。')
    return None

def _check_open_stayman(H):
    N, E, S, W = H
    if not _nt_opener(S) or not _opponents_quiet(E, W):
        return None
    Ln = lengths(N)
    if (Ln[0] == 4 or Ln[1] == 4) and Ln[0] < 5 and Ln[1] < 5 and 8 <= hcp(N) <= 15:
        return ('S', '开 1NT · 应对 Stayman', '你开 1NT,搭档叫 2♣ Stayman 问高花。'
                '有 4 张高花就叫出(♥优先),两门都没有叫 2♦。')
    return None

def _check_open_transfer(H):
    N, E, S, W = H
    if not _nt_opener(S) or not _opponents_quiet(E, W):
        return None
    Ln = lengths(N)
    for m in (0, 1):
        if Ln[m] >= 5 and Ln[m] >= Ln[1 - m]:
            return ('S', f'开 1NT · 应对转移', f'你开 1NT,搭档转移到{SUIT_SYM[m]}。'
                    f'先接受转移(叫出该高花),牌力好+4 张配合可超接受跳一级。')
    return None

def _check_open_invite(H):
    N, E, S, W = H
    if not _nt_opener(S) or not _opponents_quiet(E, W):
        return None
    Ln = lengths(N)
    if is_balanced(Ln) and Ln[0] < 4 and Ln[1] < 4 and 8 <= hcp(N) <= 9:
        return ('S', '开 1NT · 应对邀请', '你开 1NT,搭档叫 2NT 邀请成局。'
                '你 17(最大)接受上 3NT,15(最小)停 2NT,16 看牌型质量。')
    return None

def _check_open_jacoby2nt(H):
    # You open 1 major; partner (Ben) has 4+ support + game values and bids
    # Jacoby 2NT — you show your shortage / extra strength.
    N, E, S, W = H
    Ls, Ln = lengths(S), lengths(N)
    for m in (0, 1):
        if Ls[m] >= 5 and 12 <= hcp(S) <= 20:
            if Ln[m] >= 4 and hcp(N) >= 13 and min(Ln) >= 2:
                return ('S', f'开 1{SUIT_SYM[m]} · 应对 Jacoby 2NT',
                        f'你开 1{SUIT_SYM[m]},搭档叫 Jacoby 2NT(将牌配合+成局力,问短套)。'
                        f'你按牌型回答:有短套跳叫示短,均型/额外牌力另有应法,再探满贯。')
    return None


# ===================== slam & forcing tools =====================
def _check_blackwood(H):
    N, E, S, W = H; Ls, Ln = lengths(S), lengths(N)
    for m in (0, 1):
        if Ls[m] >= 5 and Ln[m] >= 3 and 15 <= hcp(S) <= 20 and hcp(N) >= 13 and hcp(S) + hcp(N) >= 30:
            return ('S', 'Blackwood / RKC (4NT)',
                    f'你{SUIT_SYM[m]}长套,双方合计 30+ 有满贯苗头。用 RKC 1430 的 4NT '
                    f'问关键张(4 张 A + 将 K),数够再上 6{SUIT_SYM[m]}。')
    return None

def _check_gerber(H):
    N, E, S, W = H
    if not _nt_opener(N):
        return None
    if hcp(S) >= 16 and is_balanced(lengths(S)):
        return ('N', 'Gerber (4♣ 问 A)',
                '搭档开 1NT。你均型 16+、合计满贯边缘,用 Gerber 4♣ 直接问 A 数,够就上 6NT。')
    return None

def _check_splinter(H):
    N, E, S, W = H; Ln, Ls = lengths(N), lengths(S)
    for m in (0, 1):
        if Ln[m] >= 5 and 12 <= hcp(N) <= 20 and Ls[m] >= 4 and 11 <= hcp(S) <= 15 and min(Ls) <= 1:
            short = [s for s in range(4) if Ls[s] <= 1][0]
            return ('N', 'splinter 双跳示短',
                    f'搭档开 1{SUIT_SYM[m]},你 4+ 张将支持 + 成局力 + {SUIT_SYM[short]}短套。'
                    f'用 splinter 双跳({SUIT_SYM[short]})示配合+短套,探满贯。')
    return None

def _check_control_cue(H):
    N, E, S, W = H; Ls, Ln = lengths(S), lengths(N)
    for m in (0, 1):
        if Ls[m] >= 5 and Ln[m] >= 3 and hcp(S) + hcp(N) >= 31 and hcp(S) >= 14:
            return ('S', '控制示叫 (cuebid)',
                    f'双方{SUIT_SYM[m]}配合、满贯区。定将后用控制示叫(先示第一轮控制=A/缺门)'
                    f'逐门交流,判断能否安全上满贯。')
    return None

def _check_fourth_suit(H):
    N, E, S, W = H; Ln, Ls = lengths(N), lengths(S)
    if Ln[2] >= 4 and Ln[0] == 4 and is_opener(N, Ln) and hcp(N) <= 17:
        if Ls[1] >= 4 and hcp(S) >= 12 and Ls[0] <= 2 and Ls[3] <= 2:
            return ('N', '第四花色逼叫 (4SF)',
                    '搭档 1♦ 开叫、再叫 1♠(两门),你 1♥ 应叫后有成局力但无现成落点——'
                    '用第四花色 2♣ 人工逼叫,问挡张/补充描述,再定 3NT 或高花。')
    return None

def _check_new_minor(H):
    N, E, S, W = H; Ln, Ls = lengths(N), lengths(S)
    for m in (0, 1):
        if Ls[m] >= 5 and 11 <= hcp(S) <= 15 and is_balanced(lengths(N)) and 12 <= hcp(N) <= 14 and Ln[m] <= 3:
            return ('N', '重询斯台曼(新低花逼叫 / checkback)',
                    f'搭档开叫后再叫 1NT(12-14 均型)。你 5 张{SUIT_SYM[m]}+邀请以上,'
                    f'用新低花逼叫问搭档有没有 3 张{SUIT_SYM[m]}(找 5-3),否则打 NT。')
    return None

# ===================== competitive & defensive =====================
def _check_negative_double(H):
    N, E, S, W = H; Ln, Le, Ls = lengths(N), lengths(E), lengths(S)
    if not is_opener(N, Ln):
        return None
    nsuit = longest(Ln)
    if Ln[nsuit] < 4:
        return None
    esuit = longest(Le)
    if not (Le[esuit] >= 5 and hcp(E) >= 8 and esuit != nsuit):
        return None
    majors = [mm for mm in (0, 1) if mm != nsuit and mm != esuit and Ls[mm] >= 4]
    if majors and 6 <= hcp(S) <= 11:
        return ('N', '负性加倍 (negative X)',
                f'搭档开 1{SUIT_SYM[nsuit]},东家夺叫 {SUIT_SYM[esuit]}。你有 4+ 张未叫高花 + 6-11 点,'
                f'用负性加倍示高花+并列牌力,让搭档继续描述。')
    return None

def _check_michaels(H):
    N, E, S, W = H; Le, Ls = lengths(E), lengths(S)
    if not is_opener(E, Le):
        return None
    esuit = longest(Le)
    if Le[esuit] < 5:
        return None
    if esuit in (2, 3):
        if Ls[0] >= 5 and Ls[1] >= 5 and 8 <= hcp(S) <= 16:
            return ('E', 'Michaels 起叫 (双高花)',
                    f'东家开 1{SUIT_SYM[esuit]}(低花)。你黑桃+红心 5-5,'
                    f'用 Michaels 起叫(叫对方花色)一次示两门高花。')
    else:
        other = 1 - esuit
        for mn in (2, 3):
            if Ls[other] >= 5 and Ls[mn] >= 5 and 8 <= hcp(S) <= 16:
                return ('E', 'Michaels 起叫 (高花+低花)',
                        f'东家开 1{SUIT_SYM[esuit]}(高花)。你{SUIT_SYM[other]}+{SUIT_SYM[mn]} 5-5,'
                        f'用 Michaels 起叫示另一门高花 + 一门低花。')
    return None

def _check_unusual_2nt(H):
    N, E, S, W = H; Le, Ls = lengths(E), lengths(S)
    if not is_opener(E, Le):
        return None
    esuit = longest(Le)
    if esuit in (0, 1) and Le[esuit] >= 5 and Ls[2] >= 5 and Ls[3] >= 5 and 8 <= hcp(S) <= 16:
        return ('E', '异型 2NT (双低花)',
                f'东家开 1{SUIT_SYM[esuit]}。你方块+梅花 5-5,用异型 2NT 一次示两门低花。')
    return None

def _check_drury(H):
    N, E, S, W = H; Ln, Ls = lengths(N), lengths(S)
    if hcp(S) > 11:
        return None
    for m in (0, 1):
        if Ln[m] >= 5 and 11 <= hcp(N) <= 17 and Ls[m] >= 3 and 10 <= hcp(S) <= 11:
            return ('S', 'Drury (过手方)',
                    f'你(过手方,已 Pass)后,搭档第三家开 1{SUIT_SYM[m]}。你 3+ 张配合 + 10-11 限加叫,'
                    f'用 Drury 2♣ 问搭档是否真开叫,避免叫过。')
    return None

def _check_inverted_minors(H):
    N, E, S, W = H; Ln, Ls = lengths(N), lengths(S)
    for mn in (2, 3):
        if Ln[mn] >= 3 and is_opener(N, Ln) and longest(Ln) == mn and Ls[mn] >= 4 and Ls[0] < 4 and Ls[1] < 4:
            return ('N', '低花倒置加叫',
                    f'搭档开 1{SUIT_SYM[mn]}。你 4+ 张{SUIT_SYM[mn]}支持、无 4 张高花。'
                    f'倒置加叫:2{SUIT_SYM[mn]}=强(10+ 逼叫),3{SUIT_SYM[mn]}=弱(阻击),按点力选。')
    return None


_SEQS = {
    'blackwood':      _check_blackwood,
    'gerber':         _check_gerber,
    'splinter':       _check_splinter,
    'control_cue':    _check_control_cue,
    'fourth_suit':    _check_fourth_suit,
    'new_minor':      _check_new_minor,
    'negative_double':_check_negative_double,
    'michaels':       _check_michaels,
    'unusual_2nt':    _check_unusual_2nt,
    'drury':          _check_drury,
    'inverted_minors':_check_inverted_minors,
    'open_1nt':       _check_open_1nt,
    'open_stayman':   _check_open_stayman,
    'open_transfer':  _check_open_transfer,
    'open_invite':    _check_open_invite,
    'open_jacoby2nt': _check_open_jacoby2nt,
    'stayman':    _check_stayman,
    'transfer_h': lambda H: _check_transfer(H, 1, 0, '红心'),
    'transfer_s': lambda H: _check_transfer(H, 0, 1, '黑桃'),
    'nt_invite':  _check_nt_invite,
    'nt_game':    _check_nt_game,
    'nt_slam':    _check_nt_slam,
    'twoway_stayman': _check_twoway_stayman,
    'puppet_stayman': _check_puppet_stayman,
    'strong_2c':  _check_strong_2c,
    'respond_2c': _check_respond_2c,
    'respond_2c_pos': _check_respond_2c_pos,
    'weak_two':   _check_weak_two,
    'respond_preempt': _check_respond_preempt,
    'defend_preempt':  _check_defend_preempt,
    'twoover1':   _check_twoover1,
    'jacoby2nt':  _check_jacoby2nt,
    'takeout':    _check_takeout,
    'overcall':   _check_overcall,
}

# (key, name, desc, group) — group: 'open'(开叫1NT) 'nt'(应叫1NT) 'seq'(典型序列)
SEQ_GROUPS = [('open', '① 开叫 1NT'), ('nt', '② 应叫 1NT'), ('seq', '③ 典型叫牌序列'),
              ('slam', '④ 满贯与逼叫工具'), ('comp', '⑤ 竞叫与防守')]
SEQ_LIST = [
    ('open_1nt',      '开叫 1NT',    '你 15-17 均型,开 1NT 并打好定约', 'open'),
    ('open_stayman',  '应对 Stayman', '搭档问高花,你答有无 4 张高花', 'open'),
    ('open_transfer', '应对雅可比转移', '搭档转移,你接受(或超接受)', 'open'),
    ('open_invite',   '应对邀请',     '搭档 2NT 邀请,你按 15/17 取舍', 'open'),
    ('open_jacoby2nt','应对 Jacoby 2NT', '你开 1 高花,搭档跳 2NT,你示短套', 'open'),
    ('stayman',    '斯台曼 Stayman', '需 8+ 点 + 4 张高花,叫 2♣ 问高花', 'nt'),
    ('transfer_h', '雅可比转移·红心', '5+ 红心(不限点力),叫 2♦ 转移', 'nt'),
    ('transfer_s', '雅可比转移·黑桃', '5+ 黑桃(不限点力),叫 2♥ 转移', 'nt'),
    ('nt_invite',  '2NT 邀请',      '均型 8-9,叫 2NT 邀请', 'nt'),
    ('nt_game',    '直上 3NT',      '均型 10-14 无高花,叫 3NT', 'nt'),
    ('nt_slam',    '满贯邀请',      '均型 16-17,定量 4NT', 'nt'),
    ('twoway_stayman','双路斯台曼',  '成局逼叫值+4 高花,叫 2♦ 逼局斯台曼', 'nt'),
    ('puppet_stayman','傀儡斯台曼',  '搭档开 2NT,4+ 高花,叫 3♣ 傀儡问高花', 'nt'),
    ('strong_2c',  '强 2♣ 开叫',    '22+ 强牌,人工逼叫开叫', 'seq'),
    ('respond_2c', '强 2♣ 应叫·2♦等叫', '搭档开 2♣,你 ≤7 点叫 2♦ 等叫', 'seq'),
    ('respond_2c_pos','强 2♣ 应叫·正响应','搭档开 2♣,你 8+ 点带好套,直接示套', 'seq'),
    ('weak_two',   '弱二开叫',      '6 张高花 5-10 点,开弱二', 'seq'),
    ('respond_preempt','阻击应叫·抬成局','搭档开弱二,你有配合+成局力,抬到 4', 'seq'),
    ('twoover1',   '2/1 逼局',      '开 1 高花,搭档低花 2/1 逼局', 'seq'),
    ('jacoby2nt',  'Jacoby 2NT',   '搭档开 1 高花,4+ 将支持+成局力,叫 2NT 探满贯', 'seq'),
    ('takeout',    '技术性加倍',    '对方开叫,短其门+支持它门', 'seq'),
    ('overcall',   '夺叫',          '对方开叫,你有好套夺叫', 'seq'),
    ('blackwood',  'Blackwood/RKC', '满贯苗头,4NT 问关键张', 'slam'),
    ('gerber',     'Gerber 4♣',    '1NT 后满贯边缘,4♣ 问 A', 'slam'),
    ('splinter',   'Splinter',     '高花配合+短套,双跳示短探满贯', 'slam'),
    ('control_cue','控制示叫',      '满贯区,逐门示控制交流', 'slam'),
    ('fourth_suit','第四花色逼叫',  '无落点时叫第四花色人工逼叫', 'slam'),
    ('new_minor',  '重询斯台曼(新低花逼叫)', '搭档 1NT 再叫后找 5-3 高花', 'slam'),
    ('defend_preempt','防守对手阻击·加倍','对手开弱二,你 13+ 短其门,技术性加倍', 'comp'),
    ('negative_double','负性加倍',  '搭档开叫被夺叫,示未叫高花', 'comp'),
    ('michaels',   'Michaels 起叫', '起叫对方花色示双色套', 'comp'),
    ('unusual_2nt','异型 2NT',      '2NT 示两门低花', 'comp'),
    ('drury',      'Drury',        '过手方,搭档 3 家开高花,限加叫', 'comp'),
    ('inverted_minors','低花倒置加叫','1 低花后 2 强 3 弱', 'comp'),
]


def generate(seq, max_attempts=200000):
    seq = (seq or 'stayman').lower()
    check = _SEQS.get(seq)
    if check is None:
        seq, check = 'stayman', _SEQS['stayman']
    for _ in range(max_attempts):
        H = _split()
        res = check(H)
        if res:
            dealer, note, hint = res
            return deal_to_str(H), dealer, 'None', note, hint
    H = _split()
    return deal_to_str(H), 'S', 'None', '随机牌(未命中该序列)', ''


if __name__ == '__main__':
    import sys, time
    t = sys.argv[1] if len(sys.argv) > 1 else 'stayman'
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for _ in range(n):
        t0 = time.perf_counter()
        d, dl, v, note, hint = generate(t)
        ms = (time.perf_counter() - t0) * 1000
        hs = d.split()
        print(f'[{t}] {ms:6.1f}ms  dealer={dl}  {note}')
        for seat, h in zip('NESW', hs):
            mark = '  <- 你' if seat == 'S' else ('  (搭档)' if seat == 'N' else '')
            print(f'  {seat}: {h}{mark}')
        print(f'  提示: {hint}\n')
