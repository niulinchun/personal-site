"""
ledger 视图（整个模块需 admin 登录）。

页面：
- /ledger/          流水页（月份切换 + 汇总卡片 + 流水表格 + 模态框增删改）
- /ledger/report/   报表页（当月分类占比饼图 + 近 12 个月收入/支出趋势）

API（fetch 用，返回 JSON）：
- GET   /ledger/api/records/?month=YYYY-MM&page=N   流水分页
- POST  /ledger/api/records/                        新增流水
- GET/PUT/DELETE /ledger/api/records/<id>/          查看/编辑/删除
- GET/POST /ledger/api/categories/                   分类下拉；POST=模态框快捷加分类
"""
import datetime
import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from ledger.forms import RecordForm
from ledger.models import LedgerCategory, Record

RECORD_PAGE_SIZE = 15
TREND_MONTHS = 12

# ---------------------------------------------------------------------------
# 月份工具
# ---------------------------------------------------------------------------


def _parse_month(value):
    """'YYYY-MM' → 该月第一天/下月第一天。非法输入回退到当前月。"""
    target = None
    if value:
        try:
            parsed = datetime.datetime.strptime(value, "%Y-%m")
            target = datetime.date(parsed.year, parsed.month, 1)
        except ValueError:
            target = None
    if target is None:
        today = datetime.date.today()
        target = datetime.date(today.year, today.month, 1)
    start = target
    end = _shift_month(start, 1)
    label = f"{start.year}-{start.month:02d}"
    return label, start, end


def _shift_month(anchor: datetime.date, months: int) -> datetime.date:
    total = anchor.year * 12 + (anchor.month - 1) + months
    year, month = divmod(total, 12)
    return datetime.date(year, month + 1, 1)


def _month_summary(qs):
    """(收入合计, 支出合计, 结余)。"""
    agg = qs.aggregate(
        income=Sum("amount", filter=Q(type=LedgerCategory.Type.INCOME)),
        expense=Sum("amount", filter=Q(type=LedgerCategory.Type.EXPENSE)),
    )
    income = agg["income"] or 0
    expense = agg["expense"] or 0
    return float(income), float(expense), float(income - expense)


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


@login_required
def ledger_index(request):
    """流水页。"""
    month, start, end = _parse_month(request.GET.get("month"))

    month_records = (
        Record.objects.filter(record_date__gte=start, record_date__lt=end)
        .select_related("category")
        .order_by("-record_date", "-id")
    )
    income, expense, balance = _month_summary(Record.objects.filter(record_date__gte=start, record_date__lt=end))

    try:
        page_number = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page_number = 1
    paginator = Paginator(month_records, RECORD_PAGE_SIZE)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "ledger/index.html",
        {
            "month": month,
            "prev_month": _shift_month(start, -1).strftime("%Y-%m"),
            "next_month": end.strftime("%Y-%m"),
            "page_obj": page_obj,
            "records": page_obj.object_list,
            "categories": LedgerCategory.objects.all(),
            "income": income,
            "expense": expense,
            "balance": balance,
            "month_start": start,
            "month_end": _shift_month(start, 1) - datetime.timedelta(days=1),
        },
    )


@login_required
def ledger_report(request):
    """报表页：当月分类占比饼图 + 近 12 个月趋势柱状图。"""
    month, start, end = _parse_month(request.GET.get("month"))

    # 1) 当月分类占比（饼图）：按分类聚合，标注收入/支出类型
    pie_qs = (
        Record.objects.filter(record_date__gte=start, record_date__lt=end)
        .values("category__id", "category__name", "category__type")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    pie_data = [
        {
            "label": row["category__name"] or "未分类",
            "type": row["category__type"],
            "total": float(row["total"] or 0),
        }
        for row in pie_qs
        if row["total"] is not None
    ]

    # 2) 近 12 个月趋势：双序列（收入/支出）
    months = [_shift_month(start, i) for i in range(-TREND_MONTHS + 1, 1)]
    trend_start = months[0]
    trend_qs = (
        Record.objects.filter(record_date__gte=trend_start, record_date__lt=end)
        .annotate(m_key=TruncMonth("record_date"))
        .values("m_key")
        .annotate(
            income=Sum("amount", filter=Q(type=LedgerCategory.Type.INCOME)),
            expense=Sum("amount", filter=Q(type=LedgerCategory.Type.EXPENSE)),
        )
        .order_by("m_key")
    )
    trend_map = {
        f"{row['m_key'].year}-{row['m_key'].month:02d}": row
        for row in trend_qs
        if row["m_key"] is not None
    }
    trend_data = {
        "labels": [f"{m.year}-{m.month:02d}" for m in months],
        "income": [float((trend_map.get(f"{m.year}-{m.month:02d}") or {}).get("income") or 0) for m in months],
        "expense": [float((trend_map.get(f"{m.year}-{m.month:02d}") or {}).get("expense") or 0) for m in months],
    }

    income, expense, balance = _month_summary(Record.objects.filter(record_date__gte=start, record_date__lt=end))

    return render(
        request,
        "ledger/report.html",
        {
            "month": month,
            "prev_month": _shift_month(start, -1).strftime("%Y-%m"),
            "next_month": end.strftime("%Y-%m"),
            "pie_json": json.dumps(pie_data, ensure_ascii=False),
            "trend_json": json.dumps(trend_data, ensure_ascii=False),
            "income": income,
            "expense": expense,
            "balance": balance,
            "month_start": start,
            "month_end": _shift_month(start, 1) - datetime.timedelta(days=1),
        },
    )


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


def _record_payload(record: Record):
    return {
        "id": record.id,
        "type": record.type,
        "category_id": record.category_id,
        "category": record.category.name if record.category else "",
        "amount": str(record.amount),
        "note": record.note,
        "record_date": record.record_date.strftime("%Y-%m-%d"),
    }


def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def _form_data(request):
    """POST/PUT 兼容 form 与 JSON 两种提交。"""
    if request.content_type and "json" in request.content_type:
        return dict(_json_body(request))
    return request.POST


@login_required
@require_http_methods(["GET"])
def api_record_page(request):
    """流水分页（用于前端翻页）。"""
    month, start, end = _parse_month(request.GET.get("month"))
    qs = Record.objects.filter(record_date__gte=start, record_date__lt=end).select_related("category")
    order = request.GET.get("order", "date_desc")
    if order == "amount_desc":
        qs = qs.order_by("-amount", "-id")
    elif order == "amount_asc":
        qs = qs.order_by("amount", "-id")
    elif order == "date_asc":
        qs = qs.order_by("record_date", "-id")
    else:
        qs = qs.order_by("-record_date", "-id")
    page = Paginator(qs, RECORD_PAGE_SIZE)
    try:
        number = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        number = 1
    page_obj = page.get_page(number)

    return JsonResponse(
        {
            "items": [_record_payload(r) for r in page_obj.object_list],
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
            "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            "prev_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def api_records_dispatch(request):
    """/ledger/api/records/ 入口：GET=分页列表，POST=新增。"""
    if request.method == "GET":
        return api_record_page(request)
    return api_record_create(request)


@login_required
@require_http_methods(["POST"])
def api_record_create(request):
    form = RecordForm(_form_data(request))
    if form.is_valid():
        record = form.save()
        return JsonResponse({"record": _record_payload(record)}, status=201)
    return JsonResponse({"errors": form.errors}, status=400)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_record_detail(request, pk):
    record = get_object_or_404(Record, pk=pk)
    if request.method == "GET":
        return JsonResponse({"record": _record_payload(record)})
    if request.method == "DELETE":
        record.delete()
        return JsonResponse({"ok": True})
    form = RecordForm(_form_data(request), instance=record)
    if form.is_valid():
        record = form.save()
        return JsonResponse({"record": _record_payload(record)})
    return JsonResponse({"errors": form.errors}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def api_categories(request):
    if request.method == "GET":
        items = [{"id": c.id, "name": c.name, "type": c.type} for c in LedgerCategory.objects.all()]
        return JsonResponse({"items": items})

    # POST：模态框快捷加分类（正式管理仍在 /admin/）
    data = _form_data(request)
    name = (data.get("name") or "").strip()
    cat_type = (data.get("type") or LedgerCategory.Type.EXPENSE).strip()
    if not name:
        return JsonResponse({"error": "分类名不能为空"}, status=400)
    if cat_type not in LedgerCategory.Type.values:
        cat_type = LedgerCategory.Type.EXPENSE
    category, _created = LedgerCategory.objects.get_or_create(name=name, defaults={"type": cat_type})
    if not _created and category.type != cat_type:
        category.type = cat_type
        category.save(update_fields=["type"])
    return JsonResponse(
        {"category": {"id": category.id, "name": category.name, "type": category.type}},
        status=201,
    )
