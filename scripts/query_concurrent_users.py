#!/usr/bin/env python3
"""
Query Prometheus for concurrent JupyterHub user statistics across all prod hubs.

Requires an active port-forward to the Prometheus server (you may need to change
the namespace or deployment name if your setup differs):
    kubectl -n support port-forward deployment/support-prometheus-server 9090

kubectl will print "Handling connection for 9090" to stdout for each request.
To suppress it, redirect both stdout and stderr when starting the port-forward:
    kubectl -n support port-forward deployment/support-prometheus-server 9090 >/dev/null 2>&1 &

Then run:
    python3 scripts/query_concurrent_users.py

Optional arguments:
    --days                Number of days to look back (default: 90). Mutually exclusive
                          with --start/--end.
    --start               Start of the query window in local time, e.g. "2026-03-01" or
                          "2026-03-01 08:00". Requires --end. Mutually exclusive with --days.
    --end                 End of the query window in local time, e.g. "2026-04-15" or
                          "2026-04-15 18:00". Requires --start. Mutually exclusive with --days.
    --step                Sub-query resolution for instant queries (peak, % above threshold).
                          In Prometheus subquery notation [90d:5m], this is the '5m': how
                          finely Prometheus resamples the inner expression across the lookback
                          window. Does not affect the time-series data returned for the
                          hourly/daily/weekly breakdown tables. (default: 5m)
    --url                 Prometheus URL (default: http://localhost:9090)
    --threshold           User count threshold for "above N users" stats (default: 80).
                          Roughly the total users a single node with ~64GB RAM can support.
    --timezone            IANA timezone for local time display, should match hub users' location
                          (default: America/Los_Angeles)
    --namespace-pattern   Prometheus regex to match hub namespaces (default: .*-prod)
    --save-report         Optionally save a report to scripts/reports/: text,
                          markdown (or md), or html
    --config              Path to a YAML config file. Any key matching a CLI
                          arg sets its default; explicit CLI args always win.
    --debug               Print each Prometheus query and sample counts as the script runs.

Two independent resolutions are used per run:

  1. Instant query sub-query resolution (--step, default 5m)
     Controls how finely the peak/threshold instant queries sample across the lookback
     window. Returns a single aggregated value, not a time series.

  2. Range data sample interval (not user-configurable)
     Controls how many data points are fetched for the hourly, daily, and week-by-week
     breakdown tables. Auto-scales with the query window to maximise detail while staying
     within Prometheus point limits (~11k points):
         ≤  7 days  →  5-minute sample interval  (~2,000 points) — single-week deep-dives
         ≤ 30 days  → 15-minute sample interval  (~2,900 points) — month-long snapshots
         ≤ 90 days  → 30-minute sample interval  (~4,300 points) — default rolling view
         > 90 days  → 60-minute sample interval  (~4,300 points) — semester-plus ranges

Note: --start/--end ranges shorter than 7 days suppress the Active (WAU) column in
the week-by-week table. jupyterhub_active_users always reflects a rolling 7-day window,
so its values would extend outside the query range and be misleading for short spans.

Examples:
    # Default: last 90 days, 30-minute sample interval for breakdown tables
    python3 scripts/query_concurrent_users.py

    # Last 30 days, 15-minute sample interval
    python3 scripts/query_concurrent_users.py -d 30

    # Full spring semester — 115-day span, 60-minute sample interval
    python3 scripts/query_concurrent_users.py \\
        --start "2026-01-20" --end "2026-05-15" -r html

    # Historical month snapshot — 30-day span, 15-minute sample interval
    python3 scripts/query_concurrent_users.py \\
        --start "2026-02-01" --end "2026-03-01"

    # Midterm week deep-dive — 5-day span, 5-minute sample interval for max granularity
    python3 scripts/query_concurrent_users.py \\
        --start "2026-03-09 00:00" --end "2026-03-13 23:59"

Example config file (my-deployment.yaml):
    namespace_pattern: ".*-staging"
    timezone: "America/New_York"
    threshold: 60
"""

import argparse
import calendar
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from ruamel.yaml import YAML

DAYS_OF_WEEK = list(calendar.day_abbr)


def parse_local_dt(s, tz):
    """Parse a date/datetime string in the given timezone."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"Cannot parse datetime {s!r}; use YYYY-MM-DD or YYYY-MM-DD HH:MM"
    )


def prom_query(url, promql, time=None):
    """Run an instant Prometheus query and return parsed JSON."""
    params = {"query": promql}
    if time is not None:
        params["time"] = time
    try:
        with urlopen(f"{url}/api/v1/query?{urlencode(params)}") as resp:
            return json.load(resp)
    except URLError as e:
        print(f"Error connecting to Prometheus at {url}: {e}")
        print(
            "Is the port-forward to Prometheus running? See the docstring for setup instructions."
        )
        sys.exit(1)


def query_range(url, promql, start, end, step):
    """Run a Prometheus range query and return the list of (timestamp, value) pairs."""
    params = urlencode({"query": promql, "start": start, "end": end, "step": step})
    try:
        with urlopen(f"{url}/api/v1/query_range?{params}") as resp:
            data = json.load(resp)
    except URLError as e:
        print(f"Error connecting to Prometheus at {url}: {e}")
        print(
            "Is the port-forward to Prometheus running? See the docstring for setup instructions."
        )
        sys.exit(1)

    if data.get("status") != "success":
        print(f"Prometheus error: {data.get('error', 'unknown')}")
        sys.exit(1)

    return data["data"]["result"][0]["values"]


def get_range_samples(
    url, start_ts, end_ts, tz_name, namespace_pattern, step=1800, debug=False
):
    """
    Fetch total running servers over [start_ts, end_ts] at the given step (seconds).
    Returns a list of (datetime_local, value) tuples, converted to tz_name.
    """
    tz = ZoneInfo(tz_name)
    promql = f'sum(jupyterhub_running_servers{{namespace=~"{namespace_pattern}"}})'
    if debug:
        print(f"  [debug]   {promql}")

    values = query_range(url, promql, start_ts, end_ts, step=step)

    samples = []
    for ts, val in values:
        v = max(int(float(val)), 0)  # clamp negatives from counter resets
        dt = datetime.fromtimestamp(int(ts), tz=tz)
        samples.append((dt, v))
    return samples


def section(title):
    """Print a titled section header to stdout."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def format_text(report):
    """Render report data as plain text (mirrors stdout output)."""
    T = report["threshold"]
    T2 = report["threshold2"]
    range_label = report["range_label"]
    lines = []

    lines.append("JupyterHub Concurrent User Report")
    lines.append(f"Generated: {report['generated']}")
    lines.append(
        f"Range: {range_label}  |  Thresholds: {T}, {T2} users per node"
        f"  |  Namespace: {report['namespace_pattern']}  |  Timezone: {report['timezone']}"
    )
    lines.append(
        f"\nColumn legend:\n"
        f"  Peak     highest concurrent users observed\n"
        f"  Active   unique users with a running server (7-day rolling window)\n"
        f"  Hrs>{T}  hours where concurrent users exceeded {T} (node capacity)\n"
        f"  Hrs>{T2}  hours where concurrent users exceeded {T2} (1.5x node capacity)\n"
        f"  Avg      average concurrent users in the time bucket\n"
        f"  Pct>{T}  % of samples where concurrent users exceeded {T}\n"
        f"  Chart    bar chart; each # = 5 users"
    )

    lines.append(f"\n{'=' * 60}")
    lines.append(f"  Overall statistics ({range_label})")
    lines.append(f"{'=' * 60}")
    lines.append(f"  Peak concurrent users (all hubs): {report['overall']['peak']}")
    for a in report["overall"]["above"]:
        lines.append(
            f"  % of time above {a['n']:>3} users per node: "
            f"{a['pct']:5.2f}%  (~{a['hours']:.1f} hours total)"
        )

    lines.append(f"\n{'=' * 60}")
    lines.append(f"  Per-namespace peak concurrent users ({range_label})")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {'Namespace':<28} {'Peak':>5}  Chart")
    lines.append(f"  {'-' * 28} {'-' * 5}  -----")
    for hub, val in report["hubs"]:
        bar = "#" * (val // 5)
        lines.append(f"  {hub:<28} {val:>5}  {bar}")

    hrs_t_col = f"Hrs>{T}"
    hrs_t2_col = f"Hrs>{T2}"
    lines.append(f"\n{'=' * 60}")
    lines.append("  Week-by-week breakdown (Mon-Sun, local time)")
    lines.append(f"{'=' * 60}")
    lines.append(
        f"  {'Week of':<12} {'Peak':>5}  {'Active':>6}  "
        f"{hrs_t_col:>7}  {hrs_t2_col:>8}  Chart"
    )
    lines.append(f"  {'-' * 12} {'-' * 5}  {'-' * 6}  {'-' * 7}  {'-' * 8}  -----")
    for w in report["weeks"]:
        bar = "#" * (w["peak"] // 5)
        lines.append(
            f"  {w['week']:<12} {w['peak']:>5}  {str(w['active']):>6}  "
            f"{w['hrs_t']:>6.1f}h  {w['hrs_t2']:>7.1f}h  {bar}"
        )
    if report.get("active_note"):
        lines.append(f"  * {report['active_note']}")

    pct_col = f"Pct>{T}"
    lines.append(f"\n{'=' * 60}")
    lines.append("  Concurrent users by hour of day (local time)")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {'Hour':<10} {'Peak':>5}  {'Avg':>5}  {pct_col:>8}  Chart")
    lines.append(f"  {'-' * 10} {'-' * 5}  {'-' * 5}  {'-' * 8}  -----")
    for h in report["hours"]:
        bar = "#" * (h["peak"] // 5)
        lines.append(
            f"  {h['label']:<10} {h['peak']:>5}  {h['avg']:>5.1f}"
            f"  {h['pct']:>7.1f}%  {bar}"
        )

    lines.append(f"\n{'=' * 60}")
    lines.append("  Concurrent users by day of week (local time)")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {'Day':<5} {'Peak':>5}  {'Avg':>5}  {pct_col:>8}  Chart")
    lines.append(f"  {'-' * 5} {'-' * 5}  {'-' * 5}  {'-' * 8}  -----")
    for dow in report["days_of_week"]:
        bar = "#" * (dow["peak"] // 5)
        lines.append(
            f"  {dow['label']:<5} {dow['peak']:>5}  {dow['avg']:>5.1f}"
            f"  {dow['pct']:>7.1f}%  {bar}"
        )
    lines.append("")

    return "\n".join(lines)


def format_markdown(report):
    """Render report data as Markdown."""
    T = report["threshold"]
    T2 = report["threshold2"]
    range_label = report["range_label"]
    lines = []

    lines.append("# JupyterHub Concurrent User Report")
    lines.append("")
    lines.append(f"**Generated:** {report['generated']}  ")
    lines.append(
        f"**Range:** {range_label}  |  "
        f"**Thresholds:** {T}, {T2} users per node  |  "
        f"**Namespace:** {report['namespace_pattern']}  |  "
        f"**Timezone:** {report['timezone']}"
    )
    lines.append("")
    lines.append("**Column legend:**")
    lines.append("")
    lines.append("| Column | Description |")
    lines.append("|---|---|")
    lines.append("| Peak | Highest concurrent users observed |")
    lines.append(
        "| Active | Unique users with a running server (7-day rolling window) |"
    )
    lines.append(
        f"| Hrs>{T} | Hours where concurrent users exceeded {T} (node capacity) |"
    )
    lines.append(
        f"| Hrs>{T2} | Hours where concurrent users exceeded {T2} (1.5x node capacity) |"
    )
    lines.append("| Avg | Average concurrent users in the time bucket |")
    lines.append(f"| Pct>{T} | % of samples where concurrent users exceeded {T} |")
    lines.append("| Chart | Bar chart; each # = 5 users |")
    lines.append("")

    lines.append(f"## Overall statistics ({range_label})")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Peak concurrent users | **{report['overall']['peak']}** |")
    for a in report["overall"]["above"]:
        lines.append(
            f"| % of time above {a['n']} users per node"
            f" | {a['pct']:.2f}% (~{a['hours']:.1f} hours) |"
        )
    lines.append("")

    lines.append(f"## Per-namespace peak concurrent users ({range_label})")
    lines.append("")
    lines.append("| Namespace | Peak |")
    lines.append("|---|---|")
    for hub, val in report["hubs"]:
        lines.append(f"| {hub} | {val} |")
    lines.append("")

    lines.append("## Week-by-week breakdown (Mon-Sun, local time)")
    lines.append("")
    lines.append(f"| Week of | Peak | Active | Hrs > {T} | Hrs > {T2} |")
    lines.append("|---|---|---|---|---|")
    for w in report["weeks"]:
        lines.append(
            f"| {w['week']} | {w['peak']} | {w['active']}"
            f" | {w['hrs_t']:.1f}h | {w['hrs_t2']:.1f}h |"
        )
    if report.get("active_note"):
        lines.append(f"\n*{report['active_note']}*")
    lines.append("")

    lines.append("## Concurrent users by hour of day (local time)")
    lines.append("")
    lines.append(f"| Hour | Peak | Avg | % > {T} |")
    lines.append("|---|---|---|---|")
    for h in report["hours"]:
        lines.append(
            f"| {h['label']} | {h['peak']} | {h['avg']:.1f} | {h['pct']:.1f}% |"
        )
    lines.append("")

    lines.append("## Concurrent users by day of week (local time)")
    lines.append("")
    lines.append(f"| Day | Peak | Avg | % > {T} |")
    lines.append("|---|---|---|---|")
    for dow in report["days_of_week"]:
        lines.append(
            f"| {dow['label']} | {dow['peak']} | {dow['avg']:.1f} | {dow['pct']:.1f}% |"
        )

    return "\n".join(lines)


def format_html(report):
    """Render report data as a self-contained HTML document."""
    T = report["threshold"]
    T2 = report["threshold2"]
    range_label = report["range_label"]

    def th(*cells):
        return "<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>"

    def td(*cells):
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>JupyterHub Concurrent User Report</title>
  <style>
    body {{ font-family: sans-serif; max-width: 960px; margin: 2em auto; padding: 0 1em; color: #222; }}
    h1 {{ font-size: 1.4em; }}
    h2 {{ font-size: 1.1em; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 2em; }}
    p.meta {{ color: #666; font-size: 0.9em; }}
    table {{ border-collapse: collapse; margin: 1em 0; font-size: 0.9em; }}
    th, td {{ border: 1px solid #ddd; padding: 4px 12px; }}
    th {{ background: #f0f0f0; }}
    td {{ text-align: right; }}
    td:first-child {{ text-align: left; }}
    .bar {{ font-family: monospace; color: #999; }}
  </style>
</head>
<body>
<h1>JupyterHub Concurrent User Report</h1>
<p class="meta">
  Generated: {report["generated"]} &nbsp;|&nbsp;
  Range: {range_label} &nbsp;|&nbsp;
  Thresholds: {T}, {T2} users per node &nbsp;|&nbsp;
  Namespace: {report["namespace_pattern"]} &nbsp;|&nbsp;
  Timezone: {report["timezone"]}
</p>""")

    parts.append(
        f"<h2>Column legend</h2><table>"
        f"{th('Column', 'Description')}"
        f"{td('Peak', 'Highest concurrent users observed')}"
        f"{td('Active', 'Unique users with a running server (7-day rolling window)')}"
        f"{td(f'Hrs&gt;{T}', f'Hours where concurrent users exceeded {T} (node capacity)')}"
        f"{td(f'Hrs&gt;{T2}', f'Hours where concurrent users exceeded {T2} (1.5x node capacity)')}"
        f"{td('Avg', 'Average concurrent users in the time bucket')}"
        f"{td(f'Pct&gt;{T}', f'% of samples where concurrent users exceeded {T}')}"
        f"{td('Chart', 'Bar chart; each # = 5 users')}"
        f"</table>"
    )

    parts.append(f"<h2>Overall statistics ({range_label})</h2><table>")
    parts.append(th("Metric", "Value"))
    parts.append(
        td("Peak concurrent users", f"<strong>{report['overall']['peak']}</strong>")
    )
    for a in report["overall"]["above"]:
        parts.append(
            td(
                f"% of time above {a['n']} users per node",
                f"{a['pct']:.2f}% (~{a['hours']:.1f} hours)",
            )
        )
    parts.append("</table>")

    parts.append(f"<h2>Per-namespace peak concurrent users ({range_label})</h2><table>")
    parts.append(th("Namespace", "Peak", "Chart"))
    for hub, val in report["hubs"]:
        bar = "#" * (val // 5)
        parts.append(td(hub, val, f'<span class="bar">{bar}</span>'))
    parts.append("</table>")

    parts.append("<h2>Week-by-week breakdown (Mon-Sun, local time)</h2><table>")
    parts.append(th("Week of", "Peak", "Active", f"Hrs &gt; {T}", f"Hrs &gt; {T2}"))
    for w in report["weeks"]:
        parts.append(
            td(
                w["week"],
                w["peak"],
                w["active"],
                f"{w['hrs_t']:.1f}h",
                f"{w['hrs_t2']:.1f}h",
            )
        )
    parts.append("</table>")
    if report.get("active_note"):
        parts.append(f"<p><em>{report['active_note']}</em></p>")

    parts.append("<h2>Concurrent users by hour of day (local time)</h2><table>")
    parts.append(th("Hour", "Peak", "Avg", f"% &gt; {T}"))
    for h in report["hours"]:
        parts.append(td(h["label"], h["peak"], f"{h['avg']:.1f}", f"{h['pct']:.1f}%"))
    parts.append("</table>")

    parts.append("<h2>Concurrent users by day of week (local time)</h2><table>")
    parts.append(th("Day", "Peak", "Avg", f"% &gt; {T}"))
    for dow in report["days_of_week"]:
        parts.append(
            td(dow["label"], dow["peak"], f"{dow['avg']:.1f}", f"{dow['pct']:.1f}%")
        )
    parts.append("</table>")

    parts.append("</body></html>")
    return "\n".join(parts)


def write_report(report, fmt, script_dir):
    """Write a formatted report to scripts/reports/."""
    ext = {"text": "txt", "markdown": "md", "md": "md", "html": "html"}[fmt]
    if report.get("start") and report.get("end"):
        start_slug = report["start"].replace(" ", "T").replace(":", "")
        end_slug = report["end"].replace(" ", "T").replace(":", "")
        filename = f"concurrent-users-{start_slug}-to-{end_slug}.{ext}"
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"concurrent-users-{date_str}.{ext}"
    path = script_dir / "reports" / filename

    formatters = {
        "text": format_text,
        "markdown": format_markdown,
        "md": format_markdown,
        "html": format_html,
    }
    path.write_text(formatters[fmt](report), encoding="utf-8")
    print(f"\nReport written to {path}")


def main(args):
    ns_filter = f'namespace=~"{args.namespace_pattern}"'
    T = args.threshold
    T2 = int(T * 1.5)
    tz = ZoneInfo(args.timezone)

    # Determine query window from either --start/--end or --days
    if args.start:
        start_dt = parse_local_dt(args.start, tz)
        end_dt = parse_local_dt(args.end, tz)
        if end_dt <= start_dt:
            parser.error("--end must be after --start.")
        range_label = f"from {args.start} to {args.end}"
        query_time = int(end_dt.timestamp())
    else:
        end_dt = datetime.now(tz)
        start_dt = end_dt - timedelta(days=args.days)
        range_label = f"last {args.days} days"
        query_time = None

    duration = end_dt - start_dt
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    window = f"{int(duration.total_seconds())}s"

    # Auto-scale range-query step to maximise detail within Prometheus point limits
    if duration <= timedelta(days=7):
        range_step = 300  # 5m  — deep-dive granularity
    elif duration <= timedelta(days=30):
        range_step = 900  # 15m — month snapshot
    elif duration <= timedelta(days=90):
        range_step = 1800  # 30m — default rolling view
    else:
        range_step = 3600  # 60m — semester-plus spans

    step_label = {300: "5m", 900: "15m", 1800: "30m", 3600: "60m"}.get(
        range_step, f"{range_step}s"
    )

    # WAU metric reflects a rolling 7-day window; suppress for shorter ranges
    show_active = duration >= timedelta(days=7)

    subquery = f"[{window}:{args.step}]"

    if args.debug:
        print("[debug] time window:")
        print(f"  start:      {start_dt.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  end:        {end_dt.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  duration:   {duration}")
        print(f"  range_step: {step_label}")
        print(f"  subquery:   {subquery}")
        if query_time is not None:
            print(f"  query_time: {query_time}")

    print(f"Querying {args.url} — {range_label}")
    print(
        f"Thresholds: {T}, {T2} users per node  |  "
        f"Namespace: {args.namespace_pattern}  |  Timezone: {args.timezone}"
    )
    print(
        f"\nColumn legend:\n"
        f"  Peak     highest concurrent users observed\n"
        f"  Active   unique users with a running server (7-day rolling window)\n"
        f"  Hrs>{T}  hours where concurrent users exceeded {T} (node capacity)\n"
        f"  Hrs>{T2}  hours where concurrent users exceeded {T2} (1.5x node capacity)\n"
        f"  Avg      average concurrent users in the time bucket\n"
        f"  Pct>{T}  % of samples where concurrent users exceeded {T}\n"
        f"  Chart    bar chart; each # = 5 users"
    )

    report = {
        "generated": datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z"),
        "range_label": range_label,
        "start": args.start,
        "end": args.end,
        "threshold": T,
        "threshold2": T2,
        "timezone": args.timezone,
        "namespace_pattern": args.namespace_pattern,
        "active_note": (
            None
            if show_active
            else (
                "Active column suppressed: query range is shorter than 7 days. "
                "jupyterhub_active_users always reflects a rolling 7-day window "
                "and would extend outside the requested range."
            )
        ),
        "overall": {"peak": None, "above": []},
        "hubs": [],
        "weeks": [],
        "hours": [],
        "days_of_week": [],
    }

    # -------------------------------------------------------------------------
    # Section 1: Overall peak + time-above-threshold
    # -------------------------------------------------------------------------
    section(f"Overall statistics ({range_label})")

    promql = f"max_over_time(sum(jupyterhub_running_servers{{{ns_filter}}}){subquery})"
    if args.debug:
        print("  [debug] querying overall peak concurrent users")
        print(f"  [debug]   {promql}")
    data = prom_query(args.url, promql, time=query_time)
    peak = int(data["data"]["result"][0]["value"][1])
    print(f"  Peak concurrent users (all hubs): {peak}")
    report["overall"]["peak"] = peak

    for n in [T, T2]:
        promql = (
            f"sum_over_time((sum(jupyterhub_running_servers{{{ns_filter}}}) > bool {n}){subquery})"
            f" / count_over_time(sum(jupyterhub_running_servers{{{ns_filter}}}){subquery})"
        )
        if args.debug:
            print(f"  [debug] querying % of time above {n} users")
            print(f"  [debug]   {promql}")
        data = prom_query(args.url, promql, time=query_time)
        frac = float(data["data"]["result"][0]["value"][1])
        hours_above = frac * duration.total_seconds() / 3600
        print(
            f"  % of time above {n:>3} users per node: "
            f"{frac * 100:5.2f}%  (~{hours_above:.1f} hours total)"
        )
        report["overall"]["above"].append(
            {"n": n, "pct": frac * 100, "hours": hours_above}
        )

    # -------------------------------------------------------------------------
    # Section 2: Per-hub peak
    # -------------------------------------------------------------------------
    section(f"Per-namespace peak concurrent users ({range_label})")

    promql = f"max_over_time(jupyterhub_running_servers{{{ns_filter}}}{subquery})"
    if args.debug:
        print("  [debug] querying per-namespace peak concurrent users")
        print(f"  [debug]   {promql}")
    data = prom_query(args.url, promql, time=query_time)
    hubs = {}
    for r in data["data"]["result"]:
        ns = r["metric"].get("namespace", "unknown")
        val = int(r["value"][1])
        if val > hubs.get(ns, 0):
            hubs[ns] = val

    print(f"  {'Namespace':<28} {'Peak':>5}  Chart")
    print(f"  {'-' * 28} {'-' * 5}  -----")
    for hub, val in sorted(hubs.items(), key=lambda x: -x[1]):
        if val == 0:
            continue
        bar = "#" * (val // 5)
        print(f"  {hub:<28} {val:>5}  {bar}")
        report["hubs"].append((hub, val))

    # -------------------------------------------------------------------------
    # Fetch range data once for the remaining analyses (30m resolution)
    # -------------------------------------------------------------------------
    if args.debug:
        print(
            f"\n  [debug] fetching range samples at {step_label} resolution ({range_label})"
        )
    samples = get_range_samples(
        args.url,
        start_ts,
        end_ts,
        args.timezone,
        args.namespace_pattern,
        step=range_step,
        debug=args.debug,
    )
    if args.debug:
        print(f"  [debug] got {len(samples)} samples")

    # -------------------------------------------------------------------------
    # Section 3: Week-by-week breakdown
    # -------------------------------------------------------------------------
    section("Week-by-week breakdown (Mon–Sun, local time)")

    # Fetch weekly active users: last sample per week gives WAU for that week.
    # Suppressed for ranges < 7 days since the metric always reflects a 7-day window.
    week_active_users = {}
    if show_active:
        wau_promql = f'sum(max(jupyterhub_active_users{{period="7d", {ns_filter}}}) by (namespace))'
        if args.debug:
            print(
                "  [debug] fetching weekly active users (jupyterhub_active_users{period='7d'})"
            )
            print(f"  [debug]   {wau_promql}")
        au_vals = query_range(args.url, wau_promql, start_ts, end_ts, step=1800)
        for ts, val in au_vals:
            dt = datetime.fromtimestamp(int(ts), tz=tz)
            week_key = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
            week_active_users[week_key] = int(float(val))
        if args.debug:
            print(f"  [debug] got WAU data for {len(week_active_users)} weeks")
    elif args.debug:
        print("  [debug] skipping WAU query: range shorter than 7 days")

    week_samples = defaultdict(list)
    for dt, v in samples:
        week_start = dt - timedelta(days=dt.weekday())
        week_samples[week_start.strftime("%Y-%m-%d")].append(v)

    hrs_t_col = f"Hrs>{T}"
    hrs_t2_col = f"Hrs>{T2}"
    print(
        f"  {'Week of':<12} {'Peak':>5}  {'Active':>6}  "
        f"{hrs_t_col:>7}  {hrs_t2_col:>8}  Chart"
    )
    print(f"  {'-' * 12} {'-' * 5}  {'-' * 6}  {'-' * 7}  {'-' * 8}  -----")
    sample_hours = range_step / 3600
    for week in sorted(week_samples):
        s = week_samples[week]
        wpeak = max(s)
        active = week_active_users.get(week, "--") if show_active else "--"
        hrs_t = sum(1 for v in s if v > T) * sample_hours
        hrs_t2 = sum(1 for v in s if v > T2) * sample_hours
        bar = "#" * (wpeak // 5)
        print(
            f"  {week:<12} {wpeak:>5}  {str(active):>6}  "
            f"{hrs_t:>6.1f}h  {hrs_t2:>7.1f}h  {bar}"
        )
        report["weeks"].append(
            {
                "week": week,
                "peak": wpeak,
                "active": active,
                "hrs_t": hrs_t,
                "hrs_t2": hrs_t2,
            }
        )
    if report.get("active_note"):
        print(f"  * {report['active_note']}")

    # -------------------------------------------------------------------------
    # Section 4: Hour-of-day breakdown
    # -------------------------------------------------------------------------
    section("Concurrent users by hour of day (local time)")

    hour_samples = defaultdict(list)
    for dt, v in samples:
        hour_samples[dt.hour].append(v)

    pct_col = f"Pct>{T}"
    print(f"  {'Hour':<10} {'Peak':>5}  {'Avg':>5}  {pct_col:>8}  Chart")
    print(f"  {'-' * 10} {'-' * 5}  {'-' * 5}  {'-' * 8}  -----")
    for h in range(24):
        s = hour_samples[h]
        if not s:
            continue
        hpeak = max(s)
        havg = sum(s) / len(s)
        pct = sum(1 for v in s if v > T) / len(s) * 100
        bar = "#" * (hpeak // 5)
        label = f"{h:02d}:00-{(h + 1) % 24:02d}:00"
        print(f"  {label:<10} {hpeak:>5}  {havg:>5.1f}  {pct:>7.1f}%  {bar}")
        report["hours"].append({"label": label, "peak": hpeak, "avg": havg, "pct": pct})

    # -------------------------------------------------------------------------
    # Section 5: Day-of-week breakdown
    # -------------------------------------------------------------------------
    section("Concurrent users by day of week (local time)")

    dow_samples = defaultdict(list)
    for dt, v in samples:
        dow_samples[dt.weekday()].append(v)

    print(f"  {'Day':<5} {'Peak':>5}  {'Avg':>5}  {pct_col:>8}  Chart")
    print(f"  {'-' * 5} {'-' * 5}  {'-' * 5}  {'-' * 8}  -----")
    for d in range(7):
        s = dow_samples[d]
        if not s:
            continue
        dpeak = max(s)
        davg = sum(s) / len(s)
        pct = sum(1 for v in s if v > T) / len(s) * 100
        bar = "#" * (dpeak // 5)
        print(f"  {DAYS_OF_WEEK[d]:<5} {dpeak:>5}  {davg:>5.1f}  {pct:>7.1f}%  {bar}")
        report["days_of_week"].append(
            {"label": DAYS_OF_WEEK[d], "peak": dpeak, "avg": davg, "pct": pct}
        )

    # -------------------------------------------------------------------------
    # Optional: write report to scripts/reports/
    # -------------------------------------------------------------------------
    if args.save_report:
        write_report(report, args.save_report, Path(__file__).parent)


if __name__ == "__main__":
    # Pre-parse to get --config before setting up the full parser, so config
    # file values can be applied as defaults before argparse sees the rest.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("-c", "--config")
    pre_args, _ = pre.parse_known_args()

    config_defaults = {}
    if pre_args.config:
        _yaml = YAML(typ="safe")
        with open(pre_args.config) as f:
            config_defaults = _yaml.load(f) or {}

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-c", "--config", metavar="FILE", help="Path to a YAML config file"
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=None,
        help="Days to look back (default: 90). Mutually exclusive with --start/--end.",
    )
    parser.add_argument(
        "--start",
        metavar="DATETIME",
        help='Start of query window in local timezone, e.g. "2026-03-01" or "2026-03-01 08:00". '
        "Requires --end. Mutually exclusive with --days.",
    )
    parser.add_argument(
        "--end",
        metavar="DATETIME",
        help='End of query window in local timezone, e.g. "2026-04-15" or "2026-04-15 18:00". '
        "Requires --start. Mutually exclusive with --days.",
    )
    parser.add_argument(
        "--step",
        default="5m",
        help="Query resolution step for instant queries (default: 5m)",
    )
    parser.add_argument(
        "-u",
        "--url",
        default="http://localhost:9090",
        help="Prometheus URL (default: http://localhost:9090)",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=int,
        default=80,
        help=(
            "User count threshold for percentage/hours stats (default: 80). "
            "Roughly the total users a single node with ~64GB RAM can support."
        ),
    )
    parser.add_argument(
        "-z",
        "--timezone",
        default="America/Los_Angeles",
        help=(
            "IANA timezone for local time display, should match hub users' location "
            "(default: America/Los_Angeles)"
        ),
    )
    parser.add_argument(
        "-n",
        "--namespace-pattern",
        default=".*-prod",
        help="Prometheus regex to match hub namespaces (default: .*-prod)",
    )
    parser.add_argument(
        "-r",
        "--save-report",
        choices=["text", "markdown", "md", "html"],
        help=(
            "Save a report to scripts/reports/ in the specified format "
            "(md and markdown are equivalent)"
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print each Prometheus query and sample counts as the script runs",
    )

    if config_defaults:
        parser.set_defaults(**config_defaults)

    args = parser.parse_args()

    using_range = bool(args.start or args.end)
    using_days = args.days is not None
    if using_range and using_days:
        parser.error("--start/--end and --days are mutually exclusive.")
    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must both be provided together.")
    if not using_days and not using_range:
        args.days = 90

    if args.debug:
        print("[debug] resolved args:")
        for k, v in sorted(vars(args).items()):
            print(f"  {k}: {v!r}")

    main(args)
