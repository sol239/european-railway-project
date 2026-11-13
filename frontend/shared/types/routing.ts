import type { RailwayFeature } from './railway'
import type { Point } from '../utils/train-position'

export interface RailTrack { path: Point[]; cumulative: number[]; length: number }
export interface RoutePair { key: string; from: Point; to: Point }
export type RoutingRequest = { id: number; type: 'init'; features: RailwayFeature[] }
  | { id: number; type: 'routes'; pairs: RoutePair[] }
export interface RoutingResponse { id: number; tracks?: { key: string; track: RailTrack | null }[]; error?: string }
