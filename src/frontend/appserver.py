import sys
from gevent import monkey
monkey.patch_all()

# Patching to suppress the warning about invalid HTTP versions
monkey.patch_all(warn_on_full_argv=False, warn_on_stopping=False)

from bottle import Bottle, run, static_file, redirect, template, request, response, HTTPError
import bottle
bottle.BaseRequest.MEMFILE_MAX = 5 * 1024 * 1024 

import shelve
import uuid
import json
import os
import argparse
import datetime
import numpy as np
from urllib.parse import parse_qs
from urllib.parse import quote
import re
import subprocess
import dealgen  # themed practice-deal generator
import techgen  # technique practice-deal generator (DDS-verified)
import bidgen   # bidding-sequence practice-deal generator

# Bidding systems the engine can run (single-server-restart switching).
# Keys map to config files under src/; models verified to start on Apple Silicon.
BEN_ROOT = os.path.dirname(os.path.dirname(script_dir)) if 'script_dir' in dir() else os.path.expanduser('~/ben')
SYSTEMS = {
    'gib':  {'conf': 'config/onnx.conf',     'name': 'GIB / 通用', 'desc': '默认 · 轻量 (ONNX)'},
    '21gf': {'conf': 'config/BEN-21GF.conf', 'name': '2/1 GF',     'desc': '2-over-1 逼局'},
    'sayc': {'conf': 'config/BEN-Sayc.conf', 'name': 'SAYC',       'desc': '标准美国黄卡'},
}

def current_system():
    try:
        with open(os.path.join(BEN_ROOT, '.current_system')) as f:
            k = f.read().strip()
            return k if k in SYSTEMS else 'gib'
    except Exception:
        return 'gib'


app = Bottle()
script_dir = os.path.dirname(os.path.abspath(__file__))

BUNDLE_TEMP_DIR = ''

try:
    if getattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
        BUNDLE_TEMP_DIR = sys._MEIPASS
        FILES_DIR = "./BBA/CC/"
        #Modify template
        bottle.TEMPLATE_PATH.insert(0,BUNDLE_TEMP_DIR + '/views')
except:
    BUNDLE_TEMP_DIR= '' 
    # Directory containing the files
    FILES_DIR = "../../BBA/CC/"


# Get a list of filenames in the directory
filenames = [f for f in os.listdir(FILES_DIR) if os.path.isfile(os.path.join(FILES_DIR, f))]
file_map = {os.path.splitext(f)[0]: f for f in filenames}  # Remove extension but keep mapping
  
def extract_value(s: str) -> str:
    return s[s.index('"') + 1 : s.rindex('"')]

class TypeHand:
    def __init__(self):
        self.suit = [""] * 4

board = np.zeros((4, 4), dtype=int)
C_SPADES = 3
C_HEARTS = 2
C_DIAMONDS = 1
C_CLUBS = 0
C_NT = 4
C_NORTH = 0
C_EAST = 1
C_SOUTH = 2
C_WEST = 3
C_NONE = 0
C_WE = 1
C_NS = 2
C_BOTH = 3

board[C_NORTH, C_NONE] = 1
board[C_EAST, C_NS] = 2
board[C_SOUTH, C_WE] = 3
board[C_WEST, C_BOTH] = 4
board[C_NORTH, C_NS] = 5
board[C_EAST, C_WE] = 6
board[C_SOUTH, C_BOTH] = 7
board[C_WEST, C_NONE] = 8
board[C_NORTH, C_WE] = 9
board[C_EAST, C_BOTH] = 10
board[C_SOUTH, C_NONE] = 11
board[C_WEST, C_NS] = 12
board[C_NORTH, C_BOTH] = 13
board[C_EAST, C_NONE] = 14
board[C_SOUTH, C_NS] = 15
board[C_WEST, C_WE] = 16

def is_valid_deal_id(deal_id):
    # Check if the deal_id is a valid hexadecimal string or in the form 'xxx-Open' or 'xxx-Closed'
    return bool(re.match(r'^([0-9a-fA-F]{32}|[0-9]+-(Open|Closed))$', deal_id))

def hand_as_string(hand):
    s = ""
    for i in range(4):
        for j in range(4):
            s += hand[i].suit[3 - j]
            if j == 3:  # Checks if we've reached the last suit
                s += " "
            else:
                s += "."
    return s

def encode_board(hand, dealer, vulnerability, deal_number):
    board_extension = ((deal_number - 1) // 16) % 16
    str_Deal = format(board_extension, 'x') + format(dealer * 4 + vulnerability, 'x')
    encryption_byte = board[dealer,vulnerability]

    for j in range(1, 14): 
        sum_value = 0
        str_cards = "AKQJT98765432"[j - 1]
        for i in range(4):
            for player_index in range(4):
                if str_cards in hand[player_index].suit[i]:
                    sum_value += int(player_index * (4 ** i))
        # ---coding
        sum_value = encryption_byte ^ sum_value
        str_cards = format(sum_value, 'x')
        if len(str_cards) == 1:
            str_cards = "0" + str_cards
        str_Deal += str_cards.upper()

    return str_Deal.upper()  # Convert the entire string to uppercase for consistency with VBA output

def transform_hand(hands):
    hand = [TypeHand() for _ in range(4)]

    for i in range(4):
        suits = hands[i].split('.')
        hand[i].suit[C_CLUBS] = suits[3]
        hand[i].suit[C_DIAMONDS] = suits[2]
        hand[i].suit[C_HEARTS] = suits[1]
        hand[i].suit[C_SPADES] = suits[0]
    
    return hand


def decode_board(encoded_str_deal):
    # Initialize the hand
    hand = [TypeHand() for _ in range(4)]

    board_extension = int(encoded_str_deal[0], 16)
    number = int(encoded_str_deal[1], 16)
    dealer_i = number // 4
    vulnerable = number % 4
    deal_no = board_extension * 16 + board[dealer_i][vulnerable]
    encryption_byte = board[dealer_i][vulnerable]

    card_index = 2
    for j in range(1, 14):
        str_card = "AKQJT98765432"[j - 1]
        str_number = encoded_str_deal[card_index:card_index + 2]
        number = int(str_number, 16)
        number = encryption_byte ^ number
        lbloki = [0] * 4
        lbloki[0] = number % 4
        lbloki[1] = (number // 4) % 4
        lbloki[2] = (number // 16) % 4
        lbloki[3] = number // 64
        card_index += 2

        for i in range(4):
            k = lbloki[i]
            hand[k].suit[i] += str_card
    dealer = "NESW"[dealer_i]
    vulnerable = ['None', 'E-W', 'N-S', 'Both'][vulnerable]
    return hand, dealer, vulnerable, deal_no

def parse_lin(lin):
    rx_hand = r'S(?P<S>[2-9A,K,Q,J,T]*?)H(?P<H>[2-9A,K,Q,J,T]*?)D(?P<D>[2-9A,K,Q,J,T]*?)C(?P<C>[2-9A,K,Q,J,T]*?)$'

    lin_vuln = re.findall(r'sv\|(.)\|', lin)[0].upper()
    vuln = "None"
    if lin_vuln == 'N':
        vuln = "N-S"
    elif lin_vuln == 'E':
        vuln = "E-W"
    elif lin_vuln == 'B':
        vuln = "Both"

    lin_deal = re.findall(r'(?<=md\|)(.*?)(?=\|)', lin)[0]
    dealer = {'1': 'S', '2': 'W', '3': 'N', '4': 'E'}[lin_deal[0]]
    lin_hands = lin_deal[1:].split(',')
    hd_south = re.search(rx_hand, lin_hands[0].upper()).groupdict()
    hd_west = re.search(rx_hand, lin_hands[1].upper()).groupdict()
    hd_north = re.search(rx_hand, lin_hands[2].upper()).groupdict()

    if len(lin_hands) == 4:
        hd_east = re.search(rx_hand, lin_hands[3].upper()).groupdict()
    else:
        def seen_cards(suit):
            return set(hd_south[suit]) | set(hd_west[suit]) | set(hd_north[suit])

        hd_east = {suit: set('AKQJT98765432') - seen_cards(suit) for suit in 'SHDC'}

    def to_pbn(hd):
        return '.'.join([''.join(list(hd[suit])) for suit in 'SHDC'])

    hands = [to_pbn(hd) for hd in [hd_north, hd_east, hd_south, hd_west]]
    # Pattern to find "Board <number>" and extract the number
    pattern = r'Board (\d+)'

    # Using re.search to find the pattern in the text
    match = re.search(pattern, lin)

    if match:
        board_no = match.group(1)  # Extracting the matched board number
    else:
        board_no = ""

    return dealer, vuln, hands, board_no

def parse_bsol(url):
    query_params = parse_qs(url.split('?')[1])
    # Extract the required values
    board = query_params.get('board', [])[0]
    dealer = query_params.get('dealer', [])[0]
    vuln_str = query_params.get('vul', [])[0]
    vulnerable = {'NS': 'N-S', 'EW': 'E-W', 'All': 'Both'}.get(vuln_str, vuln_str)

    hands = []
    # Concatenate the values from North, South, East, and West
    hands.append(query_params.get('North', [])[0])
    hands.append(query_params.get('South', [])[0])
    hands.append(query_params.get('East', [])[0])
    hands.append(query_params.get('West', [])[0])

    hands = " ".join(hands)
    return dealer, vulnerable, hands, board
    
def parse_pbn(fin):
    for line in fin:
        if line.startswith('[Dealer'):
            dealer = extract_value(line)
        if line.startswith('[Vulnerable'):
            vuln_str = extract_value(line)
            vulnerable = {'NS': 'N-S', 'EW': 'E-W', 'All': 'Both'}.get(vuln_str, vuln_str)
        if line.startswith('[Board'):
            board = extract_value(line)
            if not board.isdigit():
                last_space_index = board.rfind(' ')
                board = board[last_space_index + 1:]
        if line.startswith('[Deal '):
            hands_pbn = extract_value(line)
            [seat, hands] = hands_pbn.split(':')
            hands_nesw = [''] * 4
            first_i = 'NESW'.index(seat)
            for hand_i, hand in enumerate(hands.split()):
                hands_nesw[(first_i + hand_i) % 4] = hand
        else:
            continue

    return dealer, vulnerable, " ".join(hands_nesw), board

def validate_suit(part):
    return part == '' or bool(re.match(r'\d|[TJQKA]', part))
 
def validdeal(board, direction):
    # Split the input string into individual deals
    hands = board.split()
    
    # Check if there are exactly 4 deals
    if len(hands) != 4:
        print("Not 4 hands", board)
        return None
    
    # Check each deal individually
    for hand in hands:
        suits = hand.split('.')
        if len(suits) != 4:
            print("Not 4 suits in ", hand)
            return None
        if len(hand) != 16:
            print("Not 13 cards ", hand)
            return None
        result =  all(validate_suit(p.strip()) for p in suits)
        if not result:
            print("Wrong format ", hand)
            return None

    # All checks passed, return the hands
    # print("Direction", direction)        
    if direction == "N":
        return hands
    if direction == "E":
        return [hands[3], hands[0], hands[1], hands[2]]
    if direction == "S":
        return [hands[2], hands[3], hands[0], hands[1]]
    if direction == "W":
        return [hands[1], hands[2], hands[3], hands[0]]
    return hands


@app.route('/robots.txt')
def robots():
    response.content_type = 'text/plain'
    return "User-agent: *\nAllow: /\nAllow: /home\nAllow: /play\nDisallow: /api\nDisallow: /gib\nDisallow: /bba\nDisallow: /autoplay\nDisallow: /submit\nDisallow: /error\nDisallow: /app/\n"

@app.route('/')
def index():
    # Land straight into a playing table: random deal, human plays South,
    # full bidding + play. Deal-options page is still at /home.
    redirect("/app/bridge.html?board_no=&S=x&H=x&A=x&T=1&server=3")

@app.route('/deal/<theme>')
def themed_deal(theme):
    # Generate a deal matching a practice theme, then drop straight into the
    # table as human South (full bid + play). See dealgen.py for the themes.
    deal, dealer, vulnerable, note = dealgen.generate(theme)
    player = "&S=x&H=x&A=x&T=1"
    # Carry the theme into the table so "next deal" can re-draw the same theme
    # instead of falling back to a plain random deal.
    url = (f"/app/bridge.html?deal=(%27{deal}%27, %27{dealer} {vulnerable}%27)"
           f"{player}&board_no=&server=3&theme={quote(theme)}")
    redirect(url)

@app.route('/deal/tech/<key>')
def technique_deal(key):
    # DDS-verified technique deal, then straight into the table as human South.
    deal, dealer, vuln, note, hint = techgen.generate(key)
    player = "&S=x&H=x&A=x&T=1"
    # Carry the entry path so "next deal" re-draws the same technique.
    url = (f"/app/bridge.html?deal=(%27{deal}%27, %27{dealer} {vuln}%27)"
           f"{player}&board_no=&server=3"
           f"&technote={quote(note)}&techhint={quote(hint)}"
           f"&next={quote('/deal/tech/' + key)}")
    redirect(url)

@app.route('/deal/bid/<key>')
def bidding_deal(key):
    # Bidding-sequence practice deal (auction-driven, no DDS) -> table as South.
    deal, dealer, vuln, note, hint = bidgen.generate(key)
    player = "&S=x&H=x&A=x&T=1"
    # Carry the entry path so "next deal" re-draws the same bidding sequence.
    url = (f"/app/bridge.html?deal=(%27{deal}%27, %27{dealer} {vuln}%27)"
           f"{player}&board_no=&server=3"
           f"&technote={quote(note)}&techhint={quote(hint)}&bantag={quote('🃏 叫牌练习')}"
           f"&next={quote('/deal/bid/' + key)}")
    redirect(url)

# Practice menu: pick a deal type to drill.  Themes must match dealgen._THEME_META.
_PRACTICE_THEMES = [
    ('1nt',       '1NT 开叫',   '南家 15-17 均型,练强无将开叫与应叫'),
    ('game',      '成局定约',   'N-S 有高花配合的成局牌,练 4♥/4♠'),
    ('3nt',       '3NT',        'N-S 均型无大牌配合,冲 3NT'),
    ('slam',      '满贯',       'N-S 33+ 点,练小满贯叫牌'),
    ('preempt',   '阻击开叫',   '南家弱牌带 6+ 长套,练弱二/阻击'),
    ('defense',   '防守练习',   'E-W 做庄成局,你(南)专练防守'),
    ('partscore', '部分定约',   '双方都无成局,争叫/部分定约区'),
    ('random',    '随机一副',   '不设条件,随机发牌'),
]

@app.route('/练习')
@app.route('/practice')
def practice_menu():
    cards = "\n".join(
        f'<a class="theme" href="/deal/{key}">'
        f'<span class="th-name">{name}</span>'
        f'<span class="th-desc">{desc}</span></a>'
        for key, name, desc in _PRACTICE_THEMES
    )
    tech_cards = "\n".join(
        f'<a class="theme tech" href="/deal/tech/{key}" onclick="techLoading(this)">'
        f'<span class="th-name">{name}</span>'
        f'<span class="th-desc">{desc}</span></a>'
        for key, name, desc in techgen.TECHNIQUE_LIST
    )
    bid_sections = ""
    for gkey, gname in bidgen.SEQ_GROUPS:
        items = [x for x in bidgen.SEQ_LIST if x[3] == gkey]
        gcards = "\n".join(
            f'<a class="theme bid" href="/deal/bid/{k}">'
            f'<span class="th-name">{n}</span><span class="th-desc">{d}</span></a>'
            for k, n, d, g in items)
        bid_sections += f'<div class="subttl">{gname}</div>\n<div class="grid">{gcards}</div>\n'
    response.content_type = 'text/html; charset=utf-8'
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>牌型练习 · Ben</title>
<style>
:root{{--felt:#0f5f34;--felt2:#1f7a46;--wood:#4a3524;--ink:#f4ecd8;--muted:#c7bfa8;--gold:#ffd66b;}}
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}}
body{{font-family:-apple-system,"PingFang SC","Helvetica Neue",sans-serif;
  min-height:100vh;color:var(--ink);
  background:radial-gradient(circle at 50% 0%,var(--felt2),var(--felt) 70%);
  padding:24px 16px 40px;}}
header{{text-align:center;margin:8px 0 22px;}}
h1{{font-size:24px;letter-spacing:2px;font-weight:700;}}
.sub{{color:var(--muted);font-size:13px;margin-top:6px;}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;max-width:640px;margin:0 auto;}}
.theme{{display:flex;flex-direction:column;gap:6px;text-decoration:none;color:var(--ink);cursor:pointer;
  background:linear-gradient(160deg,rgba(255,255,255,.10),rgba(0,0,0,.18));
  border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:16px 15px;min-height:92px;
  box-shadow:0 4px 14px rgba(0,0,0,.28);transition:transform .08s ease,border-color .12s;}}
.theme:active{{transform:scale(.97);border-color:#ffd66b;}}
.theme.import{{background:linear-gradient(160deg,rgba(255,214,107,.16),rgba(0,0,0,.2));border-color:rgba(255,214,107,.35);}}
.secttl{{max-width:640px;margin:10px auto 12px;font-size:15px;font-weight:700;color:var(--ink);}}
.secttl small{{font-weight:400;font-size:11px;color:var(--muted);margin-left:6px;}}
.theme.tech{{background:linear-gradient(160deg,rgba(120,190,255,.14),rgba(0,0,0,.2));border-color:rgba(120,190,255,.32);}}
.theme.tech.loading{{opacity:.55;pointer-events:none;}}
.theme.tech.loading .th-desc::after{{content:" · 生成中(DDS 验证)…";color:#ffd66b;}}
.subttl{{max-width:640px;margin:14px auto 8px;font-size:13px;font-weight:700;color:var(--gold);letter-spacing:.04em;}}
.theme.bid{{background:linear-gradient(160deg,rgba(190,150,255,.15),rgba(0,0,0,.2));border-color:rgba(190,150,255,.32);min-height:78px;}}
.th-name{{font-size:18px;font-weight:700;letter-spacing:1px;}}
.th-desc{{font-size:12px;line-height:1.5;color:var(--muted);}}
.foot{{max-width:640px;margin:22px auto 0;display:flex;gap:10px;justify-content:center;}}
.foot a{{color:var(--ink);text-decoration:none;font-size:14px;padding:9px 16px;border-radius:10px;
  border:1px solid rgba(255,255,255,.18);background:rgba(0,0,0,.2);}}
.note{{max-width:640px;margin:18px auto 0;text-align:center;color:var(--muted);font-size:11px;line-height:1.6;}}
@media(max-width:480px){{.grid{{grid-template-columns:1fr;}}}}
/* bidding-system switcher */
#sysbar{{max-width:640px;margin:0 auto 16px;background:linear-gradient(160deg,rgba(255,255,255,.07),rgba(0,0,0,.16));
  border:1px solid rgba(255,255,255,.13);border-radius:13px;padding:12px 14px;}}
#sysbar .lbl{{font-size:12px;color:var(--muted);margin-bottom:9px;}}
#sysbar .lbl b{{color:var(--gold);}}
#sysbar .sysrow{{display:flex;gap:8px;flex-wrap:wrap;}}
#sysbar button{{flex:1;min-width:96px;font:inherit;font-size:13px;font-weight:600;color:var(--ink);cursor:pointer;
  background:rgba(0,0,0,.22);border:1px solid rgba(255,255,255,.16);border-radius:10px;padding:9px 8px;line-height:1.4;}}
#sysbar button.active{{background:linear-gradient(160deg,var(--gold),#e6b84f);color:#3a2c00;border-color:var(--gold);}}
#sysbar button small{{display:block;font-weight:400;font-size:11px;opacity:.8;}}
#sysbar .switching{{color:var(--gold);font-size:12px;margin-top:8px;text-align:center;display:none;}}
#sysbar .switching.on{{display:block;}}
/* import modal */
.overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:50;
  align-items:center;justify-content:center;padding:18px;}}
.overlay.on{{display:flex;}}
.modal{{width:100%;max-width:520px;background:linear-gradient(160deg,#14653a,#0d5330);
  border:1px solid rgba(255,255,255,.16);border-radius:16px;padding:20px;box-shadow:0 12px 40px rgba(0,0,0,.5);}}
.modal h2{{font-size:18px;margin-bottom:4px;}}
.modal p{{font-size:12px;color:var(--muted);margin-bottom:12px;line-height:1.5;}}
.modal label{{font-size:12px;color:var(--muted);display:block;margin:10px 0 5px;}}
.modal select,.modal textarea{{width:100%;font:inherit;color:var(--ink);
  background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.18);border-radius:10px;padding:10px;}}
.modal textarea{{min-height:120px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;resize:vertical;}}
.mrow{{display:flex;gap:10px;margin-top:16px;}}
.mrow button{{flex:1;font:inherit;font-size:15px;font-weight:600;padding:12px;border-radius:11px;border:none;cursor:pointer;}}
.btn-go{{background:#ffd66b;color:#3a2c00;}}
.btn-x{{background:rgba(255,255,255,.12);color:var(--ink);border:1px solid rgba(255,255,255,.2)!important;}}
</style></head><body>
<header><h1>♠ ♥ 牌型练习 ♦ ♣</h1>
<div class="sub">选一类牌型直接开打 · 你坐南家</div></header>
<div id="sysbar">
  <div class="lbl">当前叫牌体系:<b id="cursys">…</b>(点下方切换,约 10 秒重启引擎)</div>
  <div class="sysrow" id="sysrow"></div>
  <div class="switching" id="switching">⏳ 正在切换体系,引擎重启中…完成后自动刷新</div>
</div>
<div class="grid">
{cards}
<a class="theme import" onclick="document.getElementById('imp').classList.add('on')">
<span class="th-name">📥 导入牌例</span>
<span class="th-desc">粘贴 PBN / LIN / BBO 牌局手数,自己指定牌来打</span></a>
</div>
<div class="secttl">🎯 技巧练习 <small>DDS 验证 · 每副专练一种做庄/防守技巧</small></div>
<div class="grid">
{tech_cards}
</div>
<div class="secttl">🃏 叫牌练习 <small>按约定构造牌型 · 目标叫牌序列自然发生 · 你坐南家</small></div>
{bid_sections}
<div class="foot"><a href="/">🎲 随机开局</a><a href="/历史">📜 历史牌局</a><a href="/叫牌体系">📖 叫牌体系</a></div>
<div class="note">牌型按点力/牌型/配合约束生成,决定"该打成什么定约"的概率极高;<br>
最终叫到什么由 Ben 叫牌决定。防守类牌你坐南家防 E-W 的定约。</div>

<div class="overlay" id="imp">
  <form class="modal" action="/submit" method="post">
    <h2>导入牌例</h2>
    <p>从 BBO / 桥牌软件复制牌局,选格式后粘贴。你坐南家、完整叫牌+打牌。</p>
    <input type="hidden" name="server" value="3">
    <input type="hidden" name="S" value="x"><input type="hidden" name="H" value="x">
    <input type="hidden" name="A" value="x"><input type="hidden" name="T" value="1">
    <input type="hidden" name="dealer" value="N"><input type="hidden" name="vulnerable" value="None">
    <label>格式</label>
    <select id="fmt" onchange="switchFmt()">
      <option value="dealpbn">PBN(整段,含 [Deal ...])</option>
      <option value="deallin">LIN(BBO 手数 / 链接)</option>
      <option value="dealtext">手输(N:♠.♥.♦.♣ 四家,空格分隔)</option>
    </select>
    <label>牌局内容</label>
    <textarea id="dealbox" name="dealpbn" placeholder="在此粘贴..."></textarea>
    <div class="mrow">
      <button type="button" class="btn-x" onclick="document.getElementById('imp').classList.remove('on')">取消</button>
      <button type="submit" class="btn-go">开打 →</button>
    </div>
  </form>
</div>
<script>
function switchFmt(){{document.getElementById('dealbox').name=document.getElementById('fmt').value;}}
function techLoading(el){{el.classList.add('loading');}}

let SYS_CURRENT='gib';
fetch('/api/system').then(r=>r.json()).then(d=>{{
  SYS_CURRENT=d.current;
  const cur=d.systems.find(s=>s.key===d.current);
  document.getElementById('cursys').textContent=cur?cur.name:d.current;
  document.getElementById('sysrow').innerHTML=d.systems.map(s=>
    '<button class="'+(s.key===d.current?'active':'')+'" data-key="'+s.key+'" data-name="'+s.name+'">'+
    s.name+'<small>'+s.desc+'</small></button>').join('');
  Array.from(document.querySelectorAll('#sysrow button')).forEach(b=>
    b.addEventListener('click',()=>switchSystem(b.dataset.key,b.dataset.name)));
}}).catch(()=>{{document.getElementById('cursys').textContent='(读取失败)';}});

function switchSystem(key,name){{
  if(key===SYS_CURRENT) return;
  document.getElementById('switching').classList.add('on');
  document.getElementById('sysrow').style.opacity=.4;
  fetch('/api/system/'+key,{{method:'POST'}}).then(r=>r.json()).then(()=>{{
    // engine restart takes ~10s (TF2 load); wait then reload the menu.
    setTimeout(()=>location.reload(), 13000);
  }}).catch(()=>{{
    document.getElementById('switching').textContent='切换失败,请重试';
  }});
}}
</script>
</body></html>"""

@app.route('/叫牌体系')
@app.route('/system')
def bidding_system():
    response.content_type = 'text/html; charset=utf-8'
    return """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>叫牌体系 · Ben</title>
<style>
:root{--felt:#0f5f34;--felt2:#1f7a46;--ink:#f4ecd8;--muted:#c7bfa8;--gold:#ffd66b;}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}
body{font-family:-apple-system,"PingFang SC","Helvetica Neue",sans-serif;min-height:100vh;color:var(--ink);
  background:radial-gradient(circle at 50% 0%,var(--felt2),var(--felt) 70%);padding:22px 16px 48px;line-height:1.65;}
.wrap{max-width:680px;margin:0 auto;}
h1{font-size:23px;letter-spacing:1px;text-align:center;margin-bottom:4px;}
.sub{text-align:center;color:var(--muted);font-size:13px;margin-bottom:22px;}
.card{background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(0,0,0,.16));
  border:1px solid rgba(255,255,255,.13);border-radius:14px;padding:15px 17px;margin-bottom:14px;}
h2{font-size:16px;color:var(--gold);margin-bottom:9px;letter-spacing:.5px;}
table{width:100%;border-collapse:collapse;font-size:13.5px;}
td{padding:5px 6px;border-bottom:1px solid rgba(255,255,255,.09);vertical-align:top;}
td:first-child{white-space:nowrap;font-weight:700;color:#ffe9a8;width:34%;}
.s{color:#111;background:#f4ecd8;border-radius:3px;padding:0 3px;font-weight:700;}
.red{color:#d1344a;}.orange{color:#e07b00;}.green{color:#1a8a3c;}
ul{margin:2px 0 0 18px;font-size:13.5px;}li{margin:3px 0;}
.tip{color:var(--muted);font-size:12px;margin-top:6px;}
.foot{text-align:center;margin-top:20px;}
.foot a{color:var(--ink);text-decoration:none;font-size:14px;padding:10px 18px;border-radius:11px;
  border:1px solid rgba(255,255,255,.2);background:rgba(0,0,0,.22);margin:0 5px;display:inline-block;}
</style></head><body><div class="wrap">
<h1>♠♥♦♣ 叫牌体系</h1>
<div class="sub">Ben 可切换三套体系(在练习页顶部切换)。当前运行:<b id="cursys-badge">…</b></div>
<script>
fetch('/api/system').then(r=>r.json()).then(d=>{
  var m={gib:'GIB / 通用',_21gf:'2/1 GF',sayc:'SAYC'};
  var cur=(d.systems.find(function(s){return s.key===d.current;})||{}).name||d.current;
  document.getElementById('cursys-badge').textContent=cur;
}).catch(function(){document.getElementById('cursys-badge').textContent='(读取失败)';});
</script>

<div class="card"><h2>三套可切换体系</h2>
<table>
<tr><td>GIB / 通用</td><td>BBO 上 GIB 机器人的 2/1 风格(默认、轻量)。下面的内容主要就是它。</td></tr>
<tr><td>2/1 GF</td><td>标准 2-over-1 逼局,和 GIB 基本同源、更"正统"。</td></tr>
<tr><td>SAYC</td><td>标准美国黄卡。<b>主要区别</b>:1 阶高花后的 2/1 应叫只是<b>一轮逼叫</b>(非成局逼叫);其余(5 张高花、15-17 1NT、强 2♣、Stayman/转移)与 2/1 基本一致。</td></tr>
</table>
<div class="tip">下面按 2/1 / GIB 讲解;切到 SAYC 时,记住 2/1 应叫不再一路逼到成局即可。</div></div>

<div class="card"><h2>核心约定</h2>
<table>
<tr><td>5 张高花</td><td>开叫 <span class="s">1</span><span class="s red">♥</span>/<span class="s">1</span><span class="s">♠</span> 保证 5 张</td></tr>
<tr><td>1NT 开叫</td><td>15–17 点,均型(4333/4432/5332)</td></tr>
<tr><td>低花开叫</td><td><span class="s">1</span><span class="s orange">♦</span> 常 4+;<span class="s">1</span><span class="s green">♣</span> 可短(3 张),点力不足开高花时用</td></tr>
<tr><td>强 2♣</td><td><span class="s">2</span><span class="s green">♣</span> = 22+ 均型 或 接近成局的强牌(人工、逼叫)</td></tr>
<tr><td>弱二</td><td><span class="s">2</span><span class="s orange">♦</span>/<span class="s red">♥</span>/<span class="s">♠</span> = 5–10 点,6 张好套</td></tr>
</table></div>

<div class="card"><h2>2/1 逼局(体系精髓)</h2>
<ul>
<li>1 阶高花开叫后,应叫人跳到 <b>2 阶低花/低于开叫花色的新花</b>(如 1♠–2♦)= <b>成局逼叫</b>,12+ 点,一路叫到成局。</li>
<li>因此 2/1 应答后双方有充裕空间从容找配合、探满贯,不必跳叫挤空间。</li>
<li>唯一例外:<b>1NT 应叫可为半逼叫</b>(forcing 1NT),6–12 点,开叫人须再叫一次。</li>
</ul></div>

<div class="card"><h2>常用约定叫</h2>
<table>
<tr><td>Stayman</td><td>1NT–<span class="s">2</span><span class="s green">♣</span>,问 4 张高花</td></tr>
<tr><td>Jacoby 转移</td><td>1NT–<span class="s">2</span><span class="s orange">♦</span>=红心、–<span class="s">2</span><span class="s red">♥</span>=黑桃</td></tr>
<tr><td>Blackwood 1430</td><td><span class="s">4</span><span class="s green">♣</span>/RKC 问关键张(4 A + 将 K)</td></tr>
<tr><td>Jacoby 2NT</td><td>高花配合 + 成局力,问短套探满贯</td></tr>
<tr><td>示警加倍</td><td>低阶 X 多为技术性/示警,非罚</td></tr>
</table>
<div class="tip">牌桌上每口叫品下方,Ben 会实时用 BBA 给出解释(如 “1H = 4+♥; 6+ HCP; Forcing”),对照着看最快上手。</div></div>

<div class="card"><h2>大致点力门槛</h2>
<table>
<tr><td>开叫</td><td>约 12+ 点(或好牌型 11 点)</td></tr>
<tr><td>成局</td><td>双方合计约 25 点 → 3NT / 4<span class="red">♥</span><span >♠</span> / 5<span class="orange">♦</span><span class="green">♣</span></td></tr>
<tr><td>小满贯</td><td>约 33 点</td></tr>
<tr><td>大满贯</td><td>约 37 点</td></tr>
</table></div>

<div class="foot">
  <a href="/practice">← 牌型练习</a>
  <a href="/">🎲 开一局</a>
</div>
</div></body></html>"""

@app.route('/error')
def error_page():
    error_message = request.query.message
    # Render your error page template here, passing error_message to the template
    return f"<h3>{error_message}</h3>"

@app.route('/submit', method="POST")
def index(): 
    url = None
    server = request.forms.get("server")
    north = request.forms.get('N')
    east = request.forms.get('E')
    south = request.forms.get('S')
    west = request.forms.get('W')    
    human = request.forms.get('H')    
    autocomplete = request.forms.get('A')
    name = request.forms.get('name')
    timeout = request.forms.get('T')
    cont = request.forms.get('C')
    rotate = request.forms.get('R')
    visible = request.forms.get('V')
    matchpoint = request.forms.get('M')
    play = request.forms.get('play')
    player = ""
    if north: player += "&N=x"
    if east: player += "&E=x"
    if south: player += "&S=x"
    if west: player += "&W=x"
    if human: player += "&H=x"
    if autocomplete: player += "&A=x"
    if name: player += f"&name={name}"
    if timeout: player += f"&T={timeout}"
    if cont: player += "&C=x"
    if rotate: player += "&R=x"
    if visible: player += "&V=x"
    if matchpoint: player += "&M=x"
    board_no = request.forms.get('board')
    
    dealtext = request.forms.get('dealtext')
    if dealtext:
        dealer = request.forms.get('dealer')
        vulnerable = request.forms.get('vulnerable')
        direction = "N"
        dealtext = dealtext.upper().split(":")
        if len(dealtext) == 2:
            direction = dealtext[0][0]
            dealtext = dealtext[1] 
        else:
            dealtext = dealtext[0] 

        deal = validdeal(dealtext, direction)

        if deal == None:
            error_message = f'Error parsing deal-input.'
            print(error_message)
            print(dealtext)
            encoded_error_message = quote(error_message)
            redirect(f'/error?message={encoded_error_message}')

        deal = " ".join(deal)
        print(deal)
        url = f"/app/bridge.html?deal=(%27{deal}%27, %27{dealer} {vulnerable}%27){player}&board_no={board_no}&server={server}" + (f"&play={play}" if play else "")
    
    dealpbn = request.forms.get('dealpbn')
    if dealpbn:
        try:
            dealpbn = request.forms.get('dealpbn')
            dealer, vulnerable, deal, board_no = parse_pbn(dealpbn.splitlines())
            print(deal)
            url = f"/app/bridge.html?deal=(%27{deal}%27, %27{dealer} {vulnerable}%27){player}&board_no={board_no}&server={server}" + (f"&play={play}" if play else "")
        except Exception as e:
            error_message = f'Error parsing PBN-input. {e}'
            print(error_message)
            print(dealpbn)
            encoded_error_message = quote(error_message)
            redirect(f'/error?message={encoded_error_message}')

    dealbsol = request.forms.get('dealbsol')
    if dealbsol:
        dealbsol = request.forms.get('dealbsol')
        dealer, vulnerable, deal, board_no = parse_bsol(dealbsol)
        print(deal)
        url = f"/app/bridge.html?deal=(%27{deal}%27, %27{dealer} {vulnerable}%27){player}&board_no={board_no}&server={server}" + (f"&play={play}" if play else "")

    deallin = request.forms.get('deallin')
    if deallin:
        if "?" in deallin:
            query_params = deallin.split('?')
            deallin = parse_qs(query_params[-1])
            deallin = deallin.get('lin', [None])[0]
        else:
            if "lin=" in deallin:
                deallin = deallin.split("lin=")[-1]
        dealer, vulnerable, deal, board_no = parse_lin(deallin)
        try:
            dealer, vulnerable, deal, board_no = parse_lin(deallin)
        except Exception as e:
            error_message = f'Error parsing LIN-input. {e}'
            print(error_message)
            print(deallin)
            encoded_error_message = quote(error_message)
            redirect(f'/error?message={encoded_error_message}')

        deal = " ".join(deal)
        print(deal)
        url = f"/app/bridge.html?deal=(%27{deal}%27, %27{dealer} {vulnerable}%27){player}&board_no={board_no}&server={server}" + (f"&play={play}" if play else "")

    dealbba = request.forms.get('dealbba')
    if dealbba:
        hand, dealer, vulnerable, board_no = decode_board(dealbba)
        deal_as_str = hand_as_string(hand)
        url = f"/app/bridge.html?deal=(%27{deal_as_str}%27, %27{dealer} {vulnerable}%27){player}&board_no={board_no}&server={server}" + (f"&play={play}" if play else "")
    if url:
        redirect(url)
    else:
        board_no = request.forms.get('board')
        redirect(f"/app/bridge.html?board_no={board_no}{player}&server={server}" + (f"&play={play}" if play else ""))

def read_deals():
    deals = []
    with shelve.open(DB_NAME) as db:
        deal_items = sorted(list(db.items()), key=lambda x: x[1]['timestamp'], reverse=True)
        for deal_id, deal in deal_items:
            board_no_ref = ""
            board_no_index = ""
            if 'feedback' in deal: feedback = deal['feedback']
            else: feedback = ""
            if 'quality' in deal: quality = deal['quality']
            else: quality = 'ok'
            if 'board_number' in deal and deal['board_number'] is not None:
                board_no_ref = f"&board_number={deal['board_number']}"
                board_no_index = f"Board:{deal['board_number']}"
            vulnerable = C_NONE
            if (deal["vuln_ns"]) and (deal["vuln_ew"]): vulnerable = C_BOTH
            else:
                if deal["vuln_ns"]: vulnerable = C_NS
                if deal["vuln_ew"]: vulnerable = C_WE
            encoded_str_deal = encode_board(transform_hand(deal["hands"].split(" ")), deal["dealer"], vulnerable, int(deal['board_number']) if deal['board_number'] is not None else 0)                
            # Trick winners are relative to declarer so 1 and 3 are declarer and dummy
            tricks = len(list(filter(lambda x: x % 2 == 1, deal['trick_winners'])))

            if 'claimed' in deal:
                if 'claimedbydeclarer' in deal and deal['claimedbydeclarer']:
                    tricks += deal['claimed']
                else:
                    tricks += 13 - len(deal['trick_winners'])-deal['claimed']
            
            if "bidding_only" in deal and deal["bidding_only"]:
                tricks = ""

            if deal['contract'] is not None:
                deals.append({
                    'board_no_index': board_no_index,
                    'deal_id': deal_id,
                    'board_no_ref': board_no_ref,
                    'contract': deal['contract'],
                    'trick_winners_count': tricks,
                    'delete_url': f"/api/delete/deal/{deal_id}",
                    'bba': encoded_str_deal,
                    'feedback':feedback,
                    'quality': quality
                })
            else:
                deals.append({
                    'board_no_index': board_no_index,
                    'deal_id': deal_id,
                    'board_no_ref': board_no_ref,
                    'contract': "All Pass",
                    'delete_url': f"/api/delete/deal/{deal_id}",
                    'bba': encoded_str_deal,
                    'feedback':feedback,
                    'quality': quality
                })
    return deals

HISTORY_HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>历史牌局 · Ben</title>
<style>
:root{--felt:#0f5f34;--felt2:#1f7a46;--ink:#f4ecd8;--muted:#c7bfa8;--gold:#ffd66b;
  --sp:#12181f;--he:#d1344a;--di:#e07b00;--cl:#1a8a3c;}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}
body{font-family:-apple-system,"PingFang SC","Helvetica Neue",sans-serif;min-height:100vh;color:var(--ink);
  background:radial-gradient(circle at 50% 0%,var(--felt2),var(--felt) 70%);padding:20px 14px 46px;}
.wrap{max-width:680px;margin:0 auto;}
h1{font-size:22px;letter-spacing:1px;text-align:center;margin-bottom:3px;}
.sub{text-align:center;color:var(--muted);font-size:12px;margin-bottom:18px;}
.row{display:flex;align-items:center;gap:12px;text-decoration:none;color:var(--ink);cursor:pointer;
  background:linear-gradient(160deg,rgba(255,255,255,.07),rgba(0,0,0,.16));
  border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:12px 14px;margin-bottom:9px;}
.row:active{border-color:var(--gold);}
.r-contract{font-size:20px;font-weight:800;min-width:74px;letter-spacing:.5px;}
.r-mid{flex:1;font-size:13px;line-height:1.5;}
.r-res{font-size:13px;text-align:right;white-space:nowrap;}
.made{color:#7ff0a6;}.down{color:#ff8a9c;}.muted{color:var(--muted);}
.sp{color:var(--sp);}.he{color:var(--he);}.di{color:var(--di);}.cl{color:var(--cl);}.nt{color:#cdd6ff;font-weight:800;}
.dark .sp{color:#e8edf2;}
.empty{text-align:center;color:var(--muted);margin-top:40px;font-size:14px;line-height:1.8;}
.foot{text-align:center;margin-top:20px;}
.foot a{color:var(--ink);text-decoration:none;font-size:14px;padding:10px 18px;border-radius:11px;
  border:1px solid rgba(255,255,255,.2);background:rgba(0,0,0,.22);margin:0 5px;display:inline-block;}
/* detail modal */
.ov{display:none;position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.62);padding:14px;overflow:auto;}
.ov.on{display:block;}
.detail{max-width:640px;margin:14px auto;background:linear-gradient(160deg,#14653a,#0c4a2b);
  border:1px solid rgba(255,255,255,.16);border-radius:16px;padding:18px;box-shadow:0 14px 44px rgba(0,0,0,.5);}
.detail h2{font-size:17px;margin-bottom:2px;}
.dsub{color:var(--muted);font-size:12px;margin-bottom:14px;}
.sec{margin:16px 0 6px;font-size:13px;color:var(--gold);font-weight:700;letter-spacing:.06em;}
.hands{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.hand{background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.1);border-radius:9px;padding:9px 11px;font-size:13.5px;}
.hand b{display:block;color:var(--gold);font-size:11px;margin-bottom:3px;letter-spacing:.1em;}
.hand .ln{line-height:1.55;font-family:ui-monospace,Menlo,monospace;}
table.auc{width:100%;border-collapse:collapse;font-size:14px;text-align:center;}
table.auc th{color:var(--muted);font-size:11px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.15);}
table.auc td{padding:5px 0;font-weight:700;}
table.play{width:100%;border-collapse:collapse;font-size:13.5px;}
table.play td{padding:4px 5px;border-bottom:1px solid rgba(255,255,255,.08);white-space:nowrap;}
table.play td.n{color:var(--muted);width:2.2rem;}
table.play td.wn{color:#7ff0a6;text-align:right;font-size:12px;}
.parbox{background:rgba(0,0,0,.22);border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:11px 13px;font-size:14px;line-height:1.9;}
.closebtn{width:100%;margin-top:16px;font:inherit;font-size:15px;font-weight:600;padding:12px;border-radius:11px;
  border:1px solid rgba(255,255,255,.2);background:rgba(0,0,0,.24);color:var(--ink);cursor:pointer;}
</style></head><body><div class="wrap">
<h1>📜 历史牌局</h1><div class="sub">每副打完自动存档 · 点开看叫牌 + 打牌 + 双名手</div>
<div id="list"><div class="empty">加载中…</div></div>
<div class="foot"><a href="/practice">← 牌型练习</a><a href="/">🎲 开一局</a></div>
</div>
<div class="ov" id="ov"><div class="detail" id="detail"></div></div>
<script>
const RANKS="AKQJT98765432", SEATS="NESW", SEAT_CN=["北","东","南","西"];
const SYM={S:"♠",H:"♥",D:"♦",C:"♣"}, CLS={S:"sp",H:"he",D:"di",C:"cl",N:"nt"};
function strainHtml(ch){return ch==="N"?'<span class="nt">NT</span>':'<span class="'+CLS[ch]+'">'+SYM[ch]+'</span>';}
function signed(n){return (n>0?"+":"")+n;}
function fmtDate(ts){if(!ts)return"";const d=new Date(ts*1000);const p=x=>String(x).padStart(2,"0");
  return (d.getMonth()+1)+"/"+d.getDate()+" "+p(d.getHours())+":"+p(d.getMinutes());}

function contractLine(c){
  if(!c)return '<span class="muted">四家 PASS</span>';
  return c[0]+strainHtml(c[1])+' <span class="muted">'+SEAT_CN[SEATS.indexOf(c[2])]+'</span>';
}
function resultBits(d){
  if(!d.contract) return {made:'', cls:'muted', txt:'无定约'};
  const level=parseInt(d.contract[0]), need=6+level, took=d.tricks_taken;
  if(typeof took!=="number") return {txt:'', cls:'muted'};
  const diff=took-need;
  if(diff===0) return {txt:'成定约', cls:'made'};
  if(diff>0)  return {txt:'超'+diff+'墩', cls:'made'};
  return {txt:'宕'+(-diff), cls:'down'};
}

fetch('/api/deals').then(r=>r.json()).then(deals=>{
  const list=document.getElementById('list');
  if(!deals.length){list.innerHTML='<div class="empty">还没有历史牌局。<br>去打一局,打完会自动存档 📜</div>';return;}
  list.innerHTML=deals.map(d=>{
    const rb=resultBits(d);
    const par=(typeof d.parscore==="number")?'Par(NS) '+signed(d.parscore):'';
    const sc=(typeof d.score==="number")?'你 '+signed(d.score):'';
    return '<div class="row" onclick="openDeal(\''+d.id+'\')">'+
      '<div class="r-contract">'+contractLine(d.contract)+'</div>'+
      '<div class="r-mid"><span class="'+rb.cls+'">'+rb.txt+'</span>'+
        (d.board_number?' <span class="muted">· #'+d.board_number+'</span>':'')+
        '<br><span class="muted">'+fmtDate(d.timestamp)+'</span></div>'+
      '<div class="r-res">'+sc+'<br><span class="muted">'+par+'</span></div>'+
    '</div>';
  }).join('');
}).catch(e=>{document.getElementById('list').innerHTML='<div class="empty">加载失败: '+e+'</div>';});

function handHtml(seat, pbn){
  const suits=pbn.split(".");  // S.H.D.C
  const order=["S","H","D","C"];
  let lines=order.map((s,i)=>'<span class="ln"><span class="'+CLS[s]+'">'+SYM[s]+'</span> '+(suits[i]||"-")+'</span>').join("<br>");
  return '<div class="hand"><b>'+seat+'</b>'+lines+'</div>';
}
function beats(c,best,trump,led){
  const cs=c[0],bs=best[0],cr=RANKS.indexOf(c[1]),br=RANKS.indexOf(best[1]);
  if(trump){if(cs===trump&&bs!==trump)return true;if(cs!==trump&&bs===trump)return false;}
  if(cs===bs)return cr<br;
  if(cs===led&&bs!==led)return true;
  return false;
}
function cardHtml(sym){const s=sym[0];return '<span class="'+CLS[s]+'">'+SYM[s]+'</span>'+sym.slice(1);}

function openDeal(id){
  fetch('/api/deals/'+id).then(r=>r.json()).then(d=>{
    const det=document.getElementById('detail');
    const hands=(d.hands||"").split(" ");   // N E S W
    // hands grid
    let handsHtml='<div class="hands">'+SEATS.split("").map((s,i)=>handHtml(SEAT_CN[i]+"("+s+")",hands[i]||"")).join("")+'</div>';
    // auction: 4 columns N E S W, first bid at dealer column
    const bids=(d.bids||[]).map(b=>b.bid);
    const dealer=(typeof d.dealer==="number")?d.dealer:0;
    let cells=Array(dealer).fill("");  // pad to dealer column
    bids.forEach(b=>cells.push(b));
    let aucRows="";
    for(let i=0;i<cells.length;i+=4){
      aucRows+="<tr>"+[0,1,2,3].map(j=>{
        let v=cells[i+j]; if(v===undefined)v="";
        v=v.replace(/^PASS$/,"过").replace("NT","N");
        v=v.replace(/([SHDC])/,(m)=>strainHtml(m));
        return "<td>"+v+"</td>";
      }).join("")+"</tr>";
    }
    let aucHtml='<table class="auc"><tr><th>北</th><th>东</th><th>南</th><th>西</th></tr>'+aucRows+'</table>';
    // play: group into tricks of 4, compute winner
    let playHtml='<div class="muted" style="font-size:13px">（此局无打牌记录）</div>';
    const play=(d.play||[]).map(p=>p.card);
    if(play.length && d.contract){
      const trump=d.contract[1]==="N"?null:d.contract[1];
      const decl=SEATS.indexOf(d.contract[2]);
      let leader=(decl+1)%4, nsW=0,ewW=0,rows="";
      for(let t=0;t<play.length;t+=4){
        const grp=play.slice(t,t+4); if(grp.length<4)break;
        let seats=[0,1,2,3].map(k=>(leader+k)%4);
        let best=0; for(let k=1;k<grp.length;k++){if(beats(grp[k],grp[best],trump,grp[0][0]))best=k;}
        let winner=seats[best]; if(winner%2===0)nsW++;else ewW++;   // N/S even seats (N=0,S=2)
        let cellStr=grp.map((c,k)=>SEAT_CN[seats[k]]+cardHtml(c)).join("  ");
        rows+='<tr><td class="n">'+(t/4+1)+'</td><td>'+cellStr+'</td><td class="wn">'+SEAT_CN[winner]+'赢</td></tr>';
        leader=winner;
      }
      playHtml='<table class="play">'+rows+'</table>'+
        '<div class="muted" style="font-size:12px;margin-top:6px">南北得 '+nsW+' 墩 · 东西得 '+ewW+' 墩</div>';
    }
    // par box
    const parTxt=(typeof d.parscore==="number")?signed(d.parscore):"—";
    const scTxt=(typeof d.score==="number")?signed(d.score):"—";
    let parHtml='<div class="parbox">双名手 Par (南北): <b>'+parTxt+'</b><br>本局实得分 (南北): <b>'+scTxt+'</b></div>';

    det.innerHTML='<h2>'+contractLine(d.contract)+' 家做庄</h2>'+
      '<div class="dsub">'+fmtDate(d.timestamp)+(d.board_number?' · Board #'+d.board_number:'')+'</div>'+
      '<div class="sec">四家牌</div>'+handsHtml+
      '<div class="sec">叫牌过程</div>'+aucHtml+
      '<div class="sec">打牌过程</div>'+playHtml+
      '<div class="sec">双名手结果</div>'+parHtml+
      '<button class="closebtn" onclick="document.getElementById(\'ov\').classList.remove(\'on\')">关闭</button>';
    document.getElementById('ov').classList.add('on');
    document.getElementById('ov').scrollTop=0;
  });
}
</script></body></html>"""

@app.route('/api/deals')
def list_deals():
    # JSON list of all saved deals, newest first — powers the /历史 page.
    items = []
    with shelve.open(DB_NAME) as db:
        for deal_id, d in db.items():
            items.append({
                'id': deal_id,
                'timestamp': d.get('timestamp'),
                'contract': d.get('contract'),
                'declarer': d.get('declarer'),
                'dealer': d.get('dealer'),
                'tricks_taken': d.get('tricks_taken'),
                'parscore': d.get('parscore'),
                'score': d.get('score'),
                'quality': d.get('quality', ''),
                'board_number': d.get('board_number'),
            })
    items.sort(key=lambda x: x['timestamp'] or 0, reverse=True)
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(items, ensure_ascii=False)

@app.route('/历史')
@app.route('/history')
def history_page():
    response.content_type = 'text/html; charset=utf-8'
    return HISTORY_HTML

@app.route('/api/system')
def get_system():
    response.content_type = 'application/json; charset=utf-8'
    cur = current_system()
    return json.dumps({
        'current': cur,
        'systems': [{'key': k, 'name': v['name'], 'desc': v['desc']} for k, v in SYSTEMS.items()],
    }, ensure_ascii=False)

@app.route('/api/system/<key>', method=['GET', 'POST'])
def switch_system(key):
    response.content_type = 'application/json; charset=utf-8'
    if key not in SYSTEMS:
        raise HTTPError(400, "Unknown system")
    conf = SYSTEMS[key]['conf']
    script = os.path.join(BEN_ROOT, 'switch_gameserver.sh')
    # Fire the restart helper in the background; it kills the old gameserver,
    # starts the chosen config, waits for port 4443, then writes .current_system.
    subprocess.Popen(['bash', script, conf, key],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return json.dumps({'status': 'switching', 'system': key,
                       'name': SYSTEMS[key]['name']}, ensure_ascii=False)

@app.route('/home')
def home():
    deals = read_deals()
    return template('home.tpl', deals=deals, play=False)

@app.route('/play')
def home():
    deals = read_deals()
    return template('home.tpl', deals=deals, play=True)

@app.route('/app/<filename>')
def frontend(filename):
    if '?' in filename:
        filename = filename[:filename.index('?')]

    file_path = os.path.join(script_dir, '')
    resp = static_file(filename, root=file_path)
    # The frontend (html/css/js) is actively iterated; tell browsers to
    # revalidate every load so edits show up on a normal reload instead of
    # needing a hard refresh. static_file still sends ETag/Last-Modified, so
    # an unchanged file comes back as a cheap 304 rather than a full re-download.
    if filename.endswith(('.html', '.css', '.js')):
        resp.set_header('Cache-Control', 'no-cache, must-revalidate')
    return resp

@app.route('/favicon.ico')
def frontend():
    filename = 'favicon.ico'
    file_path = os.path.join(script_dir, '')    
    return static_file(filename, root=file_path)

@app.route('/api')
def index():
    return template('api.tpl')

@app.route('/gib')
def index():
    return template('gib.tpl')

@app.route('/bba')
def index():
    return template('bba.tpl', file_map=file_map)

@app.route('/autoplay')
def autoplay_page():
    return template('autoplay.tpl')

@app.route('/api/deals/<deal_id>')
def deal_data(deal_id):
    print("Getting:", deal_id)
    try:
        db = shelve.open(DB_NAME)
        deal = db[deal_id]
        db.close()

        return json.dumps(deal)
    except KeyError:
        print("Deal not found")
        raise HTTPError(404, "Deal not found")

@app.route('/api/delete/deal/<deal_id>')
def delete_deal(deal_id):
    print("Deleting:", deal_id)
    if not is_valid_deal_id(deal_id):
        print("Invalid deal ID")
        raise HTTPError(400, "Invalid deal ID")
    if host != "localhost":
        print("Port not valid")
        raise HTTPError(401, f"Not Auth {host}")
    try:
        db = shelve.open(DB_NAME)
        db.pop(deal_id)
        db.close()
        print("Returning to home")

        # Get the referrer URL to redirect back to the same page
        referrer = request.headers.get('Referer')
        if referrer:
            print("Redirecting to referrer:", referrer)
            return redirect(referrer)
        else:
            print("No referrer found, redirecting to default /home")
            return redirect('/home')  # Default fallback
    except KeyError:
        print("Deal not found")
        raise HTTPError(404, "Deal not found")

@app.route('/api/save/deal', method='POST')
def save_deal():
    data_dict = request.json  # Get JSON data from the request body
    if data_dict:
        db = shelve.open(DB_NAME)
        db[uuid.uuid4().hex] = data_dict
        db.close()
        response.status = 200  # HTTP status code: 200 OK
        response.headers['Content-Type'] = 'application/json'  # Set response content type
        return json.dumps({'message': 'Deal saved successfully'})
    else:
        print("Invalid data received")
        raise HTTPError(400, "Invalid data received")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Appserver")
    if "frontend" in script_dir:
        DB_NAME = os.path.abspath(os.path.join(os.getcwd(), "../gamedb"))
    else:
        DB_NAME = os.path.abspath(os.path.join(os.getcwd(), "gamedb"))
    parser.add_argument("--host", default="localhost", help="Hostname for appserver")
    parser.add_argument("--port", type=int, default=8080, help="Port for appserver")
    parser.add_argument("--db", default=DB_NAME, help="Db for appserver")

    args = parser.parse_args()

    DB_NAME =  args.db
    print("Reading deals from: "+DB_NAME)

    host = args.host
    port = args.port

    # Start the server
    run(app, host=host, port=port, server='gevent', log=None)    

