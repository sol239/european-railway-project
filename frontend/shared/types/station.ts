export interface Station {
  key: number
  name: string
  latitude: number
  longitude: number
  visits: number
}

export interface StationResponse {
  stations: Station[]
  coverage: { firstDate: string | null; lastDate: string | null }
  selectedDate: string | null
  updatedAt: string
}
