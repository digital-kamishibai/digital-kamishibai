"""ポンチ絵（下書き）を SVG で描き、Chrome で PNG にする試作。
1600x900。上の帯（y 36〜180）と下の帯（y 720〜864）は台本の文字が載るので、絵の主役を置かない。
"""
import math
import random
import subprocess
import sys
from pathlib import Path

OUT = Path(sys.argv[1]).resolve()
SVG_DIR = Path(__file__).parent / 'svg'
SVG_DIR.mkdir(exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

INK = '#3a3a3a'
NOTE = '#7a6f5f'
BLUE, YEL, RED, GRN, RUST, GRAY = '#bcd9f2', '#fbe3a0', '#f5bfae', '#c9e7b8', '#e8b48f', '#dcd6cc'

HEAD = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
<defs>
  <filter id="r" x="-5%" y="-5%" width="110%" height="110%">
    <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="2" seed="7"/>
    <feDisplacementMap in="SourceGraphic" scale="5"/>
  </filter>
  <marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M1,1 L9,5 L1,9" fill="none" stroke="{INK}" stroke-width="1.6" stroke-linecap="round"/>
  </marker>
  <marker id="an" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M1,1 L9,5 L1,9" fill="none" stroke="{NOTE}" stroke-width="1.6" stroke-linecap="round"/>
  </marker>
</defs>
<style>
  text {{ font-family: 'UD Digi Kyokasho N-R', 'Yu Gothic UI', sans-serif; fill: {INK}; }}
  .n {{ fill: {NOTE}; font-size: 26px; }}
  .l {{ font-size: 32px; }}
  .s {{ stroke: {INK}; stroke-width: 4; fill: none; stroke-linecap: round; stroke-linejoin: round; }}
  .t {{ stroke: {INK}; stroke-width: 2.5; fill: none; stroke-linecap: round; }}
  .g {{ stroke: #3f9a5a; stroke-width: 5; }}
  .w {{ stroke: #ffffff; }}
  .o {{ stroke: #f2a33a; stroke-width: 5; }}
  .d {{ stroke: {NOTE}; stroke-width: 2.5; fill: none; stroke-dasharray: 8 8; stroke-linecap: round; }}
</style>
<rect width="1600" height="900" fill="#f7f3ea"/>
<rect x="18" y="18" width="1564" height="864" fill="none" stroke="#d8cfbe" stroke-width="3" stroke-dasharray="14 10"/>
<text x="40" y="30" class="n" style="font-size:20px">ポンチ絵（下書き）— こんな感じの絵、という案です</text>
<g filter="url(#r)">
'''
TAIL = '</g></svg>'


def T(x, y, s, cls='l', anchor='middle', size=None, extra=''):
    st = f' style="font-size:{size}px"' if size else ''
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{st} {extra}>{s}</text>'


def C(x, y, r, fill='none', cls='s', extra=''):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" class="{cls}" style="fill:{fill}" {extra}/>'


def L(x1, y1, x2, y2, cls='s', arrow=False, note=False):
    m = (' marker-end="url(#an)"' if note else ' marker-end="url(#a)"') if arrow else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}"{m}/>'


def P(d, cls='s', fill='none', arrow=False, extra=''):
    m = ' marker-end="url(#a)"' if arrow else ''
    return f'<path d="{d}" class="{cls}" style="fill:{fill}"{m} {extra}/>'


def note(x, y, s, tx, ty, anchor='middle'):
    """注記: 文字と、指す先への細い矢印"""
    return T(x, y, s, 'n', anchor) + L(x if anchor == 'middle' else (x + 10 if anchor == 'start' else x - 10),
                                         y + 10 if ty > y else y - 30, tx, ty, 'd', True, True)


def sun(x, y, r, rays=True, fill=YEL):
    s = C(x, y, r, fill)
    if rays:
        for i in range(12):
            a = i * math.pi / 6
            s += L(x + (r + 12) * math.cos(a), y + (r + 12) * math.sin(a),
                   x + (r + 34) * math.cos(a), y + (r + 34) * math.sin(a), 't')
    return s


def earth(x, y, r):
    """青い丸に、ざっくりした陸"""
    k = r / 100

    def blob(sx, sy, pts):
        d = f'M{x+sx*k:.1f},{y+sy*k:.1f}'
        for i in range(0, len(pts), 4):
            d += f' q{pts[i]*k:.1f},{pts[i+1]*k:.1f} {pts[i+2]*k:.1f},{pts[i+3]*k:.1f}'
        return d + ' z'
    land = blob(-60, -40, [30, -30, 60, -5, 20, 25, -10, 45, -30, 10, -50, -40]) + ' ' + \
        blob(20, 10, [40, -10, 55, 25, -10, 40, -45, 30, -25, -20, -10, -55])
    return C(x, y, r, BLUE) + P(land, 't', GRN)


def person(x, y, h=120, arms='down'):
    """棒人間（y は足元）"""
    k = h / 120
    head = C(x, y - 100 * k, 18 * k, '#fff')
    body = L(x, y - 82 * k, x, y - 35 * k)
    legs = L(x, y - 35 * k, x - 18 * k, y) + L(x, y - 35 * k, x + 18 * k, y)
    if arms == 'up':
        a = L(x, y - 70 * k, x - 28 * k, y - 100 * k) + L(x, y - 70 * k, x + 28 * k, y - 100 * k)
    else:
        a = L(x, y - 70 * k, x - 26 * k, y - 45 * k) + L(x, y - 70 * k, x + 26 * k, y - 45 * k)
    return head + body + legs + a


def spiral(x, y, r, arms=2, tilt=1.0, cls='s'):
    """うずまき銀河"""
    out = C(x, y, r * 0.16, YEL)
    for a0 in range(arms):
        pts = []
        for i in range(60):
            t = i / 59
            ang = a0 * 2 * math.pi / arms + t * 3.3
            rr = r * (0.16 + 0.84 * t)
            pts.append((x + rr * math.cos(ang), y + rr * math.sin(ang) * tilt))
        out += P('M' + ' L'.join(f'{px:.1f},{py:.1f}' for px, py in pts), cls)
    return out


def galaxy_small(x, y, r, rot):
    return (f'<g transform="rotate({rot} {x} {y})">'
            f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{r*0.45}" class="t" style="fill:#ede6d6"/>'
            f'{C(x, y, r*0.18, YEL, "t")}</g>')


def thermo(x, y, h, level, fill):
    """温度計（y は球の中心）"""
    return (P(f'M{x-12},{y-16} L{x-12},{y-h} a12,12 0 0 1 24,0 L{x+12},{y-16}', 's', '#fff')
            + C(x, y, 22, fill)
            + f'<line x1="{x}" y1="{y-10}" x2="{x}" y2="{y-10-level*(h-30)}" style="stroke:#c0503a;stroke-width:12;stroke-linecap:round"/>')


def slide(n, body):
    (SVG_DIR / f'{n:02d}.svg').write_text(HEAD + body + TAIL, encoding='utf-8')


# ---------------------------------------------------------------- 1 表紙
b = ''
b += spiral(260, 470, 120, tilt=0.6)
b += T(260, 640, '銀河', 'n')
b += L(420, 470, 560, 470, 'd', True, True)
b += sun(700, 470, 60)
b += T(700, 610, '太陽', 'n')
b += L(820, 470, 960, 470, 'd', True, True)
b += earth(1150, 560, 150)
b += person(1150, 412, 110, 'up')
b += T(1350, 330, 'わたし', 'n', 'start')
b += L(1340, 322, 1180, 330, 'd', True, True)
b += T(800, 790, '宇宙の端っこから、順番に「わたし」へ近づいていく', 'n')
slide(1, '<g transform="translate(0,90)">' + b.replace('y="790"', 'y="700"') + '</g>')

# ---------------------------------------------------------------- 2 銀河の数
random.seed(2)
b = ''
spots = []
while len(spots) < 34:
    x, y = random.randint(110, 1490), random.randint(220, 690)
    if all((x - a) ** 2 + (y - c) ** 2 > 110 ** 2 for a, c in spots) and not (700 < x < 900 and 380 < y < 560) and not (900 < x < 1420 and 340 < y < 440):
        spots.append((x, y))
for x, y in spots:
    b += galaxy_small(x, y, random.randint(22, 42), random.randint(0, 170))
for i in range(120):
    b += C(random.randint(40, 1560), random.randint(200, 700), 2, INK, 't')
b += spiral(800, 470, 70, tilt=0.7)
b += C(800, 470, 100, 'none', 'd')
b += '<rect x="925" y="370" width="470" height="44" rx="8" style="fill:#f7f3ea"/>'
b += T(940, 400, 'わたしたちの銀河は、このうちの1つ', 'n', 'start')
slide(2, b)

# ---------------------------------------------------------------- 3 天の川銀河
b = ''
b += spiral(560, 450, 250, arms=2, tilt=0.95)
b += P('M560,200 Q640,330 560,450', 'd')
b += C(560, 450, 12, INK)
b += T(560, 215, 'まん中（次の絵）', 'n')
b += f'<polygon points="742,372 750,350 758,372 780,372 762,385 769,407 750,394 731,407 738,385 720,372" class="t" style="fill:#f2a33a"/>'
b += T(820, 330, '太陽はここ（うずの腕の中）', 'n', 'start')
b += L(830, 340, 770, 365, 'd', True, True)
b += L(310, 705, 810, 705, 't', True)
b += L(810, 705, 310, 705, 't', True)
b += T(560, 695, '約10万光年', 'n')
# 横から見た図
b += f'<ellipse cx="1260" cy="520" rx="210" ry="26" class="s" style="fill:#ede6d6"/>'
b += f'<ellipse cx="1260" cy="520" rx="48" ry="34" class="s" style="fill:{YEL}"/>'
b += T(1260, 430, '横から見ると', 'l')
b += T(1260, 610, '＝ 夏の夜の「天の川」', 'n')
slide(3, b)

# ---------------------------------------------------------------- 4 ブラックホール
b = ''
b += f'<rect x="520" y="200" width="560" height="500" rx="10" class="s" style="fill:#2b2621"/>'
b += C(800, 450, 175, 'none', 's').replace(INK, '#f2a33a', 1).replace('class="s"', 'style="fill:none;stroke:#f2a33a;stroke-width:46;opacity:.85"')
b += C(800, 450, 120, '#0d0b09')
b += T(800, 245, '2022年の写真のような絵', 'n', extra='style="fill:#d9cfbf;font-size:24px"')
b += T(1120, 330, '光るガスの輪', 'n', 'start')
b += L(1115, 340, 975, 400, 'd', True, True)
b += T(1120, 540, '黒い影', 'n', 'start')
b += L(1115, 532, 880, 470, 'd', True, True)
b += T(260, 380, 'わたしたちは', 'n')
b += T(260, 415, 'ずーっと遠く', 'n')
b += T(260, 450, '（光で2万7千年）', 'n')
b += L(360, 520, 510, 470, 'd', True, True)
b += C(190, 520, 9, BLUE, 't')
slide(4, b)

# ---------------------------------------------------------------- 5 太陽系
b = ''
b += P('M60,250 A260,260 0 0 1 60,690', 's', YEL)
b += T(110, 470, '太陽', 'l', 'start')
planets = [(380, 10, GRAY, '水星'), (500, 18, RED, '金星'), (640, 20, BLUE, '地球'), (780, 14, RUST, '火星'),
           (980, 52, YEL, '木星'), (1190, 44, YEL, '土星'), (1360, 30, BLUE, '天王星'), (1500, 29, BLUE, '海王星')]
for x, r, f, name in planets:
    b += P(f'M{x},280 Q{x+40},470 {x},660', 'd')
    if name == '土星':
        b += f'<ellipse cx="{x}" cy="470" rx="{r*1.9}" ry="{r*0.5}" class="t" style="fill:none"/>'
    b += C(x, 470, r, f, 's' if name == '地球' else 't')
    b += T(x, 470 + r + 40, name, 'n', size=22)
b += C(640, 470, 44, 'none', 'd')
b += L(240, 360, 620, 360, 's', True)
b += T(430, 340, '光で約8分', 'l')
b += T(640, 600, '3番目', 'n')
slide(5, b)

# ---------------------------------------------------------------- 6 熱すぎず、寒すぎず
b = ''
b += P('M40,220 A240,240 0 0 1 40,700', 's', YEL)
b += C(470, 450, 120, RED)
for dx in (-50, 0, 50):
    b += P(f'M{470+dx},300 q-14,-20 0,-40 q14,-20 0,-40', 't')
b += T(470, 640, '金星', 'l')
b += T(470, 680, 'あつい！', 'n')
b += earth(880, 450, 125)
b += P('M880,250 q-26,36 0,52 q26,-16 0,-52 z', 't', BLUE)
b += T(880, 640, '地球', 'l')
b += T(880, 680, '水が水のまま', 'n')
b += C(1290, 450, 95, RUST)
for (cx, cy) in ((1250, 420), (1320, 480)):
    for k in range(3):
        a = k * math.pi / 3
        b += L(cx - 20 * math.cos(a), cy - 20 * math.sin(a), cx + 20 * math.cos(a), cy + 20 * math.sin(a), 't w')
b += T(1290, 640, '火星', 'l')
b += T(1290, 680, 'さむい…', 'n')
b += T(880, 250, '', 'n')
b += P('M680,250 Q880,180 1080,250', 'd')
b += T(880, 215, 'ちょうどいい', 'l')
slide(6, b)

# ---------------------------------------------------------------- 7 空気の毛布
b = ''
b += sun(130, 450, 70)
# 左: 空気なし
b += C(520, 450, 120, '#e4eef6')
for (cx, cy) in ((480, 410), (560, 470), (505, 505)):
    for k in range(3):
        a = k * math.pi / 3
        b += L(cx - 18 * math.cos(a), cy - 18 * math.sin(a), cx + 18 * math.cos(a), cy + 18 * math.sin(a), 't')
b += T(520, 625, '空気がないと', 'l')
b += T(520, 665, 'こおってしまう', 'n')
# 右: 毛布つき
b += C(1020, 450, 170, 'none', 's').replace('class="s"', 'style="fill:none;stroke:#f3c7a6;stroke-width:44;opacity:.8"')
b += C(1020, 450, 170, 'none', 'd')
b += earth(1020, 450, 120)
b += L(260, 300, 860, 330, 't', True)
b += L(260, 610, 870, 560, 't', True)
b += P('M1020,330 q40,-50 0,-110', 't').replace('class="t"', 'class="t" stroke-dasharray="6 6"')
b += T(1250, 280, '毛布（空気）が', 'n', 'start')
b += T(1250, 315, '熱を少しだけ', 'n', 'start')
b += T(1250, 350, 'にがさない', 'n', 'start')
b += L(1245, 330, 1170, 400, 'd', True, True)
b += T(1020, 665, 'ちょうどいい厚さ', 'n')
b += C(1430, 560, 50, RED, 't')
b += C(1430, 560, 78, 'none', 't').replace('class="t"', 'style="fill:none;stroke:#f3c7a6;stroke-width:40;opacity:.8"')
b += T(1430, 675, '金星＝厚すぎ', 'n', size=22)
slide(7, b)

# ---------------------------------------------------------------- 8 見えないバリア
b = ''
b += sun(120, 450, 80)
random.seed(8)
for i in range(7):
    y = 260 + i * 65
    for x in range(260, 760, 70):
        b += C(x + random.randint(-10, 10), y + random.randint(-8, 8), 5, INK, 't')
for y in (300, 380, 520, 600):
    b += P(f'M770,{y} Q930,{y} 1060,{y-100 if y<450 else y+100}', 't', arrow=True)
b += T(500, 235, '太陽風（小さなつぶの流れ）', 'n')
b += earth(1150, 450, 90)
for s in (1, 1.6, 2.2):
    b += f'<ellipse cx="{1150+30*s}" cy="450" rx="{120*s}" ry="{75*s}" class="d"/>'
b += P('M1100,355 q25,-18 50,0 q25,-18 50,0', 't g')
b += P('M1100,545 q25,18 50,0 q25,18 50,0', 't g')
b += T(1300, 300, 'オーロラ', 'n', 'start')
b += L(1295, 300, 1205, 345, 'd', True, True)
b += T(1170, 660, '地球の磁場＝見えないバリア', 'n', 'start')
slide(8, b)

# ---------------------------------------------------------------- 9 青い点
b = ''
b += f'<rect x="300" y="110" width="1000" height="580" class="s" style="fill:#2b2621"/>'
for x0, col in ((480, '#7a5a3a'), (720, '#6a6a4a'), (1000, '#4a5a6a')):
    b += f'<polygon points="{x0},110 {x0+90},110 {x0+170},690 {x0+60},690" style="fill:{col};opacity:.7"/>'
b += C(865, 430, 4, '#cfe6ff', 't')
b += C(865, 430, 40, 'none', 't o')
b += T(1330, 330, 'これが地球', 'l', 'start')
b += T(1330, 370, '（点より小さい点）', 'n', 'start')
b += L(1325, 345, 910, 425, 'd', True, True)
b += T(150, 300, 'ボイジャー1号が', 'n')
b += T(150, 335, 'ふり返って撮った', 'n')
b += T(150, 370, '写真のような絵', 'n')
slide(9, b)

# ---------------------------------------------------------------- 10 宇宙の1年カレンダー
b = ''
x0, w = 120, 1360
for m in range(12):
    x = x0 + m * w / 12
    b += f'<rect x="{x:.0f}" y="300" width="{w/12:.0f}" height="90" class="t" style="fill:{"#fff" if m < 11 else YEL}"/>'
    b += T(x + w / 24, 355, f'{m+1}月', 'n', size=24)
b += T(x0, 285, '1/1 宇宙のはじまり', 'n', 'start', size=24)
b += L(x0 + 4, 290, x0 + 4, 300, 't')
b += L(x0 + 8 * w / 12 + 5, 410, x0 + 8 * w / 12 + 5, 450, 't', True)
b += T(x0 + 8 * w / 12 + 5, 480, '太陽系', 'n', size=24)
b += L(x0 + 9 * w / 12 - 10, 410, x0 + 9 * w / 12 - 10, 520, 't', True)
b += T(x0 + 9 * w / 12 - 10, 550, '生きもの', 'n', size=24)
# 12月31日を拡大
b += P(f'M{x0+11*w/12},390 L700,590 M{x0+w},390 L1480,590', 'd')
b += f'<rect x="700" y="590" width="780" height="110" class="s" style="fill:#fff"/>'
b += L(1090, 590, 1090, 700, 't')
b += T(895, 630, '12月30日', 'n', size=24)
b += T(895, 680, '恐竜がいなくなる', 'n', size=22)
b += T(1285, 630, '12月31日', 'n', size=24)
b += f'<rect x="1440" y="595" width="36" height="100" style="fill:{RED};opacity:.9"/>'
b += T(1430, 680, '最後の12分に人間', 'n', 'end', size=22)
b += T(400, 650, '138億年 → 1年に縮める', 'l')
slide(10, b)

# ---------------------------------------------------------------- 11 一生は0.2秒
b = ''
b += P('M330,470 Q600,300 870,470', 's')
b += P('M330,470 Q600,560 870,470', 's', '#fff')
b += P('M330,470 Q600,420 870,470', 's', '#f7f3ea')
for i in range(7):
    x = 400 + i * 78
    y = 470 + 30 - abs(i - 3) * 8
    b += L(x, y + 25, x - 8, y + 55, 't')
b += T(600, 640, 'まばたき、ひとつぶん', 'l')
# ストップウォッチ
b += C(1200, 470, 170, '#fff')
b += f'<rect x="1180" y="270" width="40" height="30" class="s" style="fill:#fff"/>'
for i in range(12):
    a = i * math.pi / 6
    b += L(1200 + 150 * math.sin(a), 470 - 150 * math.cos(a), 1200 + 135 * math.sin(a), 470 - 135 * math.cos(a), 't')
b += L(1200, 470, 1200 + 120 * math.sin(0.5), 470 - 120 * math.cos(0.5), 's')
b += T(1200, 720, '0.2 秒', 'l', size=48)
b += T(1200, 770, '（100年生きても、宇宙のカレンダーでは）', 'n', size=22)
slide(11, b)

# ---------------------------------------------------------------- 12 体の中にも「ちょうどいい」
b = ''
b += person(800, 640, 300)
b += sun(300, 330, 50)
for dx in (0, 30):
    b += P(f'M{730+dx},420 q-12,20 0,30 q12,-10 0,-30 z', 't', BLUE)
b += T(300, 470, 'あつい → 汗で冷やす', 'n')
b += L(420, 420, 700, 440, 'd', True, True)
for k in range(3):
    a = k * math.pi / 3
    b += L(1300 - 40 * math.cos(a), 330 - 40 * math.sin(a), 1300 + 40 * math.cos(a), 330 + 40 * math.sin(a), 's')
b += P('M890,470 l14,-8 l-10,-8 l14,-8', 't') + P('M890,520 l14,-8 l-10,-8 l14,-8', 't')
b += T(1300, 470, 'さむい → ふるえて温める', 'n')
b += L(1170, 420, 930, 470, 'd', True, True)
b += thermo(1000, 640, 260, 0.55, RED)
b += T(1035, 600, '36〜37℃', 'n', 'start')
b += T(800, 220, '', 'n')
slide(12, b)

# ---------------------------------------------------------------- 13 散らかる、片づける
b = ''
b += f'<rect x="160" y="270" width="760" height="420" class="s" style="fill:#fff"/>'
random.seed(13)
for i in range(14):
    x, y = random.randint(200, 560), random.randint(560, 670)
    b += f'<rect x="{x}" y="{y}" width="{random.randint(24,50)}" height="{random.randint(14,30)}" transform="rotate({random.randint(-40,40)} {x} {y})" class="t" style="fill:{random.choice([RED, BLUE, YEL, GRN])}"/>'
b += f'<rect x="700" y="420" width="180" height="250" class="t" style="fill:#ede6d6"/>'
for y in (500, 580):
    b += L(700, y, 880, y, 't')
b += person(640, 680, 200)
b += L(668, 600, 720, 680, 's') + P('M705,680 l40,0 l-10,-20 z', 't', YEL)
b += T(370, 520, 'ちらかる', 'n')
b += T(790, 400, 'しまう', 'n')
# 天びん
b += L(1250, 690, 1250, 420, 's')
b += P('M1220,690 L1280,690', 's')
b += L(1060, 470, 1440, 380, 's')
b += P('M1020,470 L1100,470 L1060,540 Z', 't', RED)
b += P('M1400,380 L1480,380 L1440,450 Z', 't', BLUE)
b += T(1060, 580, '散らかる速さ', 'n')
b += T(1440, 490, '片づける速さ', 'n')
b += T(1250, 330, 'どっちが速い？', 'n')
slide(13, '<g transform="translate(0,80)">' + b + '</g>')

# ---------------------------------------------------------------- 14 運動・睡眠・食事
b = ''
for cx in (350, 800, 1250):
    b += C(cx, 430, 170, '#fff')
# 走る
b += C(370, 330, 20, '#fff') + L(360, 350, 340, 430) + L(355, 370, 395, 395) + L(355, 370, 315, 360)
b += L(340, 430, 380, 470) + L(380, 470, 365, 520) + L(340, 430, 300, 470) + L(300, 470, 270, 460)
b += T(350, 650, '運動', 'l')
# 寝る
b += f'<rect x="680" y="440" width="240" height="60" rx="10" class="s" style="fill:{BLUE}"/>'
b += C(720, 425, 22, '#fff') + T(860, 380, 'Z z z', 'l')
b += T(800, 650, '睡眠', 'l')
# 食事
b += P('M1150,430 A100,90 0 0 0 1350,430 Z', 's', '#fff')
b += P('M1180,430 q20,-40 40,0 q20,-40 40,0 q20,-40 40,0 q20,-40 40,0', 't')
b += L(1320, 300, 1380, 420) + L(1340, 300, 1395, 415)
b += T(1250, 650, '食事', 'l')
b += T(800, 245, '3つとも「片づけ」の味方', 'n')
slide(14, b)

# ---------------------------------------------------------------- 15 太陽にも寿命がある
b = ''
b += L(120, 640, 1500, 640, 's', True)
b += T(250, 690, 'いま', 'n')
b += T(700, 690, '約10億年後', 'n')
b += T(1250, 690, '約50億年後', 'n')
b += sun(200, 420, 45)
b += earth(330, 470, 30)
b += sun(620, 420, 75)
b += earth(800, 470, 30)
b += P('M785,430 q-10,-20 0,-40 M815,430 q10,-20 0,-40', 't')
b += T(800, 360, '海がじょうはつ', 'n')
b += C(1250, 420, 200, '#f0a08a')
b += T(1250, 430, '赤色巨星', 'l')
b += T(1250, 470, '（大きくふくらむ）', 'n')
slide(15, b)

# ---------------------------------------------------------------- 16 ちょうどいい星で、長く生きる
b = ''
b += C(800, 560, 280, 'none', 's').replace('class="s"', 'style="fill:none;stroke:#f3c7a6;stroke-width:40;opacity:.8"')
for s in (1.25, 1.5):
    b += f'<ellipse cx="800" cy="560" rx="{300*s}" ry="{200*s}" class="d"/>'
b += earth(800, 560, 230)
b += person(800, 330, 120, 'up')
b += T(250, 300, '毛布', 'n') + L(290, 310, 560, 420, 'd', True, True)
b += T(1350, 290, 'バリア', 'n') + L(1310, 300, 1180, 380, 'd', True, True)
for (cx, label) in ((190, '夜ごはん'), (190, ''), ):
    pass
b += P('M120,700 A60,50 0 0 0 240,700 Z', 't', '#fff') + T(180, 790, '今日の夜ごはん', 'n', size=22)
b += f'<rect x="1310" y="690" width="140" height="40" rx="8" class="t" style="fill:{BLUE}"/>' + T(1380, 790, '今夜の睡眠', 'n', size=22)
b += P('M1490,700 q10,-20 20,0 q5,30 -10,30 q-15,-5 -10,-30 z', 't', '#fff') + T(1500, 790, '朝の一歩', 'n', size=22)
slide(16, b)

# ---------------------------------------------------------------- 17 青い点の上で
b = ''
b += f'<rect x="140" y="140" width="640" height="440" class="s" style="fill:#2b2621"/>'
for x0, col in ((260, '#7a5a3a'), (450, '#6a6a4a'), (620, '#4a5a6a')):
    b += f'<polygon points="{x0},140 {x0+60},140 {x0+110},580 {x0+40},580" style="fill:{col};opacity:.7"/>'
b += C(540, 360, 4, '#cfe6ff', 't')
b += P('M560,350 L1000,180 M560,370 L1000,690', 'd')
b += C(1180, 440, 240, BLUE, 's')
b += P('M960,520 Q1180,420 1400,520', 't', GRN)
b += person(1080, 470, 110, 'up') + person(1200, 460, 140) + person(1300, 470, 100)
b += T(1180, 175, 'あの点の上に、みんながいる', 'n')
slide(17, b)

# ---------------------------------------------------------------- PNG へ
OUT.mkdir(parents=True, exist_ok=True)
for svg in sorted(SVG_DIR.glob('*.svg')):
    html = svg.with_suffix('.html')
    html.write_text('<html><body style="margin:0;overflow:hidden">' + svg.read_text(encoding='utf-8') + '</body></html>',
                    encoding='utf-8')
    png = OUT / (svg.stem + '.png')
    subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
                    f'--screenshot={png}', '--window-size=1600,900', html.as_uri()],
                   check=True, capture_output=True)
    print(png)
