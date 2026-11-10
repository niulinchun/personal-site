"""
ledger 模块测试：登录边界、流水 CRUD、月份汇总、分页、分类接口、报表页。
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase

from ledger.models import LedgerCategory, Record


class LedgerBoundaryTests(TestCase):
    def test_index_requires_login(self):
        self.assertEqual(self.client.get("/ledger/").status_code, 302)

    def test_report_requires_login(self):
        self.assertEqual(self.client.get("/ledger/report/").status_code, 302)

    def test_api_requires_login(self):
        self.assertEqual(self.client.get("/ledger/api/records/").status_code, 302)
        self.assertEqual(
            self.client.post("/ledger/api/records/", {}, content_type="application/json").status_code, 302)


class LedgerRecordApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("me", "me@example.com", "pass123456")
        self.client.force_login(self.user)
        self.income_cat = LedgerCategory.objects.create(name="工资", type=LedgerCategory.Type.INCOME)
        self.expense_cat = LedgerCategory.objects.create(name="餐饮", type=LedgerCategory.Type.EXPENSE)

    def _create(self, **overrides):
        payload = dict(
            category=self.expense_cat.pk,
            amount="12.50",
            note="午饭",
            record_date="2026-02-10",
        )
        payload.update(overrides)
        return self.client.post(
            "/ledger/api/records/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_create_record_follows_category_type(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201, resp.content)
        record = Record.objects.get()
        self.assertEqual(record.type, LedgerCategory.Type.EXPENSE)
        self.assertEqual(str(record.amount), "12.50")

        resp = self._create(category=self.income_cat.pk, amount="3000.00", note="发薪", record_date="2026-02-05")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Record.objects.filter(type="income").count(), 1)

    def test_create_validation(self):
        # 缺分类
        resp = self._create(category="")
        self.assertEqual(resp.status_code, 400)
        # 负数
        resp = self._create(amount="-1")
        self.assertEqual(resp.status_code, 400)
        # 金额非数字
        resp = self._create(amount="abc")
        self.assertEqual(resp.status_code, 400)
        # 日期非法
        resp = self._create(record_date="2026/02/xx")
        self.assertEqual(resp.status_code, 400)

    def test_update_and_delete(self):
        resp = self._create()
        record_id = resp.json()["record"]["id"]

        resp = self.client.put(
            f"/ledger/api/records/{record_id}/",
            data=json.dumps({"category": self.income_cat.pk, "amount": "88.00", "note": "改", "record_date": "2026-02-12"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        record = Record.objects.get(pk=record_id)
        self.assertEqual(record.type, LedgerCategory.Type.INCOME)  # 类型跟随新分类
        self.assertEqual(float(record.amount), 88.0)

        resp = self.client.delete(f"/ledger/api/records/{record_id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Record.objects.exists())

    def test_record_page_filter_and_paging(self):
        for i in range(20):
            resp = self._create(amount=str(i), record_date=f"2026-02-{i + 1:02d}" if i < 28 else "2026-02-01")
        data = self.client.get("/ledger/api/records/", {"month": "2026-02"}).json()
        self.assertEqual(len(data["items"]), 15)
        self.assertEqual(data["next_page"], 2)
        self.assertTrue(data["has_next"])
        # 下一页
        data2 = self.client.get("/ledger/api/records/", {"month": "2026-02", "page": 2}).json()
        self.assertEqual(len(data2["items"]), 5)
        self.assertFalse(data2["has_next"])

    def test_index_page_summary(self):
        self._create(amount="100", record_date="2026-02-05")       # 支出
        self._create(category=self.income_cat.pk, amount="250", record_date="2026-02-06")
        self._create(amount="40.5", record_date="2026-03-01")      # 下月，不计

        resp = self.client.get("/ledger/?month=2026-02")
        self.assertEqual(resp.status_code, 200)
        # 收入 250 / 支出 100 / 结余 150
        self.assertContains(resp, "250")
        self.assertContains(resp, "150")
        self.assertEqual(Record.objects.count(), 3)

    def test_categories_endpoint(self):
        resp = self.client.get("/ledger/api/categories/")
        items = resp.json()["items"]
        names = [i["name"] for i in items]
        self.assertIn("工资", names)
        self.assertIn("餐饮", names)

    def test_report_renders_charts_data(self):
        self._create(amount="10", record_date="2026-02-03")          # 餐饮支出
        self._create(category=self.income_cat.pk, amount="2000", record_date="2026-01-15")
        resp = self.client.get("/ledger/report/?month=2026-02")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "当月分类占比")
        self.assertContains(resp, "餐饮")
