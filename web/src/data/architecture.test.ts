import { describe, expect, test } from 'bun:test';
import { NODE_H, NODE_W, routePoints } from '../utils/diagram';
import { VIEWBOX, edges, flows, nodes } from './architecture';

const byId = new Map(nodes.map(node => [node.id, node]));

describe('nodes', () => {
  test('ids are unique and hosts are known', () => {
    expect(byId.size).toBe(nodes.length);
    for (const node of nodes) {
      expect(['outside', 'github', 'vps']).toContain(node.host);
    }
  });

  test('sit inside the canvas and never overlap', () => {
    for (const node of nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0);
      expect(node.y).toBeGreaterThanOrEqual(0);
      expect(node.x + NODE_W).toBeLessThanOrEqual(VIEWBOX.width);
      expect(node.y + NODE_H).toBeLessThanOrEqual(VIEWBOX.height);
    }
    for (const a of nodes) {
      for (const b of nodes) {
        if (a.id >= b.id) continue;
        const apart =
          a.x + NODE_W <= b.x || b.x + NODE_W <= a.x ||
          a.y + NODE_H <= b.y || b.y + NODE_H <= a.y;
        expect(apart).toBe(true);
      }
    }
  });
});

describe('edges', () => {
  test('ids are unique and endpoints exist', () => {
    expect(new Set(edges.map(edge => edge.id)).size).toBe(edges.length);
    for (const edge of edges) {
      expect(byId.has(edge.from)).toBe(true);
      expect(byId.has(edge.to)).toBe(true);
    }
  });

  test('every route is made of horizontal and vertical segments only', () => {
    for (const edge of edges) {
      const points = routePoints({
        ...edge,
        from: byId.get(edge.from)!,
        to: byId.get(edge.to)!,
      });
      points.slice(1).forEach((point, index) => {
        const previous = points[index];
        expect(point.x === previous.x || point.y === previous.y).toBe(true);
      });
    }
  });
});

describe('flows', () => {
  test('each flow has contiguous steps 1..n, one edge per step', () => {
    for (const flow of flows) {
      const steps = edges
        .filter(edge => edge.flow === flow.id)
        .map(edge => edge.step)
        .sort((a, b) => a - b);
      expect(steps.length).toBeGreaterThan(1);
      expect(steps).toEqual(steps.map((_, index) => index + 1));
    }
  });

  test('every edge belongs to a declared flow', () => {
    const ids = new Set(flows.map(flow => flow.id));
    for (const edge of edges) expect(ids.has(edge.flow)).toBe(true);
  });
});

describe('inspector', () => {
  test('every node says what it does and why it is built that way', () => {
    for (const node of nodes) {
      expect(node.role.length).toBeGreaterThan(20);
      expect(node.why.length).toBeGreaterThan(20);
    }
  });
});

describe('ids', () => {
  test('node and edge ids never collide, so they can share a URL hash', () => {
    const ids = [...nodes.map(node => node.id), ...edges.map(edge => edge.id)];
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe('replay', () => {
  test('every edge carries a payload label and at least one log line from a known node', () => {
    for (const edge of edges) {
      expect(edge.payload.length).toBeGreaterThan(0);
      expect(edge.log.length).toBeGreaterThan(0);
      for (const line of edge.log) {
        expect(byId.has(line.node)).toBe(true);
        expect(line.text.length).toBeGreaterThan(0);
      }
    }
  });

  test('node tags are short and unique', () => {
    const tags = nodes.map(node => node.tag);
    expect(new Set(tags).size).toBe(tags.length);
    for (const tag of tags) expect(tag.length).toBeLessThanOrEqual(10);
  });
});

describe('hygiene', () => {
  test('nothing identifying the deployment leaks into the public data', () => {
    const text = JSON.stringify({ nodes, edges, flows });
    expect(text).not.toMatch(/\b\d{1,3}(\.\d{1,3}){3}\b/);
    expect(text).not.toMatch(/\b[a-z0-9]{24}\b/);
    expect(text).not.toMatch(/bucket/i);
  });

  test('the public copy does not state refresh times', () => {
    const text = JSON.stringify({ nodes, edges, flows });
    expect(text).not.toMatch(/\b\d{1,2}:\d{2}\b|cron|times a week|\b(Mon|Tue|Fri|Sun)\b/);
  });
});
