from __future__ import annotations

import argparse
import base64
import os
import uuid
from datetime import date, timedelta

from dash import Dash, Input, Output, State, html, no_update

from charts import make_conversion_trend_figure, make_funnel_figure, make_heatmap_figure, make_source_donut_figure, make_spend_revenue_figure
from config import DEFAULT_DAYS, REGION_GROUP_ORDER, TARGET_IDS
from data_loader import DataBundle, UPLOAD_SLOTS, load_folder, load_uploads
from layout import OVERALL_CARDS, PAID_CARDS, build_dashboard, build_layout, target_input_id, target_progress_id
from metrics import as_number, compute_daily_trends, compute_funnel, compute_kpis, compute_region_heatmap, compute_source_share, compute_target_progress

KPI_NAMES = [name for _, name in OVERALL_CARDS] + [name for _, name in PAID_CARDS]
MONEY_KPIS = {"all_revenue", "paid_revenue", "ad_spend", "cost_per_lead", "cost_per_mql"}
SLOT_IDS = list(UPLOAD_SLOTS)

# 上传的数据只留在进程内存里：浏览器会话用 data-key 指向自己那一份
DATA_CACHE: dict[str, DataBundle] = {}
CACHE_LIMIT = 8


def _as_date(value):
    """DatePicker 返回 ISO 字符串，默认日期是 date 对象，这里统一成 date。"""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _previous_period(start, end):
    """等长前移区间：与当前区间天数相同、紧邻其前的一段，用于环比。"""
    if start is None or end is None or end < start:
        return None, None
    span = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=span - 1), previous_end


def _format_value(name, value):
    if value is None:
        return "N/A"
    if name in MONEY_KPIS:
        return f"${value:,.0f}"
    if name == "roas":
        return f"{value:.1f}x"
    return f"{value:,.0f}"


def _format_amount(value, money: bool) -> str:
    return f"${value:,.0f}" if money else f"{value:,.0f}"


def _progress_line(entry: dict):
    """目标达成率那一行：`73% of target · 4,117 to go`。

    没填目标或该区间没有实际值时显示 `N/A`，不能伪造成 0%。
    """
    target = entry.get("target")
    money = entry.get("format") == "money"
    if target is None:
        return html.Span("No target set", className="target-none")
    attainment, gap, actual = entry.get("attainment"), entry.get("gap"), entry.get("actual")
    if attainment is None or gap is None or actual is None:
        return html.Span("N/A", className="target-none")
    caption = f"Target {_format_amount(target, money)}"
    if gap >= 0:
        return html.Span(f"{attainment:.0%} of target · {_format_amount(gap, money)} ahead", className="target-met", title=caption)
    return html.Span(f"{attainment:.0%} of target · {_format_amount(-gap, money)} to go", className="target-below", title=caption)


def _store_bundle(bundle: DataBundle) -> str:
    """把数据集放进进程内存，返回浏览器会话持有的 key。"""
    key = uuid.uuid4().hex
    DATA_CACHE[key] = bundle
    while len(DATA_CACHE) > CACHE_LIMIT:
        DATA_CACHE.pop(next(iter(DATA_CACHE)))
    return key


def _is_loaded(bundle: DataBundle, slot: str) -> bool:
    frame = bundle.tables.get(slot)
    return frame is not None and not frame.empty


def _bundle_window(bundle: DataBundle):
    """数据集里最小/最大日期，以及默认区间起点（最近 DEFAULT_DAYS 天）。"""
    dates = []
    for frame in bundle.tables.values():
        if not frame.empty:
            dates.extend(frame["date"].dropna().tolist())
    if not dates:
        return None, None, None
    max_date = max(dates).date()
    min_date = min(dates).date()
    return min_date, max_date, max(max_date - timedelta(days=DEFAULT_DAYS - 1), min_date)


def _decode_upload(content: str) -> bytes:
    """dcc.Upload 的 contents 是 `data:text/csv;base64,xxx`。"""
    payload = str(content).partition(",")[2]
    return base64.b64decode(payload)


def _as_list(value) -> list:
    """dcc.Upload 的 contents / filename 单文件是字符串、多文件是列表，统一成列表。"""
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _file_label(name, slot: str) -> str:
    text = str(name).strip() if name else ""
    text = text.replace("\\", "/").split("/")[-1]
    return text or f"{slot}.csv"


def _status_line(text: str, level: str) -> html.Div:
    return html.Div(text, className=f"status-line {level}")


def _slot_status(bundle: DataBundle, slot: str, filenames: list[str], error: str | None) -> list:
    """单个上传格子的状态行：文件名 + 行数 + 日期范围，问题按严重级别单独成行。"""
    if error:
        return [_status_line(error, "error")]
    if not filenames:
        return [_status_line("No file selected", "muted")]

    frame = bundle.tables.get(slot)
    messages = [d.message for d in bundle.diagnostics if d.level == "error" and d.path in set(filenames)]
    warnings = [d.message for d in bundle.diagnostics if d.level == "warning" and d.path in set(filenames)]
    lines = []
    if frame is None or frame.empty:
        # 没读到行时先给原因（如「放错格子」的提示），再报错
        lines.extend(_status_line(message, "warn") for message in warnings)
        lines.extend(_status_line(message, "error") for message in (messages or ["No rows could be loaded from this file"]))
        return lines
    start, end = frame["date"].min().date(), frame["date"].max().date()
    lines.append(_status_line(f"{', '.join(filenames)} · {len(frame):,} rows · {start:%b %d} – {end:%b %d, %Y}", "ok"))
    lines.extend(_status_line(message, "warn") for message in warnings)
    lines.extend(_status_line(message, "error") for message in messages)
    return lines


def create_app(data_dir=None):
    """`data_dir` 显式给定时走服务端数据目录（Docker / 本地调试），否则由使用者上传四个 CSV。"""
    bundle = load_folder(data_dir) if data_dir else None
    preload_key = _store_bundle(bundle) if bundle is not None and bundle.tables else None

    if preload_key:
        min_date, max_date, start_date = _bundle_window(bundle)
    else:
        min_date = max_date = start_date = None

    app = Dash(__name__, title="Digital Marketing KPI Dashboard", suppress_callback_exceptions=True)
    app.layout = build_layout(
        REGION_GROUP_ORDER,
        min_date,
        max_date,
        start_date,
        preloaded=preload_key is not None,
        reset=preload_key is None,
        data_key=preload_key,
    )

    output_ids = [
        Output(f"kpi-{name.replace('_', '-')}", "children") for name in KPI_NAMES
    ] + [Output(f"delta-{name.replace('_', '-')}", "children") for name in KPI_NAMES] + [Output("data-status", "children"), Output("overall-funnel", "figure"), Output("paid-funnel", "figure"), Output("conversion-trend", "figure"), Output("traffic-share", "figure"), Output("lead-share", "figure"), Output("mql-share", "figure"), Output("efficiency-trend", "figure"), Output("region-heatmap", "figure")]

    @app.callback(
        Output("data-key", "data"),
        Output("upload-gate", "style"),
        Output("dashboard-root", "children"),
        *[Output(f"slot-status-{slot}", "children") for slot in SLOT_IDS],
        *[Input(f"upload-{slot}", "contents") for slot in SLOT_IDS],
        *[State(f"upload-{slot}", "filename") for slot in SLOT_IDS],
        State("target-store", "data"),
        prevent_initial_call=True,
    )
    def handle_uploads(*args):
        contents = args[: len(SLOT_IDS)]
        filenames = args[len(SLOT_IDS) : 2 * len(SLOT_IDS)]
        stored_targets = args[-1]
        files: list[tuple[str, str, bytes]] = []
        uploaded = {slot: [] for slot in SLOT_IDS}
        errors: dict[str, str] = {}
        for slot, slot_contents, slot_filenames in zip(SLOT_IDS, contents, filenames):
            names = _as_list(slot_filenames)
            for index, content in enumerate(_as_list(slot_contents)):
                if not content:
                    continue
                label = _file_label(names[index] if index < len(names) else None, slot)
                uploaded[slot].append(label)
                try:
                    files.append((slot, label, _decode_upload(content)))
                except Exception as exc:  # 损坏的 base64 / 非 CSV 内容
                    errors[slot] = f"{label} could not be decoded: {exc}"

        bundle = load_uploads(files) if files else DataBundle({}, [])
        statuses = [_slot_status(bundle, slot, uploaded[slot], errors.get(slot)) for slot in SLOT_IDS]
        if not all(_is_loaded(bundle, slot) for slot in SLOT_IDS):
            # 还缺表：留在上传页，data-key 清空，避免拿着不完整的数据出 dashboard
            return (None, {}, None, *statuses)

        min_date, max_date, start_date = _bundle_window(bundle)
        return (
            _store_bundle(bundle),
            {"display": "none"},
            # 目标输入框用浏览器里已保存的值回填，避免上传后被打回默认值
            build_dashboard(REGION_GROUP_ORDER, min_date, max_date, start_date, show_reset=True, targets=stored_targets),
            *statuses,
        )

    @app.callback(
        *[Output(f"upload-{slot}", "contents") for slot in SLOT_IDS],
        Input("reset-data", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_uploads(_clicks):
        """清空四个格子，回到上传页；后续状态由 handle_uploads 统一刷新。"""
        return [None] * len(SLOT_IDS)

    @app.callback(output_ids, Input("date-range", "start_date"), Input("date-range", "end_date"), Input("region-filter", "value"), Input("data-key", "data"))
    def update_dashboard(start, end, selected_regions, data_key):
        bundle = DATA_CACHE.get(data_key) if data_key else None
        if bundle is None:
            # 还没上传（或刚被重置）：dashboard 组件不存在，什么都不用更新
            return [no_update] * len(output_ids)

        _min_date, max_date, default_start = _bundle_window(bundle)
        range_start = _as_date(start) or default_start
        range_end = _as_date(end) or max_date
        date_range = (range_start, range_end)
        regions_value = selected_regions or []
        kpis = compute_kpis(bundle, date_range, regions_value)
        trend = compute_daily_trends(bundle, date_range, regions_value)
        previous_range = _previous_period(range_start, range_end)
        previous = compute_kpis(bundle, previous_range, regions_value) if previous_range[0] else {}
        values = [_format_value(name, kpis.get(name)) for name in KPI_NAMES]
        deltas = []
        for name in KPI_NAMES:
            current, prior = kpis.get(name), previous.get(name)
            change = None if current is None or prior in (None, 0) else (current - prior) / prior
            deltas.append("N/A" if change is None else f"{'▲' if change >= 0 else '▼'} {abs(change):.1%} vs prior period")
        errors = sum(1 for d in bundle.diagnostics if d.level == "error")
        warnings = sum(1 for d in bundle.diagnostics if d.level == "warning")
        diagnostics = f"{len(bundle.tables)} table types · {errors} errors · {warnings} warnings · {max_date or 'no dates'}"
        return values + deltas + [diagnostics, make_funnel_figure(compute_funnel(bundle, date_range, regions_value), "Overall Funnel"), make_funnel_figure(compute_funnel(bundle, date_range, regions_value, paid=True), "Paid Funnel"), make_conversion_trend_figure(trend), make_source_donut_figure(compute_source_share(bundle, date_range, regions_value, "traffic"), "Traffic Source Share", _format_value("all_traffic", kpis["all_traffic"])), make_source_donut_figure(compute_source_share(bundle, date_range, regions_value, "leads"), "Leads Source Share", _format_value("all_leads", kpis["all_leads"])), make_source_donut_figure(compute_source_share(bundle, date_range, regions_value, "mqls"), "MQLs Source Share", _format_value("all_mqls", kpis["all_mqls"])), make_spend_revenue_figure(trend), make_heatmap_figure(compute_region_heatmap(bundle, date_range, regions_value), "MQL Conversion by Region")]

    # ---- 目标值：输入框 <-> localStorage <-> 卡片上的达成率 ----
    # 拆成三个小回调而不是塞进 update_dashboard：改目标时只重算 KPI，不重画 8 张图。
    # 存取用 dcc.Store 的 data / modified_timestamp 两个不同属性，
    # 不会让 Dash 判定成 input->store->input 的循环依赖。
    @app.callback(
        Output("target-store", "data"),
        *[Input(target_input_id(target_id), "value") for target_id in TARGET_IDS],
        State("target-store", "data"),
        prevent_initial_call=True,
    )
    def save_targets(*args):
        """把输入框的值写进浏览器本地存储；与已存的完全一致时不写，避免来回触发。"""
        values = args[: len(TARGET_IDS)]
        stored = args[-1] or {}
        payload = {target_id: as_number(raw) for target_id, raw in zip(TARGET_IDS, values)}
        if all(stored.get(target_id) == value for target_id, value in payload.items()) and set(stored) == set(payload):
            return no_update
        return payload

    @app.callback(
        *[Output(target_input_id(target_id), "value") for target_id in TARGET_IDS],
        Input("target-store", "modified_timestamp"),
        State("target-store", "data"),
        State("data-key", "data"),
    )
    def restore_targets(_timestamp, stored, data_key):
        """用浏览器里存过的目标值回填输入框；没存过就保留布局里的默认值。"""
        if not data_key:
            # 上传模式且还没上传：输入框还不存在，别去写不存在的组件
            return [no_update] * len(TARGET_IDS)
        if not stored:
            return [no_update] * len(TARGET_IDS)
        return [stored[target_id] if target_id in stored else no_update for target_id in TARGET_IDS]

    @app.callback(
        *[Output(target_progress_id(target_id), "children") for target_id in TARGET_IDS],
        *[Input(target_input_id(target_id), "value") for target_id in TARGET_IDS],
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("region-filter", "value"),
        Input("data-key", "data"),
    )
    def update_targets(*args):
        """达成率只认输入框里的值。

        不读 `target-store`：首次访问时 localStorage 还是空的，而输入框已经显示布局里的
        默认目标值，两者会打架（卡片显示 No target set，输入框却有数字）。持久化只由
        save/restore 两个回调负责，展示一律以输入框为准。
        """
        values = args[: len(TARGET_IDS)]
        start, end, selected_regions, data_key = args[len(TARGET_IDS) :]
        bundle = DATA_CACHE.get(data_key) if data_key else None
        if bundle is None:
            return [no_update] * len(TARGET_IDS)

        _min_date, max_date, default_start = _bundle_window(bundle)
        range_start = _as_date(start) or default_start
        range_end = _as_date(end) or max_date
        kpis = compute_kpis(bundle, (range_start, range_end), selected_regions or [])
        progress = compute_target_progress(kpis, dict(zip(TARGET_IDS, values)))
        return [_progress_line(progress[target_id]) for target_id in TARGET_IDS]

    return app


def _bool_flag(value: str) -> bool:
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None, help="跳过上传页，直接从这个目录加载 CSV（Docker/本地调试）")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--debug", default="1", help="开启 debug：Dash dev tools + 浏览器热刷新 + Werkzeug reloader")
    parser.add_argument("--reload", default="1", help="Werkzeug reloader：改 .py 后自动重启进程（需要能创建子进程）")
    args = parser.parse_args()
    debug = _bool_flag(args.debug)
    # 只有显式指定数据目录（CLI 或 DASHBOARD_DATA_DIR）才跳过上传页
    explicit_dir = args.data_dir or os.environ.get("DASHBOARD_DATA_DIR")
    create_app(explicit_dir).run(
        debug=debug,
        host=args.host,
        port=args.port,
        dev_tools_hot_reload=debug,
        dev_tools_ui=debug,
        # 直接透传给 Flask.run / werkzeug.run_simple
        use_reloader=debug and _bool_flag(args.reload),
    )
