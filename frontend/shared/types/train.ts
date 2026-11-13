export interface TrainStop { station: number; name: string; longitude: number; latitude: number; arrival: number; departure: number }
export interface ScheduledTrain { id: string; name: string; stops: TrainStop[] }
export interface TrainSchedule { date: string; trains: ScheduledTrain[] }
export interface TimelineInstant { date: string; seconds: number; live: boolean }

export interface TrainDetails {
  id: string; name: string; date: string; seconds: number
  stops: TrainStop[]; from: TrainStop; to: TrainStop
  progress: number; longitude: number; latitude: number
  distanceMeters: number | null; travelledMeters: number | null; segmentMeters: number
}
