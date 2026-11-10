/* 记账报表：Chart.js 渲染当月分类占比（饼）与 12 个月收支趋势（柱） */
(function () {
  "use strict";

  var pieCanvas = document.getElementById("pie-chart");
  var trendCanvas = document.getElementById("trend-chart");
  if (typeof Chart === "undefined") return;

  var INCOME_PALETTE = ["#2f9e44", "#69db7c", "#94d82d", "#37b24d", "#66a80f", "#82c91e"];
  var EXPENSE_PALETTE = ["#e03131", "#f76707", "#f59f00", "#d6336c", "#862e9c", "#495eae",
                        "#0ca678", "#e64980", "#f08c00", "#5f3dc4", "#c92a2a", "#a61e4d"];

  Chart.defaults.font.family =
    getComputedStyle(document.body).fontFamily || "system-ui, -apple-system, 'Segoe UI', sans-serif";

  /* -------------------------------------------------- 饼图 */

  if (pieCanvas) {
    var pieData = [];
    try { pieData = JSON.parse(pieCanvas.dataset.pie || "[]"); } catch (e) { pieData = []; }

    if (!pieData.length) {
      var parent = pieCanvas.closest(".card-body");
      parent.innerHTML = '<p class="text-muted m-auto">本月暂无数据</p>';
    } else {
      var usedIncome = 0, usedExpense = 0;
      new Chart(pieCanvas, {
        type: "pie",
        data: {
          labels: pieData.map(function (item) {
            return item.type === "income" ? item.label + "（收入）" : item.label + "（支出）";
          }),
          datasets: [{
            data: pieData.map(function (item) { return item.total; }),
            backgroundColor: pieData.map(function (item) {
              if (item.type === "income") return INCOME_PALETTE[usedIncome++ % INCOME_PALETTE.length];
              return EXPENSE_PALETTE[usedExpense++ % EXPENSE_PALETTE.length];
            }),
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  return ctx.label + "：¥" + Number(ctx.parsed).toFixed(2);
                }
              }
            }
          }
        }
      });
    }
  }

  /* -------------------------------------------------- 趋势柱状图 */

  if (trendCanvas) {
    var trend = {};
    try { trend = JSON.parse(trendCanvas.dataset.trend || "{}"); } catch (e) { trend = {}; }

    new Chart(trendCanvas, {
      type: "bar",
      data: {
        labels: trend.labels || [],
        datasets: [
          {
            label: "收入",
            data: trend.income || [],
            backgroundColor: "rgba(47, 158, 68, 0.75)",
            borderRadius: 4
          },
          {
            label: "支出",
            data: trend.expense || [],
            backgroundColor: "rgba(224, 49, 49, 0.75)",
            borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true },
          x: { grid: { display: false } }
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + "：¥" + Number(ctx.parsed.y).toFixed(2);
              }
            }
          }
        }
      }
    });
  }
})();
