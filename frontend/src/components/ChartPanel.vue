<script setup lang="ts">
import { init, use, type ECharts } from 'echarts/core'
import type { EChartsOption } from 'echarts'
import { BarChart, HeatmapChart, LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

use([BarChart, HeatmapChart, LineChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

const props = defineProps<{
  option: EChartsOption
  dark: boolean
  label: string
  height?: string
}>()

const host = ref<HTMLDivElement | null>(null)
let chart: ECharts | undefined
let resizeObserver: ResizeObserver | undefined

function renderChart() {
  if (!host.value) return
  if (!chart) chart = init(host.value, props.dark ? 'dark' : undefined)
  chart.setOption(props.option, true)
}

onMounted(() => {
  renderChart()
  if (host.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(host.value)
  }
})

watch(() => [props.option, props.dark], () => {
  chart?.dispose()
  chart = undefined
  renderChart()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div
    ref="host"
    class="chart-canvas"
    :style="{ height: height ?? '320px' }"
    role="img"
    :aria-label="label"
  />
</template>
