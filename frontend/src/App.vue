<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import ChartPanel from './components/ChartPanel.vue'
import { getOverview, startRefresh } from './services/api'
import type { Overview, WorkloadObservation } from './types'

type View = 'workload' | 'sources' | 'processing'
type HeatMetric = 'pending_value' | 'new_receipts' | 'completed_total' | 'throughput_ratio'
type SortKey = 'bureau_name' | 'old_receipts' | 'new_receipts' | 'accepted_total' |
  'issued' | 'not_issued' | 'completed_other' | 'completed_total' | 'pending_value' |
  'pending_change' | 'throughput_ratio'

const data = ref<Overview | null>(null)
const loading = ref(true)
const loadError = ref('')
const refreshMessage = ref('')
const refreshBusy = ref(false)
const dark = ref(false)
const view = ref<View>('workload')
const period = ref('')
const selectedBureau = ref('100000')
const hierarchy = ref<'jurisdictions' | 'offices'>('jurisdictions')
const heatMetric = ref<HeatMetric>('pending_value')
const sortKey = ref<SortKey>('accepted_total')
const sortDescending = ref(true)

const fmt = new Intl.NumberFormat('en-US')
const latestPeriod = computed(() => data.value?.latest_period ?? '')
const allRows = computed(() => {
  if (!data.value) return []
  return data.value.observations.filter((row) => row.period === (period.value || latestPeriod.value))
})
const comparisonRows = computed(() => allRows.value
  .filter((row) => hierarchy.value === 'jurisdictions'
    ? row.hierarchy_type === 'national_total' || row.hierarchy_type === 'bureau_jurisdiction'
    : row.hierarchy_type === 'office')
  .sort((a, b) => {
    if (sortKey.value === 'bureau_name') {
      return a.bureau_name.localeCompare(b.bureau_name) * (sortDescending.value ? -1 : 1)
    }
    const aValue = a[sortKey.value] ?? Number.NEGATIVE_INFINITY
    const bValue = b[sortKey.value] ?? Number.NEGATIVE_INFINITY
    return (Number(aValue) - Number(bValue)) * (sortDescending.value ? -1 : 1)
  }))
const selectorRows = computed(() => {
  const current = allRows.value
  return current.filter((row) => hierarchy.value === 'jurisdictions'
    ? row.hierarchy_type === 'national_total' || row.hierarchy_type === 'bureau_jurisdiction'
    : row.hierarchy_type === 'office')
})
const selected = computed(() => allRows.value.find((row) => row.bureau_code === selectedBureau.value))
const history = computed(() => {
  if (!data.value) return []
  return data.value.observations
    .filter((row) => row.bureau_code === selectedBureau.value)
    .sort((a, b) => a.period.localeCompare(b.period))
})
const heatPeriods = computed(() => data.value?.available_periods.slice().sort() ?? [])
const heatRows = computed(() => {
  if (hierarchy.value === 'offices') return allRows.value.filter((row) => row.hierarchy_type === 'office')
  return data.value?.observations
    .filter((row) => row.period === (period.value || latestPeriod.value)
      && row.hierarchy_type === 'bureau_jurisdiction')
    .sort((a, b) => a.sequence_number - b.sequence_number) ?? []
})
const source = computed(() => data.value?.source)

const measureOptions: Array<{ value: HeatMetric; label: string; format: (value: number) => string }> = [
  { value: 'pending_value', label: 'Pending balance', format: (value) => fmt.format(value) },
  { value: 'new_receipts', label: 'New receipts', format: (value) => fmt.format(value) },
  { value: 'completed_total', label: 'Total completed', format: (value) => fmt.format(value) },
  { value: 'throughput_ratio', label: 'Workload completed (%)', format: (value) => `${(value * 100).toFixed(1)}%` },
]
const selectedMetric = computed(() => measureOptions.find((metric) => metric.value === heatMetric.value)!)

const workloadChart = computed<EChartsOption>(() => {
  const row = selected.value
  const value = (key: keyof WorkloadObservation) =>
    typeof row?.[key] === 'number' ? row[key] as number : 0
  return {
    animationDuration: 280,
    aria: { enabled: true, description: 'Paired comparison of workload available and completed outcomes.' },
    grid: { left: 142, right: 28, top: 28, bottom: 42 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${fmt.format(Number(v))} 人` },
    legend: { top: 0, selectedMode: false },
    xAxis: {
      type: 'value',
      name: 'People (人)',
      nameLocation: 'middle',
      nameGap: 28,
      axisLabel: { formatter: (v: number) => fmt.format(v) },
      splitLine: { lineStyle: { color: 'var(--chart-grid)' } },
    },
    yAxis: { type: 'category', data: ['Workload available', 'Completed this month'] },
    series: [
      { name: 'Carried over', type: 'bar', stack: 'workload', barWidth: 42, data: [value('old_receipts'), 0], itemStyle: { color: '#315fbe' } },
      { name: 'New receipts', type: 'bar', stack: 'workload', barWidth: 42, data: [value('new_receipts'), 0], itemStyle: { color: '#8aabea' } },
      { name: 'Issued', type: 'bar', stack: 'completed', barWidth: 42, data: [0, value('issued')], itemStyle: { color: '#28866f' } },
      { name: 'Not issued', type: 'bar', stack: 'completed', barWidth: 42, data: [0, value('not_issued')], itemStyle: { color: '#d1813d' } },
      { name: 'Other closures / transfers', type: 'bar', stack: 'completed', barWidth: 42, data: [0, value('completed_other')], itemStyle: { color: '#8c79b6' } },
    ],
  }
})

const trendChart = computed<EChartsOption>(() => ({
  aria: { enabled: true, description: `Monthly COE workload trends for ${selected.value?.bureau_name ?? 'selected jurisdiction'}.` },
  grid: { left: 64, right: 24, top: 18, bottom: 48 },
  tooltip: { trigger: 'axis', valueFormatter: (v) => `${fmt.format(Number(v))} 人` },
  legend: { bottom: 0, type: 'scroll' },
  xAxis: { type: 'category', data: history.value.map((row) => row.period), axisLabel: { formatter: periodLabel } },
  yAxis: { type: 'value', name: '人', axisLabel: { formatter: (v: number) => fmt.format(v) }, splitLine: { lineStyle: { color: 'var(--chart-grid)' } } },
  series: [
    { name: 'Available workload', type: 'line', smooth: true, data: history.value.map((row) => row.accepted_total), itemStyle: { color: '#315fbe' } },
    { name: 'Total completed', type: 'line', smooth: true, data: history.value.map((row) => row.completed_total), itemStyle: { color: '#28866f' } },
    { name: 'Pending (calculated)', type: 'line', smooth: true, data: history.value.map((row) => row.pending_value), itemStyle: { color: '#b76c2b' } },
  ],
}))

const heatmapChart = computed<EChartsOption>(() => {
  const matrix = heatRows.value.flatMap((bureau, y) => heatPeriods.value.flatMap((month, x) => {
    const row = data.value?.observations.find((item) =>
      item.bureau_code === bureau.bureau_code && item.period === month)
    const value = row?.[heatMetric.value]
    return typeof value === 'number' ? [[x, y, heatMetric.value === 'throughput_ratio' ? value * 100 : value]] : []
  }))
  const max = matrix.reduce((result, item) => Math.max(result, item[2]), 0) || 1
  return {
    aria: { enabled: true, description: `Heatmap of ${selectedMetric.value.label} by bureau and month. A table alternative follows.` },
    grid: { left: 190, right: 28, top: 16, bottom: 54 },
    tooltip: {
      position: 'top',
      formatter: (params: unknown) => {
        const point = params as { value: [number, number, number] }
        const bureau = heatRows.value[point.value[1]]
        const month = heatPeriods.value[point.value[0]]
        return `${bureau?.bureau_name ?? ''}<br>${periodLabel(month)}<br>${selectedMetric.value.format(
          heatMetric.value === 'throughput_ratio' ? point.value[2] / 100 : point.value[2],
        )}${heatMetric.value === 'throughput_ratio' ? '' : ' 人'}`
      },
    },
    xAxis: { type: 'category', data: heatPeriods.value.map(periodLabel), splitArea: { show: true } },
    yAxis: { type: 'category', data: heatRows.value.map((row) => row.bureau_name), splitArea: { show: true } },
    visualMap: { min: 0, max, calculable: false, orient: 'horizontal', left: 'center', bottom: 4, inRange: { color: ['#edf2fd', '#7192d2', '#253f78'] }, textStyle: { color: 'var(--text-secondary)' } },
    series: [{ name: selectedMetric.value.label, type: 'heatmap', data: matrix, label: { show: false }, emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,.24)' } } }],
  }
})

function periodLabel(value: string) {
  if (!value) return ''
  const [year, month] = value.split('-')
  return `${year} / ${Number(month)}`
}

function number(value: number | null | undefined) {
  return value == null ? '—' : fmt.format(value)
}

function percent(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function dateTime(value: string | null | undefined) {
  if (!value) return 'Not checked yet'
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function statusLabel(status?: string | null) {
  switch (status) {
    case 'current': return 'Source current'
    case 'stale': return 'Stale data'
    case 'refresh_failed': return 'Refresh failed'
    case 'parser_needs_attention': return 'Data validation warning'
    case 'not_yet_configured': return 'Not configured'
    default: return 'Checking source'
  }
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) sortDescending.value = !sortDescending.value
  else {
    sortKey.value = key
    sortDescending.value = key !== 'bureau_name'
  }
}

function onHierarchyChange() {
  const first = selectorRows.value[0]
  selectedBureau.value = hierarchy.value === 'jurisdictions'
    ? selectorRows.value.find((row) => row.hierarchy_type === 'national_total')?.bureau_code ?? first?.bureau_code ?? ''
    : first?.bureau_code ?? ''
  if (heatMetric.value === 'pending_value' && !hasPending.value) heatMetric.value = 'new_receipts'
}

const hasPending = computed(() => data.value?.observations.some((row) => row.pending_value !== null) ?? false)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    data.value = await getOverview()
    if (data.value.refresh_queued) window.setTimeout(() => { void load() }, 2000)
    if (data.value.latest_period) {
      period.value = data.value.latest_period
      const national = data.value.rows.find((row) => row.hierarchy_type === 'national_total')
      selectedBureau.value = national?.bureau_code ?? data.value.rows[0]?.bureau_code ?? ''
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'Dashboard data could not be loaded.'
  } finally {
    loading.value = false
  }
}

async function refreshNow() {
  refreshBusy.value = true
  refreshMessage.value = ''
  try {
    const result = await startRefresh()
    refreshMessage.value = result.message
    window.setTimeout(() => { void load() }, 1800)
  } catch (error) {
    refreshMessage.value = error instanceof Error ? error.message : 'Refresh could not be started.'
  } finally {
    refreshBusy.value = false
  }
}

watch(period, () => {
  if (selected.value) return
  selectedBureau.value = selectorRows.value.find((row) => row.hierarchy_type === 'national_total')?.bureau_code
    ?? selectorRows.value[0]?.bureau_code ?? ''
})

watch(dark, (value) => {
  document.documentElement.dataset.theme = value ? 'dark' : 'light'
})

onMounted(() => { void load() })
</script>

<template>
  <div class="app-shell" :class="{ 'is-dark': dark }">
    <header class="topbar">
      <a class="brand" href="#" @click.prevent="view = 'workload'">
        <span class="brand-mark" aria-hidden="true">COE</span>
        <span class="brand-copy">
          <strong>Japan COE</strong>
          <small>Monthly workload</small>
        </span>
      </a>
      <nav class="main-nav" aria-label="Main navigation">
        <button :class="{ active: view === 'workload' }" @click="view = 'workload'">Workload</button>
        <button :class="{ active: view === 'processing' }" @click="view = 'processing'">Processing time</button>
        <button :class="{ active: view === 'sources' }" @click="view = 'sources'">Sources &amp; methods</button>
      </nav>
      <div class="topbar-actions">
        <span class="freshness-pill" :class="`status-${source?.status ?? 'not_yet_configured'}`">
          <span class="status-dot" aria-hidden="true" />
          {{ source?.status === 'current' ? 'Source current' : statusLabel(source?.status) }}
        </span>
        <button class="icon-button theme-toggle" :aria-label="dark ? 'Switch to light theme' : 'Switch to dark theme'" @click="dark = !dark">
          <span aria-hidden="true">{{ dark ? '☼' : '◐' }}</span>
        </button>
      </div>
    </header>

    <main>
      <section v-if="view === 'workload'" class="page-content">
        <div class="page-heading">
          <div>
            <div class="eyebrow">OFFICIAL MONTHLY STATISTICS</div>
            <h1>COE Processing</h1>
            <p class="heading-subtitle">Monthly workload and outcomes by immigration jurisdiction</p>
          </div>
          <button class="button button-outline refresh-button" :disabled="refreshBusy" @click="refreshNow">
            <span aria-hidden="true">↻</span>
            {{ refreshBusy ? 'Starting…' : 'Check for updates' }}
          </button>
        </div>

        <div v-if="loading && !data" class="loading-card" role="status">
          <span class="loading-spinner" />
          <div><strong>Loading official statistics</strong><span>Showing stored data first when available.</span></div>
        </div>
        <div v-else-if="loadError && !data" class="notice notice-error" role="alert">
          <strong>Dashboard data is unavailable.</strong>
          <span>{{ loadError }}</span>
          <button class="button button-outline" @click="load">Try again</button>
        </div>

        <template v-if="data">
          <div v-if="source?.status === 'refresh_failed' || source?.status === 'parser_needs_attention' || source?.status === 'stale'" class="notice notice-warning" role="status">
            <span class="notice-icon" aria-hidden="true">!</span>
            <div>
              <strong>{{ source.status === 'refresh_failed' ? 'Latest source check failed' : source.status === 'stale' ? 'Source data may be stale' : 'Source data needs review' }}</strong>
              <span>The last validated dataset remains available. {{ source.error_summary }}</span>
            </div>
          </div>
          <div v-if="refreshMessage" class="refresh-message" role="status">{{ refreshMessage }}</div>

          <section class="summary-banner" aria-labelledby="summary-title">
            <div class="summary-icon" aria-hidden="true">↗</div>
            <div>
              <div id="summary-title" class="eyebrow">CURRENT CONDITIONS</div>
              <p>{{ data.summary }}</p>
              <small>Workload counts are not waiting-time statistics and cannot predict an individual case.</small>
            </div>
          </section>

          <section class="filters-card" aria-label="Dashboard filters">
            <label class="filter-field">
              <span>Reporting month</span>
              <select v-model="period" aria-label="Reporting month">
                <option v-for="month in data.available_periods" :key="month" :value="month">{{ periodLabel(month) }}</option>
              </select>
            </label>
            <label class="filter-field bureau-filter">
              <span>{{ hierarchy === 'jurisdictions' ? 'Bureau / jurisdiction' : 'Office detail' }}</span>
              <select v-model="selectedBureau" aria-label="Bureau or office">
                <option v-for="row in selectorRows" :key="row.bureau_code" :value="row.bureau_code">
                  {{ row.hierarchy_type === 'office' ? `Office · ${row.bureau_name}` : row.bureau_name }}
                </option>
              </select>
            </label>
            <fieldset class="segmented-control">
              <legend>Hierarchy view</legend>
              <button :aria-pressed="hierarchy === 'jurisdictions'" :class="{ selected: hierarchy === 'jurisdictions' }" @click="hierarchy = 'jurisdictions'; onHierarchyChange()">Bureau totals</button>
              <button :aria-pressed="hierarchy === 'offices'" :class="{ selected: hierarchy === 'offices' }" @click="hierarchy = 'offices'; onHierarchyChange()">Office details</button>
            </fieldset>
          </section>

          <div class="metric-grid" aria-label="Selected bureau summary">
            <article class="metric-card metric-primary">
              <span class="metric-label">Available workload</span>
              <strong>{{ number(selected?.accepted_total) }}</strong>
              <small>Carried over + new receipts · {{ selected?.unit ?? '人' }}</small>
            </article>
            <article class="metric-card">
              <span class="metric-label">Carried over</span>
              <strong>{{ number(selected?.old_receipts) }}</strong>
              <small>受理_旧受 · {{ periodLabel(period) }}</small>
            </article>
            <article class="metric-card">
              <span class="metric-label">New receipts</span>
              <strong>{{ number(selected?.new_receipts) }}</strong>
              <small>受理_新受 · {{ periodLabel(period) }}</small>
            </article>
            <article class="metric-card">
              <span class="metric-label">Total completed</span>
              <strong>{{ number(selected?.completed_total) }}</strong>
              <small>Issued, not issued &amp; other closures</small>
            </article>
            <article class="metric-card metric-pending">
              <span class="metric-label">Pending at month-end</span>
              <strong>{{ number(selected?.pending_value) }}</strong>
              <small>{{ selected?.pending_label ?? 'Unavailable — totals did not validate' }}</small>
            </article>
          </div>

          <div class="section-heading">
            <div>
              <h2>Workload versus outcomes</h2>
              <p>{{ selected?.bureau_name }} · {{ periodLabel(period) }} · {{ selected?.unit ?? '人' }}</p>
            </div>
            <a class="text-link" href="#how-to-read">How to read this chart <span aria-hidden="true">↗</span></a>
          </div>
          <section class="panel chart-panel" aria-label="Workload and outcomes chart">
            <ChartPanel :option="workloadChart" :dark="dark" label="Paired stacked bars showing monthly workload available and completed outcomes." height="300px" />
            <div class="chart-caption">The two bars use separate stacks: workload available is not the same as monthly completions.</div>
            <div class="outcome-legend" aria-label="Completion categories">
              <span><i class="legend-dot issued" />Issued {{ number(selected?.issued) }}</span>
              <span><i class="legend-dot not-issued" />Not issued {{ number(selected?.not_issued) }}</span>
              <span><i class="legend-dot other" />Other closures / transfers {{ number(selected?.completed_other) }}</span>
              <span class="ratio-note">Share of available workload completed: {{ percent(selected?.throughput_ratio ?? null) }}</span>
            </div>
          </section>

          <section id="how-to-read" class="note-card">
            <div class="note-title"><span aria-hidden="true">ⓘ</span> How to read these figures</div>
            <ul>
              <li><code>旧受</code> is the source's carried-over receipt category; <code>新受</code> is new receipts and may include transfers between offices.</li>
              <li><code>既済</code> means processed for statistical purposes. <code>その他</code> is broader than withdrawals and can include transfers or cases no longer requiring processing.</li>
              <li>Pending is calculated as total workload minus total completed only when both published totals reconcile. It is app-calculated, not an e-Stat-published pending figure.</li>
              <li>These figures count people (<code>人</code>) in the office/jurisdiction used by the source. They do not identify an applicant's home prefecture or show how long any person waits.</li>
            </ul>
          </section>

          <section class="panel table-panel">
            <div class="panel-heading">
              <div><h2>{{ hierarchy === 'jurisdictions' ? 'Bureau comparison' : 'Office details' }}</h2><p>Latest figures for {{ periodLabel(period) }} · click a column heading to sort</p></div>
              <span class="mode-tag">{{ hierarchy === 'jurisdictions' ? 'Non-overlapping totals' : 'Separate office rows' }}</span>
            </div>
            <div class="table-scroll">
              <table>
                <caption class="sr-only">Monthly workload and outcomes for {{ periodLabel(period) }}</caption>
                <thead><tr>
                  <th scope="col"><button @click="toggleSort('bureau_name')">{{ hierarchy === 'jurisdictions' ? 'Bureau / jurisdiction' : 'Office' }} ↕</button></th>
                  <th scope="col"><button @click="toggleSort('old_receipts')">Carried over ↕</button></th>
                  <th scope="col"><button @click="toggleSort('new_receipts')">New receipts ↕</button></th>
                  <th scope="col"><button @click="toggleSort('accepted_total')">Workload ↕</button></th>
                  <th scope="col"><button @click="toggleSort('issued')">Issued ↕</button></th>
                  <th scope="col"><button @click="toggleSort('not_issued')">Not issued ↕</button></th>
                  <th scope="col"><button @click="toggleSort('completed_other')">Other ↕</button></th>
                  <th scope="col"><button @click="toggleSort('completed_total')">Completed ↕</button></th>
                  <th scope="col"><button @click="toggleSort('pending_value')">Pending* ↕</button></th>
                  <th scope="col"><button @click="toggleSort('pending_change')">Change ↕</button></th>
                  <th scope="col"><button @click="toggleSort('throughput_ratio')">Completed share ↕</button></th>
                </tr></thead>
                <tbody>
                  <tr v-for="row in comparisonRows" :key="row.bureau_code" :class="{ 'selected-row': row.bureau_code === selectedBureau }" @click="selectedBureau = row.bureau_code" @keydown.enter="selectedBureau = row.bureau_code" tabindex="0">
                    <th scope="row">{{ row.bureau_name }}<small v-if="row.hierarchy_type === 'national_total'">National total</small></th>
                    <td>{{ number(row.old_receipts) }}</td>
                    <td>{{ number(row.new_receipts) }}</td>
                    <td>{{ number(row.accepted_total) }}</td>
                    <td>{{ number(row.issued) }}</td>
                    <td>{{ number(row.not_issued) }}</td>
                    <td>{{ number(row.completed_other) }}</td>
                    <td>{{ number(row.completed_total) }}</td>
                    <td>{{ number(row.pending_value) }}<small v-if="row.pending_label">{{ row.pending_label === 'Calculated by the app' ? 'calculated' : 'official' }}</small></td>
                    <td :class="{ 'change-up': (row.pending_change ?? 0) > 0, 'change-down': (row.pending_change ?? 0) < 0 }">{{ row.pending_change == null ? '—' : `${row.pending_change > 0 ? '+' : ''}${number(row.pending_change)}` }}</td>
                    <td>{{ percent(row.throughput_ratio) }}</td>
                  </tr>
                  <tr v-if="!comparisonRows.length"><td colspan="11" class="empty-cell">No validated rows are available for this view.</td></tr>
                </tbody>
              </table>
            </div>
            <p class="table-footnote">* Pending is the calculated month-end balance unless explicitly marked official. “Completed share” is completed cases ÷ available workload; it is not an approval rate or a personal probability.</p>
          </section>

          <div class="two-column-grid">
            <section class="panel">
              <div class="panel-heading compact"><div><h2>Monthly trend</h2><p>{{ selected?.bureau_name }} · source unit: 人</p></div></div>
              <ChartPanel :option="trendChart" :dark="dark" label="Monthly line chart for workload, completed cases, and pending balance." height="288px" />
              <p class="panel-footnote">Pending balance is calculated when source totals reconcile. The series is workload flow, not processing duration.</p>
              <details class="trend-table">
                <summary>Accessible trend data table</summary>
                <div class="table-scroll">
                  <table>
                    <caption>Monthly workload and outcomes for {{ selected?.bureau_name }}</caption>
                    <thead><tr><th scope="col">Month</th><th scope="col">Available workload (人)</th><th scope="col">Completed (人)</th><th scope="col">Pending* (人)</th></tr></thead>
                    <tbody><tr v-for="row in history" :key="row.period"><th scope="row">{{ periodLabel(row.period) }}</th><td>{{ number(row.accepted_total) }}</td><td>{{ number(row.completed_total) }}</td><td>{{ number(row.pending_value) }}</td></tr></tbody>
                  </table>
                </div>
              </details>
            </section>
            <section class="panel">
              <div class="panel-heading compact"><div><h2>Bureau-by-month heatmap</h2><p>Official bureau jurisdiction aggregates only; parent and office rows are not combined.</p></div>
                <label class="small-select"><span class="sr-only">Heatmap measure</span><select v-model="heatMetric"><option v-for="option in measureOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              </div>
              <ChartPanel :option="heatmapChart" :dark="dark" :label="`Heatmap of ${selectedMetric.label} by bureau and month.`" height="288px" />
            </section>
          </div>
          <section class="panel data-alternative">
            <details>
              <summary>Accessible heatmap data table</summary>
              <div class="table-scroll">
                <table>
                  <caption>{{ selectedMetric.label }} by jurisdiction and month</caption>
                  <thead><tr><th scope="col">Bureau</th><th v-for="month in heatPeriods" :key="month" scope="col">{{ periodLabel(month) }}</th></tr></thead>
                  <tbody><tr v-for="bureau in heatRows" :key="bureau.bureau_code"><th scope="row">{{ bureau.bureau_name }}</th>
                    <td v-for="month in heatPeriods" :key="month">{{ (() => { const item = data?.observations.find((row) => row.bureau_code === bureau.bureau_code && row.period === month); const value = item?.[heatMetric]; return typeof value === 'number' ? selectedMetric.format(value) : '—' })() }}</td>
                  </tr></tbody>
                </table>
              </div>
            </details>
          </section>

          <footer class="source-footer">
            <div><strong>Source and freshness</strong><span>{{ source?.owner }} · {{ source?.name }}</span></div>
            <div><strong>Publication date</strong><span>{{ source?.latest_publication_date ?? 'Not reported' }}</span></div>
            <div><strong>Latest period</strong><span>{{ source?.latest_period ? periodLabel(source.latest_period) : 'Unavailable' }}</span></div>
            <div><strong>Last checked successfully</strong><span>{{ dateTime(source?.last_successful_fetch) }}</span></div>
            <a :href="source?.url" target="_blank" rel="noreferrer">Open e-Stat source ↗</a>
          </footer>
          <p class="disclaimer">General information only; not legal advice. Contact the relevant immigration office or employer for case-specific questions.</p>
        </template>
      </section>

      <section v-else-if="view === 'sources'" class="page-content secondary-page">
        <div class="eyebrow">TRANSPARENCY</div><h1>Sources &amp; methods</h1>
        <p class="heading-subtitle">Where the numbers come from, how balances are calculated, and what they cannot tell you.</p>
        <section class="panel source-detail">
          <div class="panel-heading"><div><h2>{{ source?.name ?? 'e-Stat monthly COE workload' }}</h2><p>{{ source?.owner ?? 'Immigration Services Agency of Japan / e-Stat' }}</p></div><span class="mode-tag">{{ statusLabel(source?.status) }}</span></div>
          <dl class="source-definition">
            <div><dt>Source</dt><dd><a :href="source?.url" target="_blank" rel="noreferrer">{{ source?.url }}</a></dd></div>
            <div><dt>Type / update policy</dt><dd>{{ source?.source_type }} · {{ source?.update_policy }}</dd></div>
            <div><dt>Measures</dt><dd>{{ source?.measure }}</dd></div>
            <div><dt>Unit / frequency</dt><dd>{{ source?.unit }} · {{ source?.frequency }}</dd></div>
            <div><dt>Latest publication / period</dt><dd>{{ source?.latest_publication_date ?? 'Not reported' }} · {{ source?.latest_period ? periodLabel(source.latest_period) : 'Unavailable' }}</dd></div>
            <div><dt>Last checked / successful fetch</dt><dd>{{ dateTime(source?.last_checked) }} / {{ dateTime(source?.last_successful_fetch) }}</dd></div>
          </dl>
        </section>
        <section class="panel source-detail">
          <div class="panel-heading"><div><h2>ISA processing-time source</h2><p>Immigration Services Agency of Japan</p></div><span class="mode-tag">Not configured</span></div>
          <p class="source-limitation">A compatible, comparable duration table has not been verified or imported. The checked status guide covers application requirements, so this dashboard does not infer a processing time from the e-Stat workload counts.</p>
          <a href="https://www.moj.go.jp/isa/applications/status/gijinkoku.html" target="_blank" rel="noreferrer">Open ISA status-of-residence guide ↗</a>
        </section>
        <section class="panel methods-panel"><h2>Definitions and calculations</h2>
          <ul><li><code>受理_旧受</code>: old receipts / carried-over workload.</li><li><code>受理_新受</code>: new receipts.</li><li><code>受理_総数</code>: total workload available in the source row.</li><li><code>既済_総数</code>: total processed; outcomes are issued, not issued, and other.</li><li>Calculated pending balance: <code>受理_総数 − 既済_総数</code>, shown only when receipt and completion totals reconcile and the result is non-negative.</li><li>Jurisdiction aggregates (names ending in 管内) and subordinate office rows are selected separately; the national total is taken directly from e-Stat.</li></ul>
          <p>Transfers can affect new receipts and other completed categories. The official “other” category is broader than withdrawals.</p>
        </section>
        <section class="panel methods-panel"><h2>Known limitations</h2><ul><li>e-Stat publishes monthly people counts here, not application-level start and completion dates.</li><li>No mean, median, percentile, distribution or individual waiting-time estimate is calculated from this table.</li><li>A rising count alone does not establish that an office is faster, slower, or backlogged.</li><li>These are source-defined office/jurisdiction classifications, not applicant home locations or nationalities.</li></ul></section>
        <p class="disclaimer">General information only; not legal advice. Contact the relevant immigration office or employer for case-specific questions.</p>
      </section>
      <section v-else class="page-content secondary-page">
        <div class="eyebrow">SUPPORTING STATISTICS</div><h1>Processing time</h1>
        <p class="heading-subtitle">Official duration statistics are kept separate from monthly workload counts.</p>
        <section class="panel unavailable-panel">
          <span class="unavailable-icon" aria-hidden="true">◷</span>
          <h2>No comparable duration series is configured</h2>
          <p>The e-Stat table in this dashboard reports monthly receipt and completion counts. It does not contain application-level durations, so no mean, median, percentile or waiting-time distribution can be derived from it.</p>
          <a href="https://www.moj.go.jp/isa/" target="_blank" rel="noreferrer">Visit the Immigration Services Agency ↗</a>
          <button class="button button-outline" @click="view = 'sources'">Review source details</button>
        </section>
        <p class="disclaimer">General information only; not legal advice. Aggregate workload figures do not predict an individual COE decision or completion date.</p>
      </section>
    </main>
  </div>
</template>
