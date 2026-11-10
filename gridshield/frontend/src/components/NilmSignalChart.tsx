import {
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { ChartData, ChartOptions } from "chart.js";
import type { NilmSignalSample } from "../types";

ChartJS.register(LinearScale, LineElement, PointElement, Tooltip, Legend);

interface NilmSignalChartProps {
  samples: NilmSignalSample[];
  buildingId: string | null;
}

export default function NilmSignalChart({
  samples,
  buildingId,
}: NilmSignalChartProps): React.ReactElement {
  const series = samples.filter((sample) => !buildingId || sample.building_id === buildingId);
  const data: ChartData<"line", Array<{ x: number; y: number }>> = {
    datasets: [
      {
        label: "Aggregate load · model input",
        data: series.map((sample) => ({
          x: sample.simulation_time_s,
          y: sample.aggregate_power_kw,
        })),
        borderColor: "#8bc4ad",
        backgroundColor: "rgba(139, 196, 173, 0.12)",
        borderWidth: 1.8,
        pointRadius: 0,
        tension: 0.12,
        fill: true,
        parsing: false,
      },
      {
        label: "Twin-state change",
        data: series
          .filter((sample) => sample.ground_truth_changes.length > 0)
          .map((sample) => ({
            x: sample.simulation_time_s,
            y: sample.aggregate_power_kw,
          })),
        borderColor: "#d3a66c",
        backgroundColor: "#d3a66c",
        pointRadius: 4,
        showLine: false,
        parsing: false,
      },
      {
        label: "Detected load step",
        data: series
          .filter((sample) => sample.estimated_changes.length > 0)
          .map((sample) => ({
            x: sample.simulation_time_s,
            y: sample.aggregate_power_kw,
          })),
        borderColor: "#7fb4d5",
        backgroundColor: "#7fb4d5",
        pointRadius: 3,
        pointStyle: "triangle",
        showLine: false,
        parsing: false,
      },
    ],
  };
  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { intersect: false, mode: "nearest" },
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: "#b9c5d0", boxWidth: 10, padding: 12, usePointStyle: true },
      },
      tooltip: {
        callbacks: {
          label: (context) =>
            `${context.dataset.label}: ${Number(context.parsed.y).toFixed(3)} kW`,
        },
      },
    },
    scales: {
      x: {
        type: "linear",
        title: { display: true, text: "Simulation time (s)", color: "#9aa9ad" },
        ticks: { color: "#9aa9ad", maxTicksLimit: 7 },
        grid: { color: "rgba(198, 211, 228, 0.08)" },
      },
      y: {
        title: { display: true, text: "Representative building load (kW)", color: "#9aa9ad" },
        ticks: { color: "#9aa9ad", maxTicksLimit: 5 },
        grid: { color: "rgba(198, 211, 228, 0.08)" },
      },
    },
  };

  return (
    <div className="nilm-chart">
      {series.length ? (
        <Line data={data} options={options} />
      ) : (
        <div className="systems-empty">
          Run a simulation to collect aggregate-load samples. No waveform is fabricated.
        </div>
      )}
    </div>
  );
}
