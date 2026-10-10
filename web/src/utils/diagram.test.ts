import { describe, expect, test } from 'bun:test';
import { NODE_H, NODE_W, anchor, labelPoint, routePoints, sheetRef, toPath } from './diagram';

const node = { x: 100, y: 200 };

describe('anchor', () => {
  test('sits on the middle of each side by default', () => {
    expect(anchor(node, 'l')).toEqual({ x: 100, y: 200 + NODE_H / 2 });
    expect(anchor(node, 'r')).toEqual({ x: 100 + NODE_W, y: 200 + NODE_H / 2 });
    expect(anchor(node, 't')).toEqual({ x: 100 + NODE_W / 2, y: 200 });
    expect(anchor(node, 'b')).toEqual({ x: 100 + NODE_W / 2, y: 200 + NODE_H });
  });

  test('moves along the side with the `at` fraction', () => {
    expect(anchor(node, 't', 0.2).x).toBeCloseTo(100 + NODE_W * 0.2);
    expect(anchor(node, 'l', 0.25).y).toBeCloseTo(200 + NODE_H * 0.25);
  });
});

describe('routePoints', () => {
  const from = { x: 0, y: 0 };
  const to = { x: 400, y: 0 };

  test('joins two aligned sides with a straight line', () => {
    const points = routePoints({ from, to, fromSide: 'r', toSide: 'l' });
    expect(points).toEqual([anchor(from, 'r'), anchor(to, 'l')]);
  });

  test('passes through waypoints in order', () => {
    const points = routePoints({
      from,
      to,
      fromSide: 'b',
      toSide: 'b',
      via: [[95, 140], [495, 140]],
    });
    expect(points).toHaveLength(4);
    expect(points[1]).toEqual({ x: 95, y: 140 });
    expect(points[2]).toEqual({ x: 495, y: 140 });
  });
});

describe('toPath', () => {
  test('draws straight segments with M and L', () => {
    expect(toPath([{ x: 0, y: 0 }, { x: 50, y: 0 }], 8)).toBe('M0,0 L50,0');
  });

  test('rounds a corner by stopping short of it and curving through it', () => {
    const path = toPath(
      [{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 50, y: 50 }],
      8,
    );
    expect(path).toBe('M0,0 L42,0 Q50,0 50,8 L50,50');
  });

  test('never rounds more than half of a short segment', () => {
    const path = toPath(
      [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }],
      8,
    );
    expect(path).toBe('M0,0 L5,0 Q10,0 10,5 L10,10');
  });
});

describe('labelPoint', () => {
  test('is the midpoint of the longest segment', () => {
    const point = labelPoint([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 100 },
    ]);
    expect(point).toEqual({ x: 10, y: 50 });
  });
});

describe('sheetRef', () => {
  const canvas = { width: 1200, height: 700 };

  test('names the cell a node centre falls in: letter for row, number for column', () => {
    expect(sheetRef({ x: 40, y: 60 }, canvas)).toBe('A1');
    expect(sheetRef({ x: 270, y: 240 }, canvas)).toBe('B2');
    expect(sheetRef({ x: 500, y: 420 }, canvas)).toBe('C3');
    expect(sheetRef({ x: 960, y: 590 }, canvas)).toBe('D6');
  });
});
