export interface ScheduleStatistics {
  stations: number
  mappedStations: number
  trips: number
  routes: number
  stopVisits: number
  coverage: { firstDate: string | null; lastDate: string | null }
  busiestStations: { key: number; name: string; visits: number }[]
}

export interface RailStatistics {
  operatingLengthMeters: number
  operatingSegments: number
  uploadedAt: string
}
