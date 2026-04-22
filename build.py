#!/usr/bin/env python3
"""
build.py — 从 content.md 生成 index.html
用法: python build.py
无需安装任何额外依赖，使用 Python 标准库即可。

可识别的 H1 Section（H1 = 以 "# " 开头的标题）:
    About                — 个人简介段落
    Education            — 教育经历（时间线）
    Research Experience  — 科研经历（时间线 + 研究方向 + bullet 点）
    News                 — 近期动态
    Publications         — 论文（按年份分组）
    Projects             — 项目
    Awards               — 奖项（带年份）
    Student Activities   — 学生工作
    Skills               — 技能（按分类）
    Contact              — 联系方式
"""

import re, html as hl
from pathlib import Path

# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def read(path):  return Path(path).read_text(encoding='utf-8')
def write(path, s): Path(path).write_text(s, encoding='utf-8')
def esc(s): return hl.escape(str(s), quote=True)

def inline(text):
    """
    把 Markdown 内联语法转成 HTML：
      [文字](链接)  →  <a href="...">文字</a>
      **加粗**      →  <strong>加粗</strong>
      *斜体*        →  <em>斜体</em>
    其余文字做 HTML 转义，防止 XSS。
    """
    spans = []  # [(start, end, html_replacement)]

    # 1. 链接
    for m in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', text):
        spans.append((m.start(), m.end(),
            f'<a href="{esc(m.group(2))}" target="_blank" rel="noopener">'
            f'{esc(m.group(1))}</a>'))

    # 2. 加粗
    used = {i for s, e, _ in spans for i in range(s, e)}
    for m in re.finditer(r'\*\*(.+?)\*\*', text):
        if m.start() not in used:
            spans.append((m.start(), m.end(),
                f'<strong>{esc(m.group(1))}</strong>'))
            used.update(range(m.start(), m.end()))

    # 3. 斜体
    for m in re.finditer(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', text):
        if m.start() not in used:
            spans.append((m.start(), m.end(),
                f'<em>{esc(m.group(1))}</em>'))
            used.update(range(m.start(), m.end()))

    # 4. 按位置拼装，非标记部分做 HTML 转义
    spans.sort(key=lambda x: x[0])
    out, pos = '', 0
    for start, end, tag in spans:
        if start >= pos:
            out += esc(text[pos:start])
            out += tag
            pos = end
    return out + esc(text[pos:])


# ─── 按 H1 切分文档 ────────────────────────────────────────────────────────────

def split_h1(md):
    """返回 {section_name: body_text} 字典，按 H1 标题切分。"""
    sections, name, lines = {}, None, []
    for line in md.splitlines():
        if re.match(r'^# [^#]', line):
            if name is not None:
                sections[name] = '\n'.join(lines).strip()
            name, lines = line[2:].strip(), []
        elif name is not None:
            lines.append(line)
    if name:
        sections[name] = '\n'.join(lines).strip()
    return sections


def kv(line, key):
    """从 '**Key:** value' 或 'Key: value' 提取 value，失败返回 None。"""
    m = (re.match(rf'\*\*{re.escape(key)}:\*\*\s*(.*)', line.strip()) or
         re.match(rf'{re.escape(key)}:\s*(.*)', line.strip()))
    return m.group(1).strip() if m else None


# ─── Section 解析器 ────────────────────────────────────────────────────────────

def parse_about(text):
    """返回段落列表。"""
    return [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]


def parse_education(text):
    """
    格式:
      ## 学校名
      Degree: 学位
      Period: 时间段
      Note:   备注（GPA 等）
    """
    schools, cur = [], None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith('## '):
            cur = {'school': s[3:], 'degree': '', 'period': '', 'note': ''}
            schools.append(cur)
        elif cur:
            for key in ['Degree', 'Period', 'Note']:
                v = kv(s, key)
                if v is not None:
                    cur[key.lower()] = v
    return schools


def parse_research(text):
    """
    格式:
      ## 实验室/单位名
      Period:  时间段
      Role:    角色（例如 Research Assistant）
      Advisor: 导师
      Topic:   研究方向
      - bullet 1
      - bullet 2
      - bullet 3
    """
    entries, cur = [], None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith('## '):
            cur = {'title': s[3:], 'period': '', 'role': '',
                   'advisor': '', 'topic': '', 'bullets': []}
            entries.append(cur)
        elif cur:
            matched = False
            for key in ['Period', 'Role', 'Advisor', 'Topic']:
                v = kv(s, key)
                if v is not None:
                    cur[key.lower()] = v
                    matched = True
                    break
            if not matched and s.startswith(('- ', '* ')):
                cur['bullets'].append(s[2:].strip())
    return entries


def parse_news(text):
    """
    格式（每行一条）:
      - [日期] 内容
    返回 [(date, content), ...]
    """
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith(('- ', '* ')):
            c = ln[2:]
            m = re.match(r'\[([^\]]+)\]\s*(.*)', c)
            out.append((m.group(1), m.group(2)) if m else ('', c))
    return out


def parse_publications(text):
    """
    格式:
      ## 年份
      ### 论文标题
      Authors: 作者
      Venue:   会议/期刊
      Status:  状态（可选，如 Accepted）
    返回 {year: [paper_dict, ...]}
    """
    groups, cur_year, cur_paper = {}, None, None
    for ln in text.splitlines():
        s = ln.strip()
        if not s: continue
        if re.match(r'^## \d{4}', s):
            cur_year = s[3:].strip()
            groups.setdefault(cur_year, [])
            cur_paper = None
        elif s.startswith('### ') and cur_year is not None:
            cur_paper = {'title': s[4:], 'authors': '', 'venue': '', 'status': ''}
            groups[cur_year].append(cur_paper)
        elif cur_paper is not None:
            for key in ['Authors', 'Venue', 'Status']:
                v = kv(s, key)
                if v is not None:
                    cur_paper[key.lower()] = v
    return groups


def parse_projects(text):
    """
    格式:
      ## 项目名
      Period:      时间
      Context:     背景/比赛
      Award:       获奖（可选）
      Description: 描述
    """
    projects, cur = [], None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith('## '):
            cur = {'title': s[3:], 'period': '', 'context': '',
                   'award': '', 'description': ''}
            projects.append(cur)
        elif cur:
            for key in ['Period', 'Context', 'Award', 'Description']:
                v = kv(s, key)
                if v is not None:
                    cur[key.lower()] = v
    return projects


def parse_awards(text):
    """
    格式（每行一条）:
      - 奖项名称 | 年份
    """
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith(('- ', '* ')):
            c = ln[2:].strip()
            parts = c.rsplit('|', 1)
            out.append((parts[0].strip(), parts[1].strip())
                       if len(parts) == 2 else (c, ''))
    return out


def parse_activities(text):
    """
    格式:
      ## 职务名
      Period:      时间
      Description: 职责描述
    """
    entries, cur = [], None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith('## '):
            cur = {'title': s[3:], 'period': '', 'description': ''}
            entries.append(cur)
        elif cur:
            for key in ['Period', 'Description']:
                v = kv(s, key)
                if v is not None:
                    cur[key.lower()] = v
    return entries


def parse_skills(text):
    """
    格式:
      ## 分类名
      技能1, 技能2, 技能3
    """
    groups, cur, items = [], None, []
    for ln in text.splitlines():
        s = ln.strip()
        if not s: continue
        if s.startswith('## '):
            if cur:
                groups.append((cur, ', '.join(items)))
            cur, items = s[3:], []
        elif cur:
            items.extend(x.strip() for x in re.split(r'[,，]', s) if x.strip())
    if cur:
        groups.append((cur, ', '.join(items)))
    return groups


def parse_contact(text):
    """
    格式:
      Email:    邮箱
      Phone:    电话
      Location: 地址
      Incoming: 即将入学信息
    """
    fields = {}
    for ln in text.splitlines():
        for key in ['Email', 'Phone', 'Location', 'Incoming']:
            v = kv(ln, key)
            if v is not None:
                fields[key] = v
    return fields


# ─── HTML 片段生成器 ───────────────────────────────────────────────────────────

def h_about(paras):
    return ''.join(f'                <p>{inline(p)}</p>\n' for p in paras)


def h_education(schools):
    out = ''
    for s in schools:
        note = f'<span class="badge">{esc(s["note"])}</span>' if s.get('note') else ''
        out += (
            f'            <div class="tl-item">\n'
            f'                <div class="tl-date">{esc(s.get("period",""))}</div>\n'
            f'                <div class="tl-title">{esc(s["school"])}</div>\n'
            f'                <div class="tl-sub">{esc(s.get("degree",""))}</div>\n'
            f'                {note}\n'
            f'            </div>\n'
        )
    return out


def h_research(entries):
    out = ''
    for e in entries:
        sub_parts = [x for x in [e.get('role', ''), e.get('advisor', '')] if x]
        sub_line = ''
        if sub_parts:
            sub = ' · '.join(esc(x) for x in sub_parts)
            sub_line = f'\n                <div class="tl-sub">{sub}</div>'

        topic_line = ''
        if e.get('topic'):
            topic_line = f'\n                <div class="research-topic">{inline(e["topic"])}</div>'

        bullets_html = ''
        if e.get('bullets'):
            items = ''.join(f'<li>{inline(b)}</li>' for b in e['bullets'])
            bullets_html = f'\n                <ul class="research-bullets">{items}</ul>'

        out += (
            f'            <div class="tl-item">\n'
            f'                <div class="tl-date">{esc(e.get("period",""))}</div>\n'
            f'                <div class="tl-title">{esc(e["title"])}</div>'
            f'{sub_line}'
            f'{topic_line}'
            f'{bullets_html}\n'
            f'            </div>\n'
        )
    return out


def h_news(items):
    lis = ''.join(
        (f'            <li><span class="news-tag">[{esc(d)}]</span> {inline(c)}</li>\n' if d
         else f'            <li>{inline(c)}</li>\n')
        for d, c in items
    )
    return f'        <ul class="news-list">\n{lis}        </ul>'


def h_publications(groups):
    out = ''
    for year in sorted(groups, reverse=True):
        entries = ''
        for p in groups[year]:
            status = (f'<div class="pub-meta">'
                      f'<span class="pub-badge accepted">{esc(p["status"])}</span>'
                      f'</div>') if p.get('status') else ''
            entries += (
                f'            <div class="pub-entry"><div class="pub-body">'
                f'<div class="pub-title">"{esc(p["title"])}"</div>'
                f'<div class="pub-authors">{inline(p["authors"])}</div>'
                f'<div class="pub-venue">{esc(p["venue"])}</div>'
                f'{status}</div></div>\n'
            )
        out += (f'        <div class="year-group">\n'
                f'            <div class="year-label">{esc(year)}</div>\n'
                f'{entries}        </div>\n')
    return out


def h_projects(projects):
    out = ''
    for p in projects:
        award = f'<div class="project-award">★ {esc(p["award"])}</div>' if p.get('award') else ''
        meta_parts = [x for x in [p.get('context', ''), p.get('period', '')] if x]
        meta = ' &nbsp;·&nbsp; '.join(esc(x) for x in meta_parts)
        out += (
            f'        <div class="project-entry">'
            f'<div class="project-title">{esc(p["title"])}</div>'
            f'<div class="project-meta">{meta}</div>'
            f'{award}'
            f'<div class="project-desc">{inline(p.get("description", ""))}</div>'
            f'</div>\n'
        )
    return out


def h_awards(items):
    lis = ''
    for i, (text, year) in enumerate(items):
        cls = 'award-text award-highlight' if i < 2 else 'award-text'
        lis += (f'            <li>'
                f'<span class="{cls}">{esc(text)}</span>'
                f'<span class="award-year">{esc(year)}</span>'
                f'</li>\n')
    return f'        <ul class="award-list">\n{lis}        </ul>'


def h_activities(entries):
    out = ''
    for e in entries:
        out += (
            f'        <div class="project-entry">'
            f'<div class="project-title">{esc(e["title"])}</div>'
            f'<div class="project-meta">{esc(e.get("period",""))}</div>'
            f'<div class="project-desc">{inline(e.get("description", ""))}</div>'
            f'</div>\n'
        )
    return out


def h_skills(groups):
    divs = ''.join(
        f'            <div>'
        f'<div class="skill-group-title">{esc(cat)}</div>'
        f'<div class="skill-group-body">{esc(items)}</div>'
        f'</div>\n'
        for cat, items in groups
    )
    return f'        <div class="skills-grid">\n{divs}        </div>'


def h_contact(fields):
    rows = ''
    order = [
        ('Email',    '✉',  True),   # email 是链接
        ('Phone',    '📞', False),
        ('Location', '📍', False),
        ('Incoming', '📍', False),
    ]
    for key, icon, is_email in order:
        if key in fields:
            v = fields[key]
            inner = (f'<a href="mailto:{esc(v)}">{esc(v)}</a>'
                     if is_email
                     else f'<span>{esc(v)}</span>')
            rows += (f'            <div class="contact-row">'
                     f'<span class="contact-icon">{icon}</span>'
                     f'{inner}'
                     f'</div>\n')
    return f'        <div class="contact-block">\n{rows}        </div>'


# ─── 主程序 ────────────────────────────────────────────────────────────────────

def build():
    md = read('content.md')
    template = read('template.html')
    sections = split_h1(md)

    def get(name, default=''):
        return sections.get(name, default)

    replacements = {
        '{{ABOUT}}':        h_about(parse_about(get('About'))),
        '{{EDUCATION}}':    h_education(parse_education(get('Education'))),
        '{{RESEARCH}}':     h_research(parse_research(get('Research Experience'))),
        '{{NEWS}}':         h_news(parse_news(get('News'))),
        '{{PUBLICATIONS}}': h_publications(parse_publications(get('Publications'))),
        '{{PROJECTS}}':     h_projects(parse_projects(get('Projects'))),
        '{{AWARDS}}':       h_awards(parse_awards(get('Awards'))),
        '{{ACTIVITIES}}':   h_activities(parse_activities(get('Student Activities'))),
        '{{SKILLS}}':       h_skills(parse_skills(get('Skills'))),
        '{{CONTACT}}':      h_contact(parse_contact(get('Contact'))),
    }

    output = template
    for placeholder, html in replacements.items():
        output = output.replace(placeholder, html)

    write('index.html', output)
    print('✓ index.html 已生成')


if __name__ == '__main__':
    build()
