"""Aggregate the raw performance results and draw the report charts.

Reads   <results>/raw_timings.csv, phases.csv, levels.csv, errors.csv,
        system_samples.csv (optional; written by perf_runner.py --monitor)
Writes  <results>/summary.csv              long form, one row per (resource, operation, N)
        <results>/summary_<resource>.csv   Excel layout, one row per N
        <results>/charts/*.png              see the README for the list (old PNGs are removed first)

Times (as in the report):
  T2             transaction time of the single operation under test (one HTTP call).
  T1_level       time of one measurement level: populate from the previous level to N,
                 plus the first k add, update and delete operations with their restores.
  T1_cumulative  total populate time to build the collection from 0 up to N
                 (running sum of populate time over the levels of one repeat).
All are averaged over repeats.

Resource usage of a phase is the mean of the monitor samples taken inside that
phase (start_ts <= sample <= end_ts). Nothing is interpolated or smoothed; a
phase without samples gets blank usage and is reported.

Usage:  python performance/analyze.py [--results performance/results] [--logx]
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

HERE = Path(__file__).resolve().parent
RESOURCE_ORDER = ["todos", "projects", "categories"]
OPERATION_ORDER = ["populate", "add", "update", "delete"]
MEASURED = ["add", "update", "delete"]
USAGE = ["sys_cpu_pct", "java_cpu_pct", "avail_mem_mb", "java_rss_mb"]
NAMES = {"todos": ("Todo", "Todos"), "projects": ("Project", "Projects"), "categories": ("Category", "Categories")}

# One fixed colour per operation in every chart (validated categorical palette, slots 1-3).
OP_COLOR = {"add": "#257de0", "update": "#f47230", "delete": "#00b894"}
OP_LABEL = {"add": "Add", "update": "Update", "delete": "Delete"}
OTHER_COLOR = "#a6a6a6"   # samples outside an add/update/delete phase (populate, restore, wipe)
T1_COLOR = "#6a4ce2"

# metric column -> (chart file stem, title metric, y-axis label, start y at 0?)
USAGE_CHARTS = {
    "sys_cpu_pct": ("cpu", "CPU Use (%)", "System CPU use (% of all cores)", True),
    "java_cpu_pct": ("java_cpu", "Java Process CPU Use (%)", "Todo Manager JVM CPU use (% of one core)", True),
    "avail_mem_mb": ("memory", "Free Available Memory (MB)", "Available system memory (MB)", False),
    "java_rss_mb": ("java_rss", "Java Process Memory (MB)", "Todo Manager JVM resident memory, RSS (MB)", False),
}

# The three panels of the combined report figures: (column, panel title, short y label, zero-based?)
PANELS = [
    ("T2", "(a) Transaction time T2", "T2 (ms)", True),
    ("java_cpu_pct", "(b) Java process CPU", "CPU (% of one core)", True),
    ("avail_mem_mb", "(c) Free available memory", "Free memory (MB)", False),
]

THOUSANDS = FuncFormatter(lambda value, _: f"{value:,.0f}")
TIME_XLABEL = "Sample time (ms since the start of the experiment)"


def n_label(resource):
    return f"Number of {NAMES[resource][1]}"


# --------------------------------------------------------------------------- loading

def read(results, name, required=True):
    path = results / name
    if not path.exists():
        if required:
            raise SystemExit(f"{path} not found; run perf_runner.py first")
        return None
    frame = pd.read_csv(path)
    return None if frame.empty and not required else frame


def load_levels(results):
    levels = read(results, "levels.csv")
    levels = levels.rename(columns={"T1_ms": "T1_level_ms"})  # results written before the rename
    levels = levels.sort_values(["resource", "repeat", "N"])
    levels["T1_cumulative_ms"] = levels.groupby(["resource", "repeat"])["populate_ms"].cumsum()
    return levels


def assign_samples_to_phases(samples, phases):
    """Add resource/repeat/operation/N columns to each sample that falls inside a phase."""
    phases = phases.sort_values("start_ts").reset_index(drop=True)
    ts = samples["timestamp"].to_numpy()
    index = np.searchsorted(phases["start_ts"].to_numpy(), ts, side="right") - 1
    inside = (index >= 0) & (ts <= phases["end_ts"].to_numpy()[np.clip(index, 0, None)])
    for column in ["resource", "repeat", "operation", "N"]:
        values = phases[column].to_numpy()[np.clip(index, 0, None)]
        samples[column] = pd.Series(values, dtype=object).where(inside, None)
    return samples


# --------------------------------------------------------------------------- summaries

def summarise(raw, phases, levels, errors, samples):
    keys = ["resource", "operation", "N"]
    summary = raw.groupby(keys)["elapsed_ms"].agg(
        T2_ops="count", T2_mean_ms="mean", T2_median_ms="median",
        T2_p95_ms=lambda s: s.quantile(0.95), T2_std_ms="std", T2_min_ms="min", T2_max_ms="max",
    ).reset_index()

    error_counts = errors.groupby(keys).size().rename("errors") if errors is not None and len(errors) else None
    summary = summary.merge(error_counts.reset_index(), on=keys, how="left") if error_counts is not None \
        else summary.assign(errors=0)
    summary["errors"] = summary["errors"].fillna(0).astype(int)

    if samples is not None:
        in_phase = samples.dropna(subset=["operation"]).astype({"repeat": int, "N": int})
        per_phase = in_phase.groupby(["resource", "repeat", "operation", "N"])
        usage = per_phase[USAGE].mean().join(per_phase.size().rename("n_samples")).reset_index()
        # phases with no sample at all still count (as 0) in the samples-per-phase statistics
        usage = phases.merge(usage, on=["resource", "repeat", "operation", "N"], how="left")
        usage["n_samples"] = usage["n_samples"].fillna(0).astype(int)
        usage_summary = usage.groupby(keys).agg(
            **{col: (col, "mean") for col in USAGE},
            samples_per_phase_mean=("n_samples", "mean"), samples_per_phase_min=("n_samples", "min"),
        ).reset_index()
        summary = summary.merge(usage_summary, on=keys, how="left")

    t1 = levels.groupby(["resource", "N"])[["T1_level_ms", "T1_cumulative_ms", "level_wall_ms"]].mean()
    summary = summary.merge(t1.reset_index(), on=["resource", "N"], how="left")

    summary["resource"] = pd.Categorical(summary["resource"], RESOURCE_ORDER, ordered=True)
    summary["operation"] = pd.Categorical(summary["operation"], OPERATION_ORDER, ordered=True)
    return summary.sort_values(keys).reset_index(drop=True)


def wide_summary(resource, summary, samples, levels):
    """One row per N: N, add_ms, update_ms, delete_ms, cpu_pct, java_cpu_pct, free_mem_mb, java_rss_mb,
    T1_level_ms, T1_cumulative_ms. *_ms (operations) are mean T2; usage columns are the mean over all
    samples inside that level's add/update/delete phases."""
    rows = summary[summary.resource == resource]
    wide = rows[rows.operation.isin(MEASURED)].pivot(index="N", columns="operation", values="T2_mean_ms")
    wide = wide.reindex(columns=MEASURED).add_suffix("_ms")
    if samples is not None:
        measured = samples[(samples.resource == resource) & samples.operation.isin(MEASURED)]
        usage = measured.astype({"N": int}).groupby("N")[USAGE].mean()
        usage.columns = ["cpu_pct", "java_cpu_pct", "free_mem_mb", "java_rss_mb"]
        wide = wide.join(usage)
    wide = wide.join(levels[levels.resource == resource].groupby("N")[["T1_level_ms", "T1_cumulative_ms"]].mean())
    wide.columns.name = None
    return wide.reset_index()


def write_csv(frame, path):
    # utf-8-sig adds a BOM so Excel detects the encoding; "." decimals; no index column.
    frame.round(3).to_csv(path, index=False, encoding="utf-8-sig")


# --------------------------------------------------------------------------- drawing helpers
# Each draws onto a given Axes, so the individual charts and the combined panels share them.

def draw_by_operation(ax, rows, column):
    """Add/Update/Delete as three lines of `column` vs N."""
    for op in MEASURED:
        op_rows = rows[rows.operation == op]
        ax.plot(op_rows.N, op_rows[column], "-o", color=OP_COLOR[op], label=OP_LABEL[op])


def draw_t2_scatter(ax, raw, resource, start, size=3):
    """Every T2 measurement at the time it was taken."""
    for op in MEASURED:
        points = raw[(raw.resource == resource) & (raw.operation == op)]
        ax.scatter((points.timestamp - start) * 1000, points.elapsed_ms, s=size, color=OP_COLOR[op],
                   label=OP_LABEL[op], rasterized=True, linewidths=0)


def draw_samples(ax, window, start, resource, column, size=9):
    """All monitor samples as a grey line; samples inside Add/Update/Delete phases as coloured dots."""
    x = (window.timestamp - start) * 1000
    ax.plot(x, window[column], "-", color=OTHER_COLOR, linewidth=0.8, label="All samples (incl. populate / restore)")
    for op in MEASURED:
        mask = (window.resource == resource) & (window.operation == op)
        ax.scatter(x[mask], window.loc[mask, column], s=size, color=OP_COLOR[op],
                   label=f"Sample during {OP_LABEL[op]}", zorder=3, linewidths=0)


def finish_axes(ax, xlabel, ylabel, zero, logx=False):
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if logx:
        ax.set_xscale("log")
    ax.xaxis.set_major_formatter(THOUSANDS)
    if zero:
        ax.set_ylim(bottom=0)
    else:
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)


# --------------------------------------------------------------------------- charts

BASE_STYLE = {
    "figure.figsize": (9, 5.5), "figure.dpi": 100, "savefig.dpi": 200,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e6e6e6", "grid.linewidth": 0.8,
    "axes.edgecolor": "#999999", "axes.titlesize": 13, "axes.labelsize": 11,
    "lines.linewidth": 2, "lines.markersize": 5, "legend.frameon": False,
    "text.color": "#191919", "axes.labelcolor": "#191919",
    "xtick.color": "#666666", "ytick.color": "#666666",
}
# Combined figures are meant to be scaled to half a page, so everything is larger.
COMBINED_STYLE = {
    "axes.titlesize": 17, "axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 13,
    "legend.fontsize": 15, "figure.titlesize": 19, "lines.linewidth": 2.5, "lines.markersize": 6,
}


class Charts:
    def __init__(self, out_dir, logx):
        self.out_dir = out_dir
        self.logx = logx
        self.written = []
        out_dir.mkdir(parents=True, exist_ok=True)
        for stale in out_dir.glob("*.png"):  # generated folder: drop charts from earlier runs
            stale.unlink()

    def save(self, fig, name):
        path = self.out_dir / f"{name}.png"
        fig.savefig(path)
        plt.close(fig)
        self.written.append(path)

    def single(self, name, title, xlabel, ylabel, zero, draw, logx=False):
        fig, ax = plt.subplots()
        draw(ax)
        ax.set_title(title, loc="left")
        finish_axes(ax, xlabel, ylabel, zero, logx)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(markerscale=3)  # scatter points are tiny; keep legend swatches readable
        fig.tight_layout()
        self.save(fig, name)

    # ---- individual charts

    def vs_n(self, resource, summary, levels):
        singular, plural = NAMES[resource]
        rows = summary[summary.resource == resource]
        xlabel = n_label(resource)

        self.single(f"{resource}_time_vs_n", f"{singular} Transaction Time (ms) vs Number of {plural}",
                    xlabel, "Mean transaction time T2 (ms)", True,
                    lambda ax: draw_by_operation(ax, rows, "T2_mean_ms"), self.logx)
        for column, (stem, metric, ylabel, zero) in USAGE_CHARTS.items():
            if column in rows:
                self.single(f"{resource}_{stem}_vs_n", f"{singular} {metric} vs Number of {plural}",
                            xlabel, ylabel, zero, lambda ax, c=column: draw_by_operation(ax, rows, c), self.logx)

        per_n = levels[levels.resource == resource].groupby("N")[["T1_level_ms", "T1_cumulative_ms"]].mean()
        self.single(f"{resource}_t1_vs_n", f"{singular} Time per Level T1_level (ms) vs Number of {plural}",
                    xlabel, "T1_level: populate step + k add/update/delete (ms)", True,
                    lambda ax: ax.plot(per_n.index, per_n.T1_level_ms, "-o", color=T1_COLOR), self.logx)
        self.single(f"{resource}_t1_cumulative_vs_n",
                    f"{singular} Cumulative Populate Time T1_cumulative (ms) vs Number of {plural}",
                    xlabel, "Cumulative populate time (ms)", True,
                    lambda ax: ax.plot(per_n.index, per_n.T1_cumulative_ms, "-o", color=T1_COLOR), self.logx)

    def vs_time(self, resource, raw, window, start):
        singular, _ = NAMES[resource]
        self.single(f"{resource}_time_vs_sample_time", f"{singular} Transaction Time (ms) vs Sample Time (ms)",
                    TIME_XLABEL, "Transaction time T2 (ms)", True,
                    lambda ax: draw_t2_scatter(ax, raw, resource, start))
        if window is None:
            return
        for column, (stem, metric, ylabel, zero) in USAGE_CHARTS.items():
            self.single(f"{resource}_{stem}_vs_sample_time", f"{singular} {metric} vs Sample Time (ms)",
                        TIME_XLABEL, ylabel, zero, lambda ax, c=column: draw_samples(ax, window, start, resource, c))

    # ---- combined report figures: three panels side by side, one shared legend

    def combined(self, name, title, xlabel, panels, logx=False):
        """panels: list of (panel title, y label, zero-based?, draw function)."""
        with plt.rc_context(COMBINED_STYLE):
            fig, axes = plt.subplots(1, len(panels), figsize=(16, 5.6))
            for ax, (panel_title, ylabel, zero, draw) in zip(axes, panels):
                draw(ax)
                ax.set_title(panel_title, loc="left")
                finish_axes(ax, xlabel, ylabel, zero, logx)
                if not logx:
                    ax.xaxis.set_major_locator(MaxNLocator(4))  # fewer, wider-spaced ticks at large font
            handles, labels = axes[-1].get_legend_handles_labels()
            fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
            fig.legend(handles, labels, loc="upper center", ncol=len(labels), bbox_to_anchor=(0.5, 0.93),
                       markerscale=2.5, frameon=False)
            fig.tight_layout(rect=(0, 0, 1, 0.84))
            self.save(fig, name)

    def combined_vs_n(self, resource, summary):
        plural = NAMES[resource][1]
        rows = summary[summary.resource == resource]
        panels = [(panel_title, ylabel, zero,
                   lambda ax, c=("T2_mean_ms" if column == "T2" else column): draw_by_operation(ax, rows, c))
                  for column, panel_title, ylabel, zero in PANELS if column == "T2" or column in rows]
        title = f"{plural}: Transaction Time, CPU Use and Free Memory vs Number of {plural}"
        self.combined(f"{resource}_combined_vs_n", title, n_label(resource), panels)
        self.combined(f"{resource}_combined_vs_n_logx", title + " (log scale)", n_label(resource), panels, logx=True)

    def combined_vs_time(self, resource, raw, window, start):
        plural = NAMES[resource][1]
        panels = []
        for column, panel_title, ylabel, zero in PANELS:
            if column == "T2":
                draw = lambda ax: draw_t2_scatter(ax, raw, resource, start, size=2)  # noqa: E731
            elif window is not None:
                draw = lambda ax, c=column: draw_samples(ax, window, start, resource, c, size=10)  # noqa: E731
            else:
                continue
            panels.append((panel_title, ylabel, zero, draw))
        # The T2 panel's legend lacks the grey "all samples" line, so build the legend from the last panel.
        self.combined(f"{resource}_combined_vs_sample_time",
                      f"{plural}: Transaction Time, CPU Use and Free Memory vs Sample Time (ms)",
                      "Sample time (ms)", panels)


# --------------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=HERE / "results")
    parser.add_argument("--logx", action="store_true",
                        help="log-scale N axis on the individual 'vs N' charts "
                             "(the combined vs-N figure is always written in both versions)")
    args = parser.parse_args()

    raw = read(args.results, "raw_timings.csv")
    phases = read(args.results, "phases.csv")
    levels = load_levels(args.results)
    errors = read(args.results, "errors.csv", required=False)
    samples = read(args.results, "system_samples.csv", required=False)
    if samples is not None:
        samples = assign_samples_to_phases(samples.sort_values("timestamp").reset_index(drop=True), phases)

    summary = summarise(raw, phases, levels, errors, samples)
    write_csv(summary, args.results / "summary.csv")
    print(f"Wrote {args.results / 'summary.csv'} ({len(summary)} rows)")
    resources = [r for r in RESOURCE_ORDER if r in set(raw.resource)]
    for resource in resources:
        path = args.results / f"summary_{resource}.csv"
        write_csv(wide_summary(resource, summary, samples, levels), path)
        print(f"Wrote {path}")

    if samples is None:
        print("No system_samples.csv: CPU/memory columns and charts skipped (run perf_runner.py with --monitor)")
    else:
        measured = summary[summary.operation.isin(MEASURED)]
        print(f"Samples per add/update/delete phase: min {measured.samples_per_phase_min.min():.0f}, "
              f"mean {measured.samples_per_phase_mean.mean():.1f}")
        if (measured.samples_per_phase_min == 0).any():
            print("WARNING: some phases had no samples; raise --min-phase-s or lower --interval")

    plt.rcParams.update(BASE_STYLE)
    charts = Charts(args.results / "charts", args.logx)
    for resource in resources:
        own = phases[phases.resource == resource]
        start, end = own.start_ts.min(), own.end_ts.max()
        window = None if samples is None else samples[(samples.timestamp >= start) & (samples.timestamp <= end)]
        charts.vs_n(resource, summary, levels)
        charts.vs_time(resource, raw, window, start)
        charts.combined_vs_n(resource, summary)
        charts.combined_vs_time(resource, raw, window, start)
    print(f"Wrote {len(charts.written)} charts to {args.results / 'charts'}")


if __name__ == "__main__":
    main()
