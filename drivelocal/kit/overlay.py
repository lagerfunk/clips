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


CHIP_X, CHIP_Y, CHIP_H = 100, 302, 48


def chip_events(ev, T, number, country, flag_cols, flag_vertical=False):
    """Append the series chip to a list of ASS events. Flag box x 100..164, text box from x 166, y 302..350.
    flag_cols: three ASS colours, top to bottom (or left to right when flag_vertical)."""
    x, y, h = CHIP_X, CHIP_Y, CHIP_H
    for k, col in enumerate(flag_cols):
        if flag_vertical:
            shape = f"m 0 0 l 21 0 21 {h} 0 {h}"
            px, py = x + k * 21, y
        else:
            shape = f"m 0 0 l 64 0 64 16 0 16"
            px, py = x, y + k * 16
        ev.append(f"Dialogue: 2,{ts(0)},{ts(T)},Box,,0,0,0,,{{\\pos({px},{py})\\an7\\bord0\\shad0"
                  f"\\1c{col}\\fad(200,0)\\p1}}{shape}{{\\p0}}")
    ev.append(f"Dialogue: 1,{ts(0)},{ts(T)},Box,,0,0,0,,{{\\pos({x + 76},{y + 10})\\an7\\fs28\\fad(200,0)}}"
              f"DRIVE LIKE A LOCAL  {{\\c&H0000C8FF&}}#{number}  {country}")


class Overlay:
    def __init__(self, number, country, footer, T):
        self.ev = []
        self.T = T
        self.number, self.country, self.footer = number, country, footer

    def add(self, t0, t1, style, x, y, text, size, extra="", layer=1):
        self.ev.append(f"Dialogue: {layer},{ts(t0)},{ts(t1)},{style},,0,0,0,,"
                       f"{{\\pos({x},{y})\\fs{size}{extra}}}{text}")

    def chip(self):
        """Series chip, one line, inside the safe zone (x >= 95, y >= 300): flag, then the series name and episode.
        Captions below start at y 360 or lower, so the chip never touches them."""
        chip_events(self.ev, self.T, self.number, self.country, self.flag)

    flag = ("&H00000000&", "&H000000DD&", "&H0000CEFF&")

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
        self.add(t0, t1, "Foot", X0, y, self.footer, fit(36, self.footer, 860, 0.6), "\\fad(200,0)")

    def foot2(self, t0, t1, y=960, size=40, width=860):
        """Source footer in up to three lines at up to `size` px (the Germany episodes' 40 px), centred at y, which
        sits between the closing lines and the end-card signs (and clear of the platform's bottom bar): split at ' · ',
        each part word-wrapped to the width."""
        per = max(8, int(width / (0.6 * size)))
        lines = []
        for part in self.footer.split(" · "):
            lines += wrap(part, per)
        size = min(size, min(fit(size, ln, width, 0.6) for ln in lines))
        self.add(t0, t1, "Foot", X0, y, "\\N".join(lines), size, "\\fad(200,0)")

    def text(self):
        return HEAD + "\n".join(self.ev) + "\n"
