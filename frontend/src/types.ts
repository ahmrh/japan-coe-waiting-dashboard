export type HierarchyType = 'national_total' | 'bureau_jurisdiction' | 'office'

export interface WorkloadObservation {
  period: string
  bureau_code: string
  bureau_name: string
  hierarchy_type: HierarchyType
  parent_code: string | null
  sequence_number: number
  accepted_total: number | null
  old_receipts: number | null
  new_receipts: number | null
  completed_total: number | null
  issued: number | null
  not_issued: number | null
  completed_other: number | null
  pending_official: number | null
  pending_calculated: number | null
  pending_value: number | null
  pending_label: string | null
  pending_change?: number | null
  throughput_ratio: number | null
  unit: string
  raw_values: Record<string, number | null>
}

export interface SourceFreshness {
  id: string
  name: string
  owner: string
  url: string
  source_type: string
  update_policy: string
  measure: string
  unit: string
  frequency: string
  last_checked: string | null
  last_successful_fetch: string | null
  latest_publication_date: string | null
  latest_period: string | null
  status: string
  error_summary: string | null
  limitations: string[]
}

export interface Overview {
  title: string
  latest_period: string | null
  previous_period: string | null
  available_periods: string[]
  field_labels: Record<string, string>
  source: SourceFreshness
  rows: WorkloadObservation[]
  observations: WorkloadObservation[]
  summary: string
  refresh_queued: boolean
}
