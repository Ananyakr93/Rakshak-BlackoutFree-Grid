import {
  Chart as ChartJS,
  CategoryScale,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type Plugin,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { ChartData, ChartOptions } from "chart.js";
import type { GridParameters, RunEvent, TelemetrySample } from "../types";

ChartJS.register(LineController, CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface FrequencyChartProps {
  telemetry: TelemetrySample[];
  events: RunEvent[];
  grid: GridParameters | null;
  disturbanceStart: number | null;
  comparisonSeries?: Array<{ policy: string; telemetry: TelemetrySample[] }>;
}

function markerPlugin(events: RunEvent[], disturbanceStart: number | null): Plugin<"line"> {
  const markers = [
    ...(disturbanceStart === null ? [] : [{ time: disturbanceStart, label: "Disturbance", color: "#b18a50" }]),
    ...events
      .filter((event) => /shed|restore|trip|fault/i.test(event.event_type))
      .map((event) => ({
        time: event.simulation_time_s,
        label: event.event_type.replace(/_/g, " "),
        color: /fault|trip/i.test(event.event_type) ? "#bc6d70" : "#79a99a",
      })),
  ];

  return {
    id: "simulation-event-markers",
    afterDatasetsDraw(chart) {
      const xScale = chart.scales.x;
      const area = chart.chartArea;
      const context = chart.ctx;
      context.save();
      markers.forEach((marker) => {
        const x = xScale.getPixelForValue(marker.time);
        if (x < area.left || x > area.right) return;
        context.beginPath();
        context.setLineDash([3, 5]);
        context.strokeStyle = marker.color;
        context.globalAlpha = 0.65;
        context.moveTo(x, area.top);
        context.lineTo(x, area.bottom);
        context.stroke();
      });
      context.restore();
    },
  };
}

function referenceDataset(label: string, y: number, xMax: number, color: string, dash: number[]) {
  return {
    label,
    data: [
      { x: 0, y },
      { x: xMax, y },
    ],
    borderColor: color,
    borderDash: dash,
    borderWidth: 1,
    pointRadius: 0,
    pointHitRadius: 0,
    tension: 0,
    parsing: false as const,
  };
}

export default function FrequencyChart({
  telemetry,
  events,
  grid,
  disturbanceStart,
  comparisonSeries = [],
}: FrequencyChartProps): React.ReactElement {
  const series = comparisonSeries.length
    ? comparisonSeries
    : [{ policy: "Current run", telemetry }];
  const xMax = Math.max(
    ...series.map((item) => item.telemetry[item.telemetry.length - 1]?.simulation_time_s ?? 0),
    60,
  );
  const observedFrequencies = series.flatMap((item) =>
    item.telemetry.map((sample) => sample.frequency_hz),
  );
  const yMin = Math.floor(
    (Math.min(...observedFrequencies, grid?.f_s3_hz ?? 49.4) - 0.05) * 10,
  ) / 10;
  const yMax = Math.ceil(
    (Math.max(...observedFrequencies, grid?.f_o1_hz ?? 50.05) + 0.05) * 10,
  ) / 10;
  const colors = ["#8bc4ad", "#d3a66c", "#8ba9d5", "#c18aa0"];
  const datasets = [
    ...series.map((item, index) => ({
      label: item.policy,
      data: item.telemetry.map((sample) => ({
        x: sample.simulation_time_s,
        y: sample.frequency_hz,
      })),
      borderColor: colors[index % colors.length],
      backgroundColor: `${colors[index % colors.length]}14`,
      borderWidth: 1.8,
      pointRadius: 0,
      pointHitRadius: 8,
      tension: 0.18,
      parsing: false as const,
    })),
    referenceDataset("Nominal 50.00 Hz", grid?.f0_hz ?? 50, xMax, "#9aa9ae", []),
    ...(grid
      ? [
          referenceDataset(`S0 advisory ${grid.f_s0_hz.toFixed(2)}`, grid.f_s0_hz, xMax, "#8d9ba0", [3, 5]),
          referenceDataset(`S1 shed ${grid.f_s1_hz.toFixed(2)}`, grid.f_s1_hz, xMax, "#b18a50", [5, 4]),
          referenceDataset(`S2 shed ${grid.f_s2_hz.toFixed(2)}`, grid.f_s2_hz, xMax, "#b98161", [5, 4]),
          referenceDataset(`S3 shed ${grid.f_s3_hz.toFixed(2)}`, grid.f_s3_hz, xMax, "#bc6d70", [5, 4]),
          referenceDataset(`Recovery ${grid.f_recovery_hz.toFixed(2)}`, grid.f_recovery_hz, xMax, "#79a99a", [2, 4]),
          referenceDataset(`O1 absorb ${grid.f_o1_hz.toFixed(2)}`, grid.f_o1_hz, xMax, "#8698b2", [5, 4]),
          referenceDataset(`O2 absorb+ ${grid.f_o2_hz.toFixed(2)}`, grid.f_o2_hz, xMax, "#a2859a", [5, 4]),
        ]
      : []),
  ];

  const data: ChartData<"line", Array<{ x: number; y: number }>> = {
    datasets: datasets as ChartData<"line", Array<{ x: number; y: number }>>["datasets"],
  };
  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { intersect: false, mode: "nearest" },
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          color: "#aab7c8",
          boxWidth: 12,
          boxHeight: 2,
          padding: 10,
          usePointStyle: true,
          filter: (item) => item.datasetIndex !== undefined && item.datasetIndex < series.length + 1,
        },
      },
      tooltip: {
        backgroundColor: "#111927",
        borderColor: "rgba(255, 255, 255, 0.16)",
        borderWidth: 1,
        titleColor: "#e1e8f0",
        bodyColor: "#c5d0dc",
        callbacks: {
          label: (context) => `${context.dataset.label}: ${Number(context.parsed.y).toFixed(3)} Hz`,
        },
      },
    },
    scales: {
      x: {
        type: "linear",
        min: 0,
        max: xMax,
        title: { display: true, text: "Simulation time (s)", color: "#8998aa" },
        ticks: {
          color: "#9aa8ba",
          maxTicksLimit: 7,
          callback: (value) => Number(value).toFixed(0),
        },
        grid: { color: "rgba(198, 211, 228, 0.1)" },
      },
      y: {
        min: yMin,
        max: yMax,
        title: { display: true, text: "Frequency (Hz)", color: "#8998aa" },
        ticks: { color: "#9aa8ba", maxTicksLimit: 6 },
        grid: { color: "rgba(198, 211, 228, 0.1)" },
      },
    },
  };

  return (
    <div className="frequency-chart">
      <Line data={data} options={options} plugins={[markerPlugin(events, disturbanceStart)]} />
      {series.every((item) => item.telemetry.length === 0) ? (
        <div className="chart-empty">
          <span>No frequency samples received</span>
          <small>Reference thresholds are shown; no response curve is fabricated.</small>
        </div>
      ) : null}
    </div>
  );
}
