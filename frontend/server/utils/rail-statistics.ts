import type { RailwayFeature } from '../../shared/types/railway'
import { distance } from '../../shared/utils/train-position'

/** Sum operating RFN geometry lengths; overlapping features are counted separately. */
export function operatingRailLength(features: RailwayFeature[]): number {
  let total = 0
  for (const feature of features) {
    if (feature.properties.mnemo !== 'EXPLOITE') continue
    const lines = feature.geometry.type === 'LineString' ? [feature.geometry.coordinates] : feature.geometry.coordinates
    for (const line of lines) {
      for (let i = 1; i < line.length; i++) {
        const a = line[i - 1]!, b = line[i]!
        total += distance([a[0]!, a[1]!], [b[0]!, b[1]!])
      }
    }
  }
  return total
}
