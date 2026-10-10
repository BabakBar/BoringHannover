export const NODE_W = 190;
export const NODE_H = 70;

export type Side = 't' | 'r' | 'b' | 'l';
export interface Point { x: number; y: number }

export function anchor(node: Point, side: Side, at = 0.5): Point {
  switch (side) {
    case 'l': return { x: node.x, y: node.y + NODE_H * at };
    case 'r': return { x: node.x + NODE_W, y: node.y + NODE_H * at };
    case 't': return { x: node.x + NODE_W * at, y: node.y };
    case 'b': return { x: node.x + NODE_W * at, y: node.y + NODE_H };
  }
}

interface Route {
  from: Point;
  to: Point;
  fromSide: Side;
  toSide: Side;
  fromAt?: number;
  toAt?: number;
  via?: [number, number][];
}

export function routePoints(route: Route): Point[] {
  const waypoints = (route.via ?? []).map(([x, y]) => ({ x, y }));
  return [
    anchor(route.from, route.fromSide, route.fromAt),
    ...waypoints,
    anchor(route.to, route.toSide, route.toAt),
  ];
}

const length = (a: Point, b: Point) => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);

function towards(from: Point, to: Point, distance: number): Point {
  const total = length(from, to);
  const ratio = total === 0 ? 0 : distance / total;
  return { x: from.x + (to.x - from.x) * ratio, y: from.y + (to.y - from.y) * ratio };
}

/** Polyline path whose corners are rounded with a quadratic curve. */
export function toPath(points: Point[], radius: number): string {
  const parts = [`M${points[0].x},${points[0].y}`];
  for (let index = 1; index < points.length; index++) {
    const previous = points[index - 1];
    const current = points[index];
    const next = points[index + 1];
    if (!next) {
      parts.push(`L${current.x},${current.y}`);
      continue;
    }
    const inset = Math.min(radius, length(previous, current) / 2, length(current, next) / 2);
    const entry = towards(current, previous, inset);
    const exit = towards(current, next, inset);
    parts.push(`L${entry.x},${entry.y}`, `Q${current.x},${current.y} ${exit.x},${exit.y}`);
  }
  return parts.join(' ');
}

export function labelPoint(points: Point[]): Point {
  let best: [Point, Point] = [points[0], points[1]];
  for (let index = 1; index < points.length - 1; index++) {
    if (length(points[index], points[index + 1]) > length(...best)) {
      best = [points[index], points[index + 1]];
    }
  }
  return { x: (best[0].x + best[1].x) / 2, y: (best[0].y + best[1].y) / 2 };
}

export const SHEET_COLUMNS = 6;
export const SHEET_ROWS = 4;

/** Drawing-style grid reference of a node's centre, e.g. "B2". */
export function sheetRef(node: Point, canvas: { width: number; height: number }): string {
  const column = Math.min(SHEET_COLUMNS, Math.floor(((node.x + NODE_W / 2) / canvas.width) * SHEET_COLUMNS) + 1);
  const row = Math.min(SHEET_ROWS, Math.floor(((node.y + NODE_H / 2) / canvas.height) * SHEET_ROWS));
  return `${'ABCD'[row]}${column}`;
}
