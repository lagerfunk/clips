"""Burned-in captions for Drive Like a Local junction episodes (ASS, 1080x1920), same look as episode 1.
Text stays inside x 95..955 and y 300..1500 so the TikTok and Reels buttons and captions never cover it.
Markup inside a line: [y]..[/] yellow, [r]..[/] red, [g]..[/] green, [a]..[/] [b]..[/] [c]..[/] the badge colours of cars A, B, C."""

Y, R_, Wt = "&H0000C8FF&", "&H00303BFF&", "&H00FFFFFF&"
CA, CB, CC, G_ = "&H0000BFFF&", "&H00FFBF00&", "&H009933FF&", "&H0044DD22&"
X0 = 525

HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat Black,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,7,4,5,40,40,0,1
Style: Box,Montserrat ExtraBold,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,3,10,0,7,0,0,0,1
Style: Fine,Montserrat Black,64,&H00FFFFFF,&H00FFFFFF,&H002A1FE0,&H00000000,0,0,0,0,100,100,0,0,3,18,0,5,0,0,0,1
Style: Count,Montserrat Black,200,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,10,6,5,0,0,0,1
Style: Foot,Montserrat ExtraBold,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,4,2,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

POP = "\\fad(90,120)\\fscx70\\fscy70\\t(0,140,\\fscx104\\fscy104)\\t(140,230,\\fscx100\\fscy100)"
SLAM = "\\fad(60,120)\\fscx40\\fscy40\\t(0,120,\\fscx110\\fscy110)\\t(120,220,\\fscx100\\fscy100)"
TAGS = {"[y]": Y, "[r]": R_, "[a]": CA, "[b]": CB, "[c]": CC, "[g]": G_}


def ts(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def markup(text, base=Wt):
    for k, v in TAGS.items():
        text = text.replace(k, "{\\c" + v + "}")
    return text.replace("[/]", "{\\c" + base + "}")


def plain(text):
    for k in list(TAGS) + ["[/]"]:
        text = text.replace(k, "")
    return text


def fit(size, text, width=860, k=0.62):
    return int(min(size, width / max(1, k * len(plain(text)))))


def wrap(text, max_chars):
    """Greedy word wrap that keeps markup tags attached to their words and never breaks inside a tag pair."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if cur and len(plain(cand)) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    # carry an open colour tag over a line break
    out, open_tag = [], None
    for ln in lines:
        if open_tag:
            ln = open_tag + ln
            open_tag = None
        opens = [i for i in range(len(ln)) if ln.startswith(tuple(TAGS), i)]
        closes = [i for i in range(len(ln)) if ln.startswith("[/]", i)]
        if opens and (not closes or opens[-1] > closes[-1]):
            open_tag = ln[opens[-1]:opens[-1] + 3]
            ln = ln + "[/]"
        out.append(ln)
    return out


class Overlay:
    def __init__(self, number, country, footer, T):
        self.ev = []
        self.T = T
        self.number, self.country, self.footer = number, country, footer

    def add(self, t0, t1, style, x, y, text, size, extra="", layer=1):
        self.ev.append(f"Dialogue: {layer},{ts(t0)},{ts(t1)},{style},,0,0,0,,"
                       f"{{\\pos({x},{y})\\fs{size}{extra}}}{text}")

    def chip(self):
        T = self.T
        self.add(0, T, "Box", 60, 236, "DRIVE LIKE A LOCAL", 34, "\\fad(200,0)")
        self.add(0, T, "Box", 162, 300, f"#{self.number}  {self.country}", 30, "\\fad(200,0)\\c&H0000C8FF&")
        for k, col in enumerate(("&H00000000&", "&H000000DD&", "&H0000CEFF&")):
            self.ev.append(f"Dialogue: 2,{ts(0)},{ts(T)},Box,,0,0,0,,{{\\pos(50,{291 + k * 18})\\an7\\bord0\\shad0"
                           f"\\1c{col}\\fad(200,0)\\p1}}m 0 0 l 92 0 92 18 0 18{{\\p0}}")
        self.ev.append(f"Dialogue: 1,{ts(0)},{ts(T)},Box,,0,0,0,,{{\\pos(46,287)\\an7\\bord0\\shad0\\1c&H00FFFFFF&"
                       f"\\fad(200,0)\\p1}}m 0 0 l 100 0 100 62 0 62{{\\p0}}")

    def block(self, t0, t1, lines, y_top, size=74, step=1.16, style="Cap", anim=POP, stagger=0.1, room=None,
              max_size=None):
        """Lines stacked from y_top, each line sized to fit 860 px; shrinks to fit `room` px if given."""
        sizes = [fit(max_size or size, ln) for ln in lines]
        total = sum(s * step for s in sizes)
        if room and total > room:
            sizes = [int(s * room / total) for s in sizes]
        y = y_top
        for i, (ln, s) in enumerate(zip(lines, sizes)):
            self.add(t0 + stagger * i, t1, style, X0, int(y + s * 0.575), markup(ln), s, anim)
            y += s * step
        return y

    def count(self, t0, digits=("3", "2", "1"), each=1.0, y=760, x=X0, size=200):
        for k, d in enumerate(digits):
            a = t0 + k * each
            self.add(a, a + each - 0.05, "Count", x, y, d, size,
                     "\\fad(40,160)\\fscx150\\fscy150\\t(0,180,\\fscx100\\fscy100)")

    def fine(self, t0, t1, lead, amount, extra, y_top=760):
        """Fine card: lead line(s), the amount in the red box, extra line(s) (points, ban)."""
        y = y_top
        for i, ln in enumerate(lead):
            s = fit(62, ln)
            self.add(t0 + 0.1 * i, t1, "Cap", X0, int(y + s * 0.575), markup(ln), s, POP)
            y += s * 1.16
        s = fit(150, amount)
        y += 14
        self.add(t0 + 0.12 * len(lead), t1, "Fine", X0, int(y + s * 0.575), markup(amount), s, SLAM)
        y += s * 1.35
        for j, ln in enumerate(extra):
            s = fit(56, ln)
            self.add(t0 + 0.12 * (len(lead) + 1 + j), t1, "Cap", X0, int(y + s * 0.575), markup(ln), s, POP)
            y += s * 1.16
        return y

    def foot(self, t0, t1, y=1470):
        self.add(t0, t1, "Foot", X0, y, self.footer, fit(30, self.footer, 860, 0.6), "\\fad(200,0)")

    def text(self):
        return HEAD + "\n".join(self.ev) + "\n"
