export interface StationTimetableEntry {
  id: string
  time: number
  station: string
}

export interface StationTimetable {
  station: number
  date: string
  arrivals: StationTimetableEntry[]
  departures: StationTimetableEntry[]
}
