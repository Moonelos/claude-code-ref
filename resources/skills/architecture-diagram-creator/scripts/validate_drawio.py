#!/usr/bin/env python3
"""Validate the skill's explicit-polyline contract; never guess draw.io auto-routes."""
import argparse
import base64
import html
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from itertools import combinations
from pathlib import Path


def style(cell):
    return dict(part.split('=', 1) for part in cell.get('style', '').split(';') if '=' in part)


def number(value):
    n = float(value)
    if not math.isfinite(n):
        raise ValueError('non-finite coordinate')
    return n


def overlap(a, b, gap=0):
    return (a[0] < b[0]+b[2]+gap and b[0] < a[0]+a[2]+gap
            and a[1] < b[1]+b[3]+gap and b[1] < a[1]+a[3]+gap)


def inside(a, b):
    return b[0] <= a[0] and b[1] <= a[1] and a[0]+a[2] <= b[0]+b[2] and a[1]+a[3] <= b[1]+b[3]


def hits(p, q, box, gap=0):
    x, y, w, h = box
    x, y, w, h = x-gap, y-gap, w+2*gap, h+2*gap
    if p[1] == q[1]:
        return y < p[1] < y+h and max(min(p[0], q[0]), x) < min(max(p[0], q[0]), x+w)
    return x < p[0] < x+w and max(min(p[1], q[1]), y) < min(max(p[1], q[1]), y+h)


def follows_boundary(p, q, box, gap=10):
    """Detect a route lane drawn along a boundary edge, not a perpendicular crossing."""
    x, y, w, h = box
    if p[1] == q[1]:
        shared = min(max(p[0], q[0]), x+w) - max(min(p[0], q[0]), x)
        return shared >= 20 and min(abs(p[1]-y), abs(p[1]-(y+h))) < gap
    shared = min(max(p[1], q[1]), y+h) - max(min(p[1], q[1]), y)
    return shared >= 20 and min(abs(p[0]-x), abs(p[0]-(x+w))) < gap


def validate(path, min_gap=20):
    issues = []

    def report(code, cell, detail, severity='error'):
        issues.append(dict(severity=severity, code=code, cell=cell, detail=detail))

    try:
        raw = Path(path).read_bytes()
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('DTD/entities are not supported')
        doc = ET.fromstring(raw)
        if doc.tag != 'mxfile' or not doc.findall('diagram'):
            raise ValueError('expected mxfile with diagram pages')
    except (OSError, ValueError, ET.ParseError) as exc:
        report('XML', '-', str(exc))
        return issues

    for page in doc.findall('diagram'):
        name = page.get('name', 'page')
        model = page.find('mxGraphModel')
        if model is None or model.find('root') is None:
            report('STRUCTURE', name, 'Uncompressed mxGraphModel/root required')
            continue
        cells = list(model.find('root'))
        if any(c.tag != 'mxCell' for c in cells):
            report('UNSUPPORTED', name, 'Flatten object wrappers to mxCell before checking')
            continue
        ids = [c.get('id') for c in cells]
        if None in ids or len(set(ids)) != len(ids):
            report('IDS', name, 'Missing or duplicate cell IDs')
            continue
        by_id = dict(zip(ids, cells))
        if '0' not in by_id or '1' not in by_id or by_id['1'].get('parent') != '0':
            report('ROOTS', name, 'Root cells 0 and 1 required; 1 must parent to 0')
        styles = {i: style(c) for i, c in by_id.items()}
        roles = {i: s.get('archRole') for i, s in styles.items()}
        if model.get('archProvider') == 'neutral':
            for i, s in styles.items():
                if any('mxgraph.aws4.' in v for v in s.values()):
                    report('NEUTRAL_PROVIDER', i, 'AWS glyph in a provider-neutral view')
        boxes = {}
        for i, c in by_id.items():
            if i == '0':
                continue
            if c.get('parent') not in by_id:
                report('PARENT', i, 'Missing parent')
            if c.get('vertex') != '1':
                if c.get('edge') != '1' and i != '1':
                    report('UNSUPPORTED', i, 'Expected vertex or edge')
                continue
            role = roles[i]
            image_uri = styles[i].get('image')
            if image_uri:
                if not image_uri.startswith('data:image/svg+xml,'):
                    report('IMAGE_PORTABILITY', i, 'Use the embedded SVG format from icon_assets.py')
                else:
                    try:
                        svg = base64.b64decode(image_uri.split(',', 1)[1], validate=True)
                        if b'<!DOCTYPE' in svg.upper() or b'<!ENTITY' in svg.upper():
                            raise ValueError('DTD/entities in image')
                        if ET.fromstring(svg).tag.rsplit('}', 1)[-1] != 'svg':
                            raise ValueError('Embedded image is not SVG')
                    except (ValueError, ET.ParseError) as exc:
                        report('IMAGE_PORTABILITY', i, str(exc))
            if role not in {'card', 'icon', 'label', 'boundary', 'title', 'badge', 'legend', 'legend-badge', 'legend-step'}:
                report('ROLE', i, 'Missing/unknown archRole; layout is unverified')
            parent = c.get('parent')
            if parent != '1' and not (role in {'icon', 'label'} and roles.get(parent) == 'card'):
                report('NESTING', i, 'Only icon/label children of root-level cards supported')
            g = c.find('mxGeometry')
            try:
                if g is None or g.get('relative') == '1':
                    raise ValueError('Explicit vertex geometry required')
                box = tuple(number(g.get(k, '0')) for k in ('x', 'y', 'width', 'height'))
                if box[2] <= 0 or box[3] <= 0:
                    raise ValueError('Non-positive dimensions')
                boxes[i] = box
            except (ValueError, TypeError) as exc:
                report('GEOMETRY', i, str(exc))
            if role in {'icon', 'label'} and parent != '1' and c.get('connectable') != '0':
                report('CONNECTABLE', i, 'Internal card children must be non-connectable')
            if role == 'card':
                s = styles[i]
                if (s.get('rounded', '0') != '0' or s.get('perimeter') != 'rectanglePerimeter'
                        or s.get('shape', 'rectangle') != 'rectangle'
                        or s.get('strokeColor', 'none') == 'none'):
                    report('CARD', i, 'Visible rectangular perimeter required')
            text = html.unescape(re.sub('<[^>]*>', ' ', c.get('value', '')))
            if re.search(r'FOR UPDATE|SKIP LOCKED|state\s*=|INSERT INTO', text, re.I) or len(text) > 220:
                report('LABEL_DENSITY', i, 'Review implementation detail or long text', 'warning')

        # Resolve the sole supported nesting level (children inside cards).
        for i in list(boxes):
            parent = by_id[i].get('parent')
            if roles.get(parent) == 'card' and parent in boxes:
                x, y, w, h = boxes[i]
                p = boxes[parent]
                boxes[i] = (x+p[0], y+p[1], w, h)
                if not inside(boxes[i], p):
                    report('CHILD_BOUNDS', i, 'Icon/label extends outside its card')
        cards = {i: b for i, b in boxes.items() if roles[i] == 'card'}
        if not cards:
            report('CARDS', name, 'No architecture cards')
        obstacles = {i: b for i, b in boxes.items() if roles[i] in {'card', 'badge', 'title', 'legend-badge', 'legend-step'}
                     or roles[i] in {'label', 'icon'} and by_id[i].get('parent') == '1'}
        # Boundary bodies may be crossed; their headings may not. Reserve a
        # conservative text band, not an exact browser font metric.
        for i, b in boxes.items():
            if roles[i] != 'boundary' or not by_id[i].get('value', '').strip():
                continue
            s = styles[i]
            try:
                if s.get('verticalAlign', 'middle') != 'top' or number(s.get('rotation', '0')) != 0:
                    raise ValueError('Use a separate root-level label for non-top or rotated headings')
                font = number(s.get('fontSize', '14'))
                pad = number(s.get('spacing', '0'))
                top = pad + number(s.get('spacingTop', '0'))
                left = pad + number(s.get('spacingLeft', '0'))
                right = pad + number(s.get('spacingRight', '0'))
                width = b[2] - left - right
                if font <= 0 or width <= 0 or min(top, left, right) < 0:
                    raise ValueError('Invalid heading font/spacing')
                text = re.sub(r'<br\s*/?>|</(?:div|p)>', '\n', by_id[i].get('value', ''), flags=re.I)
                text = html.unescape(re.sub('<[^>]*>', '', text))
                lines = sum(max(1, math.ceil(len(line)*font*0.65/width)) for line in text.splitlines())
                height = max(lines*font*1.4, number(s.get('archHeaderHeight', '0')))
                if s.get('align') == 'left':
                    width = min(width, max((len(line)*font*0.65 for line in text.splitlines()), default=width))
                band = (b[0]+left, b[1]+top, width, height)
                if not inside(band, b):
                    raise ValueError('Heading does not fit boundary')
                obstacles[i+'::heading'] = band
            except (ValueError, TypeError) as exc:
                report('BOUNDARY_HEADING', i, str(exc))
        for (i, a), (j, b) in combinations(obstacles.items(), 2):
            if overlap(a, b):
                report('OVERLAP', i, f'Overlaps {j}')

        routes = {}
        for i, c in by_id.items():
            if c.get('edge') != '1':
                continue
            s = styles[i]
            source, target = c.get('source'), c.get('target')
            if source not in cards or target not in cards:
                report('TERMINAL', i, 'Both source and target must reference outer cards')
                continue
            if c.get('parent') != '1':
                report('EDGE_PARENT', i, 'Edge coordinates must be root-level')
                continue
            if s.get('edgeStyle') != 'none' or s.get('noEdgeStyle') != '1' or s.get('curved', '0') != '0' or s.get('rounded', '0') != '0':
                report('UNVERIFIED_ROUTE', i, 'Use explicit straight-segment polylines; auto-route cannot be checked')
                continue
            endpoints, normals = [], []
            try:
                for prefix, terminal in [('exit', source), ('entry', target)]:
                    u, v = number(s[prefix+'X']), number(s[prefix+'Y'])
                    if not ((u in (0, 1) and 0 < v < 1) or (v in (0, 1) and 0 < u < 1)):
                        raise ValueError('Anchor must lie on a face, away from corners')
                    if any(number(s.get(prefix+k, '0')) != 0 for k in ('Dx', 'Dy')) or s.get(prefix+'Perimeter') != '1':
                        raise ValueError('Use zero offsets and perimeter=1')
                    x, y, w, h = cards[terminal]
                    endpoints.append((x+u*w, y+v*h))
                    normals.append((-1, 0) if u == 0 else (1, 0) if u == 1 else (0, -1) if v == 0 else (0, 1))
                g = c.find('mxGeometry')
                if g is None or g.get('relative') != '1':
                    raise ValueError('Relative edge geometry required')
                if g.findall('mxPoint'):
                    raise ValueError('Floating terminal points/offsets unsupported')
                pts = [(number(p.attrib['x']), number(p.attrib['y'])) for p in g.findall("Array[@as='points']/mxPoint")]
                points = [endpoints[0], *pts, endpoints[1]]
            except (KeyError, ValueError, TypeError) as exc:
                report('ANCHOR', i, str(exc))
                continue
            segments = list(zip(points, points[1:]))
            if any(p == q or (p[0] != q[0] and p[1] != q[1]) for p, q in segments):
                report('ORTHOGONAL', i, 'All segments must have positive length and be axis-aligned')
                continue
            for p, q, n in [(points[0], points[1], normals[0]), (points[-1], points[-2], normals[1])]:
                delta = (q[0]-p[0], q[1]-p[1])
                if delta[0]*n[0]+delta[1]*n[1] < 20 or delta[0]*n[1]-delta[1]*n[0] != 0:
                    report('OUTWARD_STUB', i, 'Endpoint segment must extend outward perpendicular to face for >=20 px')
            for j, b in cards.items():
                clearance = 0 if j in (source, target) else 10
                if any(hits(p, q, b, clearance) for p, q in segments):
                    report('CARD_ROUTE', i, f'Enters card or its clearance area: {j}')
            for j, b in obstacles.items():
                if j not in cards and any(hits(p, q, b, 10) for p, q in segments):
                    report('ANNOTATION_ROUTE', i, f'Route too close to annotation: {j}')
            for j, b in boxes.items():
                if roles[j] == 'boundary' and any(follows_boundary(p, q, b) for p, q in segments):
                    report('BOUNDARY_ROUTE', i, f'Route runs within 10 px of boundary edge: {j}')
            routes[i] = segments

        for (i, segs), (j, other) in combinations(routes.items(), 2):
            close, cross = False, False
            for p, q in segs:
                for r, t in other:
                    horiz, horiz2 = p[1] == q[1], r[1] == t[1]
                    if horiz == horiz2:
                        axis = 0 if horiz else 1
                        common = min(max(p[axis], q[axis]), max(r[axis], t[axis])) - max(min(p[axis], q[axis]), min(r[axis], t[axis]))
                        if common > 0 and abs(p[1-axis]-r[1-axis]) < min_gap:
                            close = True
                    else:
                        a, b, c, d = (p, q, r, t) if horiz else (r, t, p, q)
                        if min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1]):
                            cross = True
            if close:
                report('LINE_GAP', i, f'Parallel/shared lane closer than {min_gap:g}px to {j}')
            if cross:
                report('CROSSING', i, f'Perpendicular crossing with {j}; inspect readability', 'warning')

        # A step may cover several branches; proximity to any one is sufficient.
        for i, (x, y, w, h) in boxes.items():
            step = styles[i].get('archStep')
            if roles[i] != 'badge' or not step:
                continue
            cx, cy = x+w/2, y+h/2
            distances = {
                edge: min(math.hypot(
                    cx-max(min(p[0], q[0]), min(cx, max(p[0], q[0]))),
                    cy-max(min(p[1], q[1]), min(cy, max(p[1], q[1]))))
                    for p, q in segments)
                for edge, segments in routes.items()
            }
            own = [d for edge, d in distances.items() if styles[edge].get('archStep') == step]
            other = [(d, edge) for edge, d in distances.items() if styles[edge].get('archStep') != step]
            if own and other:
                distance, edge = min(other)
                if distance <= min(own)+1e-6:
                    report('BADGE_ASSOCIATION', i,
                           f'Unrelated route {edge} is as close or closer than its own step; reposition badge',
                           'warning')

        legend_mode = model.get('archLegend')
        if legend_mode not in {'0', '1'}:
            report('LEGEND_MODE', name, 'Set archLegend=1 (default) or explicit opt-out 0')
        groups = {}
        for role in ('badge', 'legend-badge', 'legend-step', 'edge'):
            group = [styles[i].get('archStep') for i in by_id if roles[i] == role or role == 'edge' and by_id[i].get('edge') == '1' and styles[i].get('archStep')]
            groups[role] = Counter(group)
        if legend_mode == '1':
            badges, sidebar_badges, rows, edges = (groups[k] for k in ('badge', 'legend-badge', 'legend-step', 'edge'))
            valid_steps = all(v is not None and re.fullmatch(r'[1-9][0-9]*', v) for v in set(badges) | set(sidebar_badges) | set(rows) | set(edges))
            if not valid_steps or not badges or set(badges) != set(sidebar_badges) or set(badges) != set(rows) or set(badges) != set(edges) or any(n != 1 for n in [*badges.values(), *sidebar_badges.values(), *rows.values()]):
                report('STEPS', name, 'Need matching unique canvas/sidebar badges and descriptions, with edges per positive step')
            elif sorted(map(int, badges)) != list(range(1, len(badges)+1)):
                report('STEPS', name, 'Step numbering must be contiguous from 1')
            panels = [b for i, b in boxes.items() if roles[i] == 'legend']
            if len(panels) != 1:
                report('LEGEND', name, 'Exactly one sidebar panel required')
            else:
                panel = panels[0]
                right = max((b[0]+b[2] for i, b in boxes.items() if roles[i] in {'card', 'boundary', 'badge'}), default=0)
                right = max(right, max((p[0] for segments in routes.values() for seg in segments for p in seg), default=0))
                if panel[0] < right+40:
                    report('LEGEND_POSITION', name, 'Sidebar must be >=40px right of architecture and routes')
                for i, b in boxes.items():
                    if roles[i] in {'legend-badge', 'legend-step'} and not inside(b, panel):
                        report('LEGEND_BOUNDS', i, 'Legend row outside panel')
                for i in by_id:
                    if roles[i] in {'badge', 'legend-badge'}:
                        if by_id[i].get('value') != styles[i].get('archStep'):
                            report('BADGE_NUMBER', i, 'Visible badge must match archStep')
                        expected = {'fillColor': '#007CBD', 'strokeColor': '#000000', 'strokeWidth': '2',
                                    'fontColor': '#FFFFFF', 'rounded': '1', 'shadow': '1', 'fontStyle': '1'}
                        if any(styles[i].get(k, '').upper() != v.upper() for k, v in expected.items()):
                            report('BADGE_STYLE', i, 'Use the shared blue badge with black outline, white bold number and shadow')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--min-gap', type=float, default=20)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.min_gap) or args.min_gap <= 0:
        parser.error('--min-gap must be positive and finite')
    results = {str(p): validate(p, args.min_gap) for p in args.files}
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for path, issues in results.items():
            errors = sum(i['severity'] == 'error' for i in issues)
            print(f'{path}: {errors} errors, {len(issues)-errors} warnings; visual review separate')
            for item in issues:
                print(f"  {item['severity']} {item['code']} [{item['cell']}]: {item['detail']}")
    return int(any(i['severity'] == 'error' for items in results.values() for i in items))


if __name__ == '__main__':
    sys.exit(main())
