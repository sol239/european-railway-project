export type RailwayGeometry = {
  type: 'LineString'
  coordinates: number[][]
} | {
  type: 'MultiLineString'
  coordinates: number[][][]
}

export interface RailwayFeature {
  type: 'Feature'
  id: string
  geometry: RailwayGeometry
  properties: {
    code_ligne: string
    mnemo: string
    libelle: string
    rg_troncon: number
    pk_debut_r: string
    pk_fin_r: string
  }
}

export interface RailwayResponse {
  type: 'FeatureCollection'
  features: RailwayFeature[]
  metadata: {
    dataset: string
    runId: string
    uploadedAt: string
    segments: number
    operatingSegments: number
    sha256: string
  }
}
