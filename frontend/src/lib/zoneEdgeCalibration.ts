/** Edge calibration helpers for speed zones (metres between polygon vertices). */

export type PolygonPoint = {
  x: number;
  y: number;
  distance_to_next_m?: number;
};

const STAGE_W = 800;
const STAGE_H = 450;

export function vertexCountFromPoints(points: number[]): number {
  return Math.floor(points.length / 2);
}

export function edgePixelLength(points: number[], edgeIndex: number): number {
  const n = vertexCountFromPoints(points);
  if (n < 2) return 0;
  const i = edgeIndex % n;
  const j = (i + 1) % n;
  const x1 = points[i * 2] / STAGE_W;
  const y1 = points[i * 2 + 1] / STAGE_H;
  const x2 = points[j * 2] / STAGE_W;
  const y2 = points[j * 2 + 1] / STAGE_H;
  return Math.hypot(x2 - x1, y2 - y1);
}

export function pointsToPolygon(
  points: number[],
  edgeDistancesM?: (number | undefined)[],
): PolygonPoint[] {
  const n = vertexCountFromPoints(points);
  const out: PolygonPoint[] = [];
  for (let i = 0; i < n; i++) {
    const pt: PolygonPoint = {
      x: points[i * 2] / STAGE_W,
      y: points[i * 2 + 1] / STAGE_H,
    };
    const d = edgeDistancesM?.[i];
    if (d != null && d > 0) pt.distance_to_next_m = d;
    out.push(pt);
  }
  return out;
}

export function polygonToPointsAndEdges(polygon: PolygonPoint[]): {
  points: number[];
  edgeDistancesM: (number | undefined)[];
} {
  const points: number[] = [];
  const edgeDistancesM: (number | undefined)[] = [];
  for (const p of polygon) {
    points.push(p.x * STAGE_W, p.y * STAGE_H);
    edgeDistancesM.push(
      p.distance_to_next_m != null && p.distance_to_next_m > 0
        ? p.distance_to_next_m
        : undefined,
    );
  }
  return { points, edgeDistancesM };
}

export function polygonFromBackend(raw: { x: number; y: number; distance_to_next_m?: number }[]): PolygonPoint[] {
  return (raw ?? []).map((p) => ({
    x: p.x,
    y: p.y,
    distance_to_next_m:
      p.distance_to_next_m != null && p.distance_to_next_m > 0 ? p.distance_to_next_m : undefined,
  }));
}

export function calibratedEdgeCount(edgeDistancesM: (number | undefined)[] | undefined): number {
  return (edgeDistancesM ?? []).filter((d) => d != null && d > 0).length;
}

export function derivedTravelDistanceM(
  points: number[],
  edgeDistancesM: (number | undefined)[] | undefined,
): number | null {
  const n = vertexCountFromPoints(points);
  if (n === 0) return null;
  let max = 0;
  let any = false;
  for (let i = 0; i < n; i++) {
    const d = edgeDistancesM?.[i];
    if (d != null && d > 0) {
      any = true;
      if (d > max) max = d;
    }
  }
  return any ? max : null;
}

export function perimeterM(edgeDistancesM: (number | undefined)[] | undefined): number | null {
  const vals = (edgeDistancesM ?? []).filter((d): d is number => d != null && d > 0);
  if (vals.length === 0) return null;
  const n = edgeDistancesM?.length ?? 0;
  if (vals.length !== n) return null;
  return vals.reduce((a, b) => a + b, 0);
}

export function midEdgeStageCoords(
  points: number[],
  edgeIndex: number,
): { x: number; y: number } {
  const n = vertexCountFromPoints(points);
  const i = edgeIndex % n;
  const j = (i + 1) % n;
  return {
    x: (points[i * 2] + points[j * 2]) / 2,
    y: (points[i * 2 + 1] + points[j * 2 + 1]) / 2,
  };
}

export function edgeStagePoints(points: number[], edgeIndex: number): number[] {
  const n = vertexCountFromPoints(points);
  const i = edgeIndex % n;
  const j = (i + 1) % n;
  return [
    points[i * 2],
    points[i * 2 + 1],
    points[j * 2],
    points[j * 2 + 1],
  ];
}

export function edgeVertexIndices(edgeIndex: number, vertexCount: number): [number, number] {
  const i = edgeIndex % vertexCount;
  return [i, (i + 1) % vertexCount];
}
